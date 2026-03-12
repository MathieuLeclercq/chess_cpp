#include "mcts.hpp"
#include <algorithm>
#include <numeric>
#include <stdexcept>

MCTS::MCTS(const std::string& model_path)
    : env(ORT_LOGGING_LEVEL_WARNING, "AlphaZeroMCTS")
{
    // Optimisations CPU pour ONNX Runtime
    session_options.SetIntraOpNumThreads(1);
    session_options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);

    // Support string conversion for Windows wide strings
    std::wstring w_model_path(model_path.begin(), model_path.end());
    session = std::make_unique<Ort::Session>(env, w_model_path.c_str(), session_options);
}

void MCTS::backup(MCTSNode* node, float value) {
    while (node != nullptr) {
        node->visit_count += 1;
        node->total_value += value;
        value = -value;
        node = node->parent;
    }
}

std::pair<MCTSNode*, int> MCTS::select_leaf(MCTSNode* root, Chessboard& board, float c_puct, bool& aborted) {
    MCTSNode* node = root;
    int moves_played = 0;
    aborted = false;

    while (!node->children.empty() && !node->is_terminal) {
        float max_ucb = -1e9f;
        int best_idx = -1;

        float parent_q = node->q_value();
        for (const auto& pair : node->children) {
            int idx = pair.first;
            MCTSNode* child = pair.second.get();

            float score = child->ucb_score(node->visit_count, parent_q, c_puct);
            if (score > max_ucb) {
                max_ucb = score;
                best_idx = idx;
            }
        }

        MCTSNode* next_node = node->children[best_idx].get();

        bool success = apply_move_by_index(board, best_idx);
        if (!success) {
            throw std::runtime_error("problème lors de la génération du coup");
        }

        node = next_node;
        moves_played++;
    }

    return { node, moves_played };
}

void MCTS::evaluate_onnx(const std::vector<float>& input_tensor, std::vector<float>& policy, float& value) {
    std::array<int64_t, 4> input_shape = { 1, 119, 8, 8 };
    auto memory_info = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);

    Ort::Value input_ort = Ort::Value::CreateTensor<float>(
        memory_info, const_cast<float*>(input_tensor.data()), input_tensor.size(),
        input_shape.data(), input_shape.size()
    );

    const char* input_names[] = { "input" };
    const char* output_names[] = { "policy", "value" };

    auto output_tensors = session->Run(Ort::RunOptions{ nullptr }, input_names, &input_ort, 1, output_names, 2);

    float* policy_data = output_tensors[0].GetTensorMutableData<float>();
    float* value_data = output_tensors[1].GetTensorMutableData<float>();

    policy.assign(policy_data, policy_data + 4672);

    // Application du Softmax manuel sur les logits de la Policy
    float max_logit = *std::max_element(policy.begin(), policy.end());
    float sum_exp = 0.0f;
    for (float& l : policy) {
        l = std::exp(l - max_logit);
        sum_exp += l;
    }
    for (float& l : policy) {
        l /= sum_exp;
    }

    value = value_data[0];
}

float MCTS::expand_node_single(MCTSNode* node, Chessboard& board) {


    // --- DÉTECTION  DES NULLES  ---
    if (board.checkThreefoldRepetition() ||
        board.getHalfMoveClock() >= 100 ||
        board.checkInsufficientMaterial()) {

        node->is_terminal = true;
        return 0.0f; // Score d'égalité stricte
    }

    // --- DÉTECTION MAT / PAT
    std::vector<int> legal_indices = board.getLegalMoveIndices();
    if (legal_indices.empty()) {
        node->is_terminal = true;
        return board.isInCheck() ? -1.0f : 0.0f;
    }

    // --- GÉNÉRATION DU TENSEUR ET APPEL ONNX ---
    std::vector<float> tensor = board.getAlphaZeroTensor();
    uint64_t hash = board.getZobristHash();

    float value;
    std::vector<std::pair<int, float>> legal_policy;

    // --- TABLE DE TRANSPOSITION ---
    auto it = transposition_table.find(hash);
    if (it != transposition_table.end()) {
        legal_policy = it->second.legal_policy;
        value = it->second.value;
    }
    else {
        std::vector<float> full_policy;
        evaluate_onnx(tensor, full_policy, value);

        // Extraction stricte des coups légaux pour le stockage
        legal_policy.reserve(legal_indices.size());
        for (int idx : legal_indices) {
            legal_policy.push_back({ idx, full_policy[idx] });
        }

        if (transposition_table.size() > 1000000) {
            transposition_table.clear();
        }

        transposition_table[hash] = { legal_policy, value };
    }

    // Calcul de la somme pour la normalisation à partir du vecteur compact
    float sum_legal = 0.0f;
    for (const auto& pair : legal_policy) {
        sum_legal += pair.second;
    }

    // Instanciation des enfants
    if (sum_legal > 0.0f) {
        for (const auto& pair : legal_policy) {
            int idx = pair.first;
            float prob = pair.second / sum_legal;
            node->children[idx] = std::make_unique<MCTSNode>(prob, idx, node);
        }
    }
    else {
        float uniform_prob = 1.0f / legal_indices.size();
        for (int idx : legal_indices) {
            node->children[idx] = std::make_unique<MCTSNode>(uniform_prob, idx, node);
        }
    }

    return value;
}

std::vector<float> MCTS::mcts_search(Chessboard& board, int num_simulations, float c_puct, bool add_dirichlet) {

    // --- SANITY CHECK ZOBRIST ---
    if (board.getZobristHash() != board.computeZobristFromScratch()) {
        throw std::runtime_error("Erreur fatale : Desynchronisation du Zobrist Hash detectee !");
    }

    std::unique_ptr<MCTSNode> root = std::make_unique<MCTSNode>(0.0f);
    expand_node_single(root.get(), board);

    if (add_dirichlet && !root->children.empty()) {
        std::mt19937 gen(std::random_device{}());
        std::gamma_distribution<float> gamma(0.3f, 1.0f); // Alpha = 0.3

        float epsilon = 0.12f;
        float sum_noise = 0.0f;
        std::vector<float> noise(root->children.size());

        for (size_t i = 0; i < root->children.size(); i++) {
            noise[i] = gamma(gen);
            sum_noise += noise[i];
        }

        int i = 0;
        for (auto& pair : root->children) {
            MCTSNode* child = pair.second.get();
            float dirichlet = noise[i++] / sum_noise;
            child->prior = (1.0f - epsilon) * child->prior + epsilon * dirichlet;
        }
    }

    for (int sim = 0; sim < num_simulations; sim++) {
        bool aborted;
        auto [node, moves_played] = select_leaf(root.get(), board, c_puct, aborted);

        if (aborted) {
            for (int i = 0; i < moves_played; i++) board.undoMove();
            continue;
        }

        if (node->is_terminal) {
            float value = board.isInCheck() ? -1.0f : 0.0f;
            backup(node, value);
            for (int i = 0; i < moves_played; i++) board.undoMove();
            continue;
        }

        if (node->children.empty()) {
            float value = expand_node_single(node, board);
            backup(node, value);
        }

        for (int i = 0; i < moves_played; i++) {
            board.undoMove();
        }
    }

    std::vector<float> pi(4672, 0.0f);
    float sum_visits = 0.0f;
    for (const auto& pair : root->children) {
        int idx = pair.first;
        MCTSNode* child = pair.second.get();
        pi[idx] = static_cast<float>(child->visit_count);
        sum_visits += pi[idx];
    }

    if (sum_visits > 0.0f) {
        for (float& prob : pi) {
            prob /= sum_visits;
        }
    }

    return pi;
}

bool MCTS::apply_move_by_index(Chessboard& board, int index) {
    bool is_black = (board.getTurn() == BLACK);
    int plane = index / 64;
    int remainder = index % 64;
    int orig_r = remainder / 8;
    int orig_f = remainder % 8;

    int df = 0, dr = 0;
    PieceType promotion = NONE;

    if (plane < 56) {
        int dir_idx = plane / 7;
        int dist = (plane % 7) + 1;
        int dirs[8][2] = { {0, 1}, {1, 1}, {1, 0}, {1, -1}, {0, -1}, {-1, -1}, {-1, 0}, {-1, 1} };
        df = dirs[dir_idx][0] * dist;
        dr = dirs[dir_idx][1] * dist;
    }
    else if (plane < 64) {
        int knight_idx = plane - 56;
        int knight_moves[8][2] = { {1, 2}, {2, 1}, {2, -1}, {1, -2}, {-1, -2}, {-2, -1}, {-2, 1}, {-1, 2} };
        df = knight_moves[knight_idx][0];
        dr = knight_moves[knight_idx][1];
    }
    else {
        int sub_idx = plane - 64;
        int dir_idx = sub_idx / 3;
        int p_idx = sub_idx % 3;
        df = dir_idx - 1;
        dr = 1;

        if (p_idx == 0) promotion = KNIGHT;
        else if (p_idx == 1) promotion = BISHOP;
        else promotion = ROOK;
    }

    int dest_f = orig_f + df;
    int dest_r = orig_r + dr;

    if (is_black) {
        orig_r = 7 - orig_r;
        dest_r = 7 - dest_r;
    }

    // Gestion automatique de la promotion en Dame si non spécifiée
    if (board.getSquare(orig_f, orig_r).getPiece().getType() == PAWN) {
        if ((!is_black && dest_r == 7) || (is_black && dest_r == 0)) {
            if (promotion == NONE) {
                promotion = QUEEN;
            }
        }
    }

    return board.movePiece(orig_f, orig_r, dest_f, dest_r, promotion, false);
}
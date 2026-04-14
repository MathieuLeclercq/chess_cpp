#include "mcts.hpp"
#include <algorithm>
#include <cmath>
#include <random>
#include <utility>
#include <stdexcept>


// ============================================================
//                     MCTSNode
// ============================================================

MCTSNode::MCTSNode(float prior, int move_idx, MCTSNode* parent)
    : m_prior(prior), m_move_idx(move_idx), m_parent(parent),
    m_visit_count(0), m_total_value(0.0f), m_is_terminal(false) {
}

float MCTSNode::ucb_score(float exploration_factor, float parent_q, float fpu_reduction) const {
    // Implémentation du FPU de LeelaChess0
    // Si noeud pas visité, on ne met pas sa Q value à 0,
    // mais on utilise celle du parent.
    float u = exploration_factor * m_prior / (1.0f + m_visit_count);
    // FPU_reduction = 0.1f
    float exploitation = (m_visit_count == 0) ? (parent_q - fpu_reduction) : -q_value();

    return exploitation + u;
}

float MCTSNode::q_value() const {
    if (m_visit_count == 0) return 0.0f;
    return m_total_value / m_visit_count;
}

MCTSNode* MCTSNode::find_child(int idx) const {
    for (const auto& pair : m_children) {
        if (pair.first == idx) return pair.second.get();
    }
    return nullptr;
}

bool MCTSNode::has_child(int idx) const {
    return find_child(idx) != nullptr;
}

std::unique_ptr<MCTSNode> MCTSNode::extract_child(int idx) {
    for (auto it = m_children.begin(); it != m_children.end(); ++it) {
        if (it->first == idx) {
            auto result = std::move(it->second);
            m_children.erase(it);
            return result;
        }
    }
    return nullptr;
}


// ============================================================
//                     MCTS
// ============================================================

MCTS::MCTS(ONNXEvaluator* evaluator) : m_evaluator(evaluator) {
    transposition_table.resize(TT_SIZE);
    m_eval_tensor.reserve(119 * 64);
    m_eval_policy.reserve(4672);
}

void MCTS::backup(MCTSNode* node, float value) {
    while (node != nullptr) {
        node->m_visit_count += 1;
        node->m_total_value += value;
        value = -value;
        node = node->m_parent;
    }
}

std::pair<MCTSNode*, int> MCTS::select_leaf(MCTSNode* root, Chessboard& board, float c_puct, bool& aborted) {
    MCTSNode* node = root;
    int moves_played = 0;
    aborted = false;

    // On continue tant qu'on n'est pas sur un état terminal
    while (!node->m_is_terminal) {

        // --- 1. EXPANSION PARESSEUSE (Lazy Expansion) ---
        // Si le noeud n'a pas d'enfants, on regarde s'il est dans la Table de Transposition
        if (node->m_children.empty()) {
            uint64_t hash = board.getZobristHash();
            size_t tt_idx = hash % TT_SIZE;

            if (transposition_table[tt_idx].hash == hash && !transposition_table[tt_idx].legal_policy.empty()) {
                const auto& cached_policy = transposition_table[tt_idx].legal_policy;
                float sum_legal = 0.0f;
                for (const auto& pair : cached_policy) sum_legal += pair.second;

                node->m_children.reserve(cached_policy.size());

                for (const auto& pair : cached_policy) {
                    float prob = (sum_legal > 0.0f) ? (pair.second / sum_legal) : (1.0f / (float)cached_policy.size());
                    node->m_children.emplace_back(pair.first, std::make_unique<MCTSNode>(prob, pair.first, node));
                }
            }
            else {
                // Pas en cache : c'est une vraie feuille qui nécessite le GPU
                break;
            }
        }

        // --- 2. CALCUL DU FPU (COHÉRENT AVEC TON ANCIEN CODE) ---
        float visited_policy_sum = 0.0f;
        for (const auto& pair : node->m_children) {
            if (pair.second->m_visit_count > 0) {
                visited_policy_sum += pair.second->m_prior;
            }
        }
        float fpu_reduction = 0.30f * std::sqrt(visited_policy_sum);

        // --- 3. SÉLECTION DU MEILLEUR COUP (UCB) ---
        float max_ucb = -1e9f;
        int best_move_idx = -1;
        float parent_q = node->q_value();
        float exploration_factor = c_puct * std::sqrt(static_cast<float>(node->m_visit_count));

        for (const auto& pair : node->m_children) {
            float score = pair.second->ucb_score(exploration_factor, parent_q, fpu_reduction);
            if (score > max_ucb) {
                max_ucb = score;
                best_move_idx = pair.first;
            }
        }

        if (best_move_idx == -1) break;

        // --- 4. DESCENTE ET MISE À JOUR ---
        MCTSNode* next_node = node->find_child(best_move_idx);
        if (!apply_move_by_index(board, best_move_idx)) {
            throw std::runtime_error("Problème lors de l'application du coup dans select_leaf");
        }

        node = next_node;
        moves_played++;

        // Vérification dynamique pendant la descente
        if (board.checkThreefoldRepetition() ||
            board.getHalfMoveClock() >= 100 ||
            board.checkInsufficientMaterial()) {
            node->m_is_terminal = true;
            break;
        }
    }

    return { node, moves_played };
}

float MCTS::expand_node_single(MCTSNode* node, Chessboard& board) {

    if (board.checkThreefoldRepetition() || board.getHalfMoveClock() >= 100 || board.checkInsufficientMaterial()) {
        node->m_is_terminal = true;
        return 0.0f;
    }

    uint64_t hash = board.getZobristHash();
    size_t tt_idx = hash % TT_SIZE; // <-- L'index constant en O(1)

    // 2. TABLE DE TRANSPOSITION (Lookup immédiat)
    if (transposition_table[tt_idx].hash == hash && !transposition_table[tt_idx].legal_policy.empty()) {
        return transposition_table[tt_idx].value; // On retourne juste la valeur, pas de création de noeuds !
    }

    // 3. CACHE MISS
    std::vector<int> legal_indices = board.getLegalMoveIndices();
    if (legal_indices.empty()) {
        node->m_is_terminal = true;
        return board.isInCheck() ? -1.0f : 0.0f;
    }

    board.getAlphaZeroTensor(m_eval_tensor);
    float value;
    m_evaluator->evaluate(m_eval_tensor, m_eval_policy, value);

    // 4. STOCKAGE SANS ALLOCATION (Réutilisation de la capacité)
    transposition_table[tt_idx].hash = hash;
    transposition_table[tt_idx].value = value;
    transposition_table[tt_idx].legal_policy.clear(); // O(1), garde la mémoire allouée intacte

    float sum_legal = 0.0f;
    for (int idx : legal_indices) {
        float prob = m_eval_policy[idx];
        transposition_table[tt_idx].legal_policy.push_back({ idx, prob }); // Pas d'allocation !
        sum_legal += prob;
    }

    if (sum_legal > 0.0f) {
        node->m_children.reserve(transposition_table[tt_idx].legal_policy.size());
        for (const auto& pair : transposition_table[tt_idx].legal_policy) {
            node->m_children.emplace_back(
                pair.first, std::make_unique<MCTSNode>(pair.second / sum_legal, pair.first, node));
        }
    }
    else {
        node->m_children.reserve(legal_indices.size());
        float uniform_prob = 1.0f / legal_indices.size();
        for (int idx : legal_indices) {
            node->m_children.emplace_back(idx, std::make_unique<MCTSNode>(uniform_prob, idx, node));
        }
    }

    return value;
}

void MCTS::add_dirichlet_noise(MCTSNode* root) {
    if (root->m_children.empty()) return;
    std::mt19937 gen(std::random_device{}());
    std::gamma_distribution<float> gamma(0.3f, 1.0f); // Alpha = 0.3 pour les échecs

    float sum_noise = 0.0f;
    std::vector<float> noise(root->m_children.size());
    for (size_t i = 0; i < root->m_children.size(); i++) {
        noise[i] = gamma(gen);
        sum_noise += noise[i];
    }

    int i = 0;
    float epsilon = 0.12f; // 0.25 pour alphazero
    for (auto& pair : root->m_children) {
        float dirichlet = noise[i++] / sum_noise;
        pair.second->m_prior = (1.0f - epsilon) * pair.second->m_prior + epsilon * dirichlet;
    }
}

std::vector<float> MCTS::mcts_search(Chessboard& board, int num_simulations, float c_puct, bool add_dirichlet) {

    //if (board.getZobristHash() != board.computeZobristFromScratch()) {
    //    throw std::runtime_error("Erreur fatale : Desynchronisation du Zobrist Hash detectee !");
    //}

    std::unique_ptr<MCTSNode> root = std::make_unique<MCTSNode>(0.0f);
    expand_node_single(root.get(), board);

    if (add_dirichlet) {
        add_dirichlet_noise(root.get());
    }

    for (int sim = 0; sim < num_simulations; sim++) {
        bool aborted;
        auto [node, moves_played] = select_leaf(root.get(), board, c_puct, aborted);

        if (aborted) {
            for (int i = 0; i < moves_played; i++) board.undoMove();
            continue;
        }

        if (node->m_is_terminal) {
            float value = 0.0f;
            // On teste d'abord les conditions de nulle (très rapide)
            if (board.checkThreefoldRepetition() || 
                board.getHalfMoveClock() >= 100 || 
                board.checkInsufficientMaterial()) {
                value = 0.0f;
            }
            // Si pas nulle, c'est mat ou pat. On teste l'échec.
            else {
                value = board.isInCheck() ? -1.0f : 0.0f;
            }

            backup(node, value);
            for (int i = 0; i < moves_played; i++) board.undoMove();
            continue;
        }

        if (node->m_children.empty()) {
            float value = expand_node_single(node, board);
            backup(node, value);
        }

        for (int i = 0; i < moves_played; i++) {
            board.undoMove();
        }
    }

    std::vector<float> pi(4672, 0.0f);
    float sum_visits = 0.0f;
    for (const auto& pair : root->m_children) {
        int idx = pair.first;
        MCTSNode* child = pair.second.get();
        pi[idx] = static_cast<float>(child->m_visit_count);
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


// ============================================================
//                     ANALYSE CONTINUE
// ============================================================

void MCTS::reset_analysis() {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_analysis_root.reset();
}

void MCTS::update_root(int move_idx) {
    std::lock_guard<std::mutex> lock(m_mutex);

    if (m_analysis_root && m_analysis_root->has_child(move_idx)) {
        m_analysis_root = m_analysis_root->extract_child(move_idx);
        m_analysis_root->m_parent = nullptr;
    }
    else {
        m_analysis_root.reset();
    }
}

float MCTS::get_root_q() const {
    if (!m_analysis_root) return 0.0f;
    return m_analysis_root->q_value();
}

void MCTS::step_analysis(Chessboard& board, int num_simulations, float c_puct) {
    // 1. Initialisation paresseuse protégée par un scope très court
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_analysis_root) {
            m_analysis_root = std::make_unique<MCTSNode>(0.0f);
            expand_node_single(m_analysis_root.get(), board);
        }
    }

    // 2. Boucle de simulation
    for (int sim = 0; sim < num_simulations; sim++) {

        // Le mutex se verrouille ici pour UNE seule simulation...
        std::lock_guard<std::mutex> lock(m_mutex);

        bool aborted;
        auto [node, moves_played] = select_leaf(m_analysis_root.get(), board, c_puct, aborted);

        if (aborted) {
            for (int i = 0; i < moves_played; i++) board.undoMove();
            continue;
        }

        if (node->m_is_terminal) {
            float value = 0.0f;
            if (board.checkThreefoldRepetition() ||
                board.getHalfMoveClock() >= 100 ||
                board.checkInsufficientMaterial()) {
                value = 0.0f;
            }
            else {
                value = board.isInCheck() ? -1.0f : 0.0f;
            }

            backup(node, value);
            for (int i = 0; i < moves_played; i++) board.undoMove();
            continue;
        }

        if (node->m_children.empty()) {
            float value = expand_node_single(node, board);
            backup(node, value);
        }

        for (int i = 0; i < moves_played; i++) {
            board.undoMove();
        }
    }
}

std::vector<MoveStats> MCTS::get_analysis_results() const {
    std::lock_guard<std::mutex> lock(const_cast<MCTS&>(*this).m_mutex);

    std::vector<MoveStats> results;
    if (!m_analysis_root) return results;

    for (const auto& pair : m_analysis_root->m_children) {
        int idx = pair.first;
        MCTSNode* child = pair.second.get();

        if (child->m_visit_count > 0) {
            results.push_back({
                idx,
                child->m_visit_count,
                -child->q_value(),
                child->m_prior
                });
        }
    }

    std::sort(results.begin(), results.end(), [](const MoveStats& a, const MoveStats& b) {
        return a.visits > b.visits;
        });

    return results;
}

MCTSNode* MCTS::advance_to_leaf(MCTSNode* root, Chessboard& board, float c_puct, int& moves_played) {
    bool aborted;
    auto [node, moves] = select_leaf(root, board, c_puct, aborted);
    moves_played = moves;

    // Cas 1 : Coup invalide généré
    if (aborted) {
        for (int i = 0; i < moves_played; i++) board.undoMove();
        return nullptr;
    }

    // Cas 2 : Fin de partie (Mat, Pat, Nulle)
    if (node->m_is_terminal) {
        float value = 0.0f;
        if (board.checkThreefoldRepetition() ||
            board.getHalfMoveClock() >= 100 ||
            board.checkInsufficientMaterial()) {
            value = 0.0f;
        }
        else {
            value = board.isInCheck() ? -1.0f : 0.0f;
        }
        backup(node, value);
        for (int i = 0; i < moves_played; i++) board.undoMove();
        return nullptr; // Pas besoin du GPU
    }

    // Cas 3 : On vérifie la Table de Transposition (TT) AVANT d'embêter le GPU
    uint64_t hash = board.getZobristHash();
    size_t tt_idx = hash % TT_SIZE;

    if (transposition_table[tt_idx].hash == hash && !transposition_table[tt_idx].legal_policy.empty()) {
        backup(node, transposition_table[tt_idx].value);
        for (int i = 0; i < moves_played; i++) board.undoMove();
        return nullptr; // Pas de création de noeuds ici 
    }

    // Cas 4 : Vraie feuille non explorée
    // On retourne le nœud. Le manager va extraire le tenseur, l'envoyer au GPU,
    // puis appeler expand_and_backup() plus tard.
    return node;
}

void MCTS::expand_and_backup(MCTSNode* leaf_node, Chessboard& board, const float* policy, float value) {
    // Cette fonction est appelée PAR LE MANAGER une fois que l'inférence ONNX est terminée

    std::vector<int> legal_indices = board.getLegalMoveIndices();
    if (legal_indices.empty()) {
        // Sécurité ultime au cas où
        leaf_node->m_is_terminal = true;
        backup(leaf_node, board.isInCheck() ? -1.0f : 0.0f);
        return;
    }

    // Mise en cache dans la Table de Transposition
    uint64_t hash = board.getZobristHash();
    size_t tt_idx = hash % TT_SIZE;
    transposition_table[tt_idx].hash = hash;
    transposition_table[tt_idx].value = value;
    transposition_table[tt_idx].legal_policy.clear();

    float sum_legal = 0.0f;
    for (int idx : legal_indices) {
        float prob = policy[idx];
        transposition_table[tt_idx].legal_policy.push_back({ idx, prob });
        sum_legal += prob;
    }

    if (sum_legal > 0.0f) {
        leaf_node->m_children.reserve(transposition_table[tt_idx].legal_policy.size());
        for (const auto& pair : transposition_table[tt_idx].legal_policy) {
            leaf_node->m_children.emplace_back(
                pair.first, std::make_unique<MCTSNode>(pair.second / sum_legal, pair.first, leaf_node));
        }
    }
    else {
        leaf_node->m_children.reserve(legal_indices.size());
        float uniform_prob = 1.0f / legal_indices.size();
        for (int idx : legal_indices) {
            leaf_node->m_children.emplace_back(idx, std::make_unique<MCTSNode>(uniform_prob, idx, leaf_node));
        }
    }

    // On remonte la valeur prédite
    backup(leaf_node, value);
}

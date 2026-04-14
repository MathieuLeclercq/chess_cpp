#include "selfplay_manager.hpp"
#include <iostream>
#include <random>
#include <chrono>
#include <iomanip>

SelfPlayManager::SelfPlayManager(
    ONNXEvaluator* evaluator, 
    int num_concurrent_games, 
    int slow_sims, int fast_sims, float slow_ratio)
    : m_evaluator(evaluator),
      m_num_concurrent_games(num_concurrent_games),
      m_slow_sims(slow_sims),
      m_fast_sims(fast_sims),
      m_slow_ratio(slow_ratio)
{
    m_boards.resize(num_concurrent_games);
    m_roots.resize(num_concurrent_games);
    m_sims_completed.resize(num_concurrent_games, 0);
    m_is_waiting.resize(num_concurrent_games, false);

    m_sims_target.resize(num_concurrent_games, 0);
    m_is_slow_move.resize(num_concurrent_games, false);

    m_game_states.resize(num_concurrent_games);
    m_game_policies.resize(num_concurrent_games);

    // Pré-allocation du tenseur de batch
    m_batch_input.resize(num_concurrent_games * 119 * 64);

    m_tensor_buffer.resize(119 * 8 * 8);

    m_shared_mcts = std::make_unique<MCTS>(m_evaluator);
    for (int i = 0; i < num_concurrent_games; ++i) {
        reset_game(i);
    }
}

void SelfPlayManager::reset_game(int game_idx) {
    m_boards[game_idx].clear();
    m_boards[game_idx].setStartupPieces();
    m_roots[game_idx] = std::make_unique<MCTSNode>(0.0f);
    m_sims_completed[game_idx] = 0;
    m_game_states[game_idx].clear();
    m_game_policies[game_idx].clear();

    // Premier appel bloquant pour initialiser la racine de la nouvelle partie
    m_shared_mcts->expand_node_single(m_roots[game_idx].get(), m_boards[game_idx]);
    m_shared_mcts->add_dirichlet_noise(m_roots[game_idx].get());
    roll_next_move(game_idx);
}

void SelfPlayManager::execute_gpu_batch() {
    if (m_waiting_leaves.empty()) return;
    int current_batch_size = m_waiting_leaves.size();

    // Inférence
    m_evaluator->evaluate_batch(m_batch_input, m_batch_policies, m_batch_values, current_batch_size);

    for (int i = 0; i < current_batch_size; ++i) {
        int game_idx = m_waiting_game_indices[i];
        int moves_played = m_waiting_moves_played[i];

        float value = m_batch_values[i];
        const float* single_policy = m_batch_policies.data() + (i * 4672);
        m_shared_mcts->expand_and_backup(m_waiting_leaves[i], m_boards[game_idx], single_policy, value);


        // RESTAURATION DE L'ECHIQUIER
        for (int k = 0; k < moves_played; ++k) {
            m_boards[game_idx].undoMove();
        }

        m_sims_completed[game_idx]++;
    }

    for (int i = 0; i < current_batch_size; ++i) {
        m_is_waiting[m_waiting_game_indices[i]] = false;
    }

    m_waiting_leaves.clear();
    m_waiting_game_indices.clear();
    m_waiting_moves_played.clear();
}

void SelfPlayManager::play_best_move(int game_idx) {
    // 1. Calcul des probabilités de visite
    std::vector<float> pi(4672, 0.0f);
    float sum_visits = 0.0f;
    for (const auto& pair : m_roots[game_idx]->m_children) {
        pi[pair.first] = pair.second->m_visit_count;
        sum_visits += pair.second->m_visit_count;
    }
    if (sum_visits > 0.0f) {
        for (float& p : pi) p /= sum_visits;
    }

    // 2. Sélection (Température pour les 30 premiers coups, Argmax ensuite)
    int best_move = -1;
    if (m_boards[game_idx].getMoveHistory().size() < 30) {
        // Sélection proportionnelle (Température = 1)
        std::uniform_real_distribution<float> dis(0.0f, 1.0f);
        float r = dis(m_rng);
        float accum = 0.0f;

        for (int i = 0; i < 4672; ++i) {
            if (pi[i] > 0.0f) {
                accum += pi[i];
                if (r <= accum) {
                    best_move = i;
                    break;
                }
            }
        }
        // Sécurité au cas où l'arrondi flottant pose problème
        if (best_move == -1) best_move = m_roots[game_idx]->m_children.begin()->first;
    }
    else {
        // Argmax pur (Température = 0)
        float max_p = -1.0f;
        for (int i = 0; i < 4672; ++i) {
            if (pi[i] > max_p) { max_p = pi[i]; best_move = i; }
        }
    }

    // 3. Sauvegarde des données pour l'entraînement
    if (m_is_slow_move[game_idx]) {
        std::vector<float> tensor;
        m_boards[game_idx].getAlphaZeroTensor(tensor);
        m_game_states[game_idx].push_back(tensor);
        m_game_policies[game_idx].push_back(pi);
    }

    // 4. On joue le coup sur le vrai échiquier
    m_shared_mcts->apply_move_by_index(m_boards[game_idx], best_move);

    // 5. Détection de fin de partie
    bool game_over = false;
    if (m_boards[game_idx].checkThreefoldRepetition() ||
        m_boards[game_idx].getHalfMoveClock() >= 100 ||
        m_boards[game_idx].checkInsufficientMaterial()) {
        game_over = true;
    }
    else if (!m_boards[game_idx].hasAnyLegalMove()) {
        game_over = true;
    }

    // 6. Si la partie est finie, on ne prépare pas le prochain coup
    if (game_over) {
        m_roots[game_idx].reset();
        m_sims_target[game_idx] = 0;
        m_sims_completed[game_idx] = 0; // Empêche de relancer des sims
        return;
    }

    // 7. On descend la racine de l'arbre (seulement si la partie continue)
    if (m_roots[game_idx]->has_child(best_move)) {
        m_roots[game_idx] = m_roots[game_idx]->extract_child(best_move);
        m_roots[game_idx]->m_parent = nullptr;
    }
    else {
        m_roots[game_idx] = std::make_unique<MCTSNode>(0.0f);
        m_shared_mcts->expand_node_single(m_roots[game_idx].get(), m_boards[game_idx]);
    }

    m_shared_mcts->add_dirichlet_noise(m_roots[game_idx].get());
    roll_next_move(game_idx);
}

void SelfPlayManager::roll_next_move(int game_idx) {
    std::uniform_real_distribution<float> dis(0.0f, 1.0f);
    m_is_slow_move[game_idx] = (dis(m_rng) < m_slow_ratio);
    m_sims_target[game_idx] = m_is_slow_move[game_idx] ? m_slow_sims : m_fast_sims;
    m_sims_completed[game_idx] = 0;
}

std::vector<GameResult> SelfPlayManager::generate_games(int total_games_to_play) {
    int games_completed = 0;
    auto start_time = std::chrono::steady_clock::now();

    while (games_completed < total_games_to_play) {
        bool batch_executed = false;

        for (int i = 0; i < m_num_concurrent_games; ++i) {
            if (games_completed >= total_games_to_play) break;

            // Si la partie attend le GPU, on passe à la suivante
            if (m_is_waiting[i]) continue;

            // Phase de simulation MCTS
            if (m_sims_completed[i] < m_sims_target[i]) {
                int moves_played = 0;
                MCTSNode* leaf = m_shared_mcts->advance_to_leaf(
                    m_roots[i].get(), m_boards[i], 1.4f, moves_played);

                if (leaf != nullptr) {
                    m_waiting_leaves.push_back(leaf);
                    m_waiting_game_indices.push_back(i);
                    m_waiting_moves_played.push_back(moves_played);
                    m_is_waiting[i] = true;

                    m_boards[i].getAlphaZeroTensor(m_tensor_buffer); // Remplit m_tensor_buffer
                    int offset = (m_waiting_leaves.size() - 1) * 119 * 64;
                    std::copy(
                        m_tensor_buffer.begin(), 
                        m_tensor_buffer.end(), 
                        m_batch_input.begin() + offset);

                    // Exécution si le batch est plein
                    if (m_waiting_leaves.size() == m_num_concurrent_games) {
                        execute_gpu_batch();
                        batch_executed = true;
                    }
                }
                else {
                    m_sims_completed[i]++;
                }
            }
            // Fin de la réflexion : on joue le coup
            else {
                play_best_move(i);
                if (m_roots[i] == nullptr) {
                    // play_best_move a détecté une fin de partie
                    GameResult res;
                    res.move_count = m_game_states[i].size();

                    res.flat_states.reserve(res.move_count * 119 * 64);
                    res.flat_policies.reserve(res.move_count * 4672);

                    for (const auto& t : m_game_states[i]) {
                        res.flat_states.insert(res.flat_states.end(), t.begin(), t.end());
                    }
                    for (const auto& p : m_game_policies[i]) {
                        res.flat_policies.insert(res.flat_policies.end(), p.begin(), p.end());
                    }

                    // Détermination du résultat
                    if (m_boards[i].checkThreefoldRepetition() ||
                        m_boards[i].getHalfMoveClock() >= 100 ||
                        m_boards[i].checkInsufficientMaterial()) {
                        res.final_outcome = 0.0f;  // Nulle par règle
                    }
                    else if (m_boards[i].isInCheck()) {
                        // Pas de coup légal + en échec = mat
                        res.final_outcome = (m_boards[i].getTurn() == WHITE) ? -1.0f : 1.0f;
                    }
                    else {
                        res.final_outcome = 0.0f;  // Pat
                    }

                    m_finished_games.push_back(res);
                    games_completed++;

                    // --- PROGRESSION ---
                    if (games_completed % 16 == 0 || games_completed == total_games_to_play) {
                        auto now = std::chrono::steady_clock::now();
                        double elapsed = std::chrono::duration<double>(now - start_time).count();
                        double speed = games_completed / elapsed;
                        double eta = (total_games_to_play - games_completed) / speed;
                        std::cout << "\r  Self-play: " << games_completed << "/" << total_games_to_play
                            << " (" << std::fixed << std::setprecision(1) << speed << " parties/s"
                            << ", ETA: " << (int)(eta / 60) << "m" << (int)((int)eta % 60) << "s)"
                            << std::flush;
                    }

                    if (games_completed < total_games_to_play) {
                        reset_game(i);
                    }
                }

            }
        }

        // Anti-blocage : Si on n'a pas pu remplir le batch, mais que toutes les parties
        // actives sont en attente, on lance quand même l'inférence.
        if (!batch_executed && !m_waiting_leaves.empty()) {
            bool all_blocked = true;
            for (int i = 0; i < m_num_concurrent_games; ++i) {
                if (m_sims_completed[i] < m_sims_target[i] && !m_is_waiting[i]) {
                    all_blocked = false;
                    break;
                }
            }
            if (all_blocked) execute_gpu_batch();
        }
    }

    std::cout << std::endl;
    return m_finished_games;
}
#include "selfplay_manager.hpp"
#include <iostream>
#include <random>

SelfPlayManager::SelfPlayManager(ONNXEvaluator* evaluator, int num_concurrent_games, int simulations_per_move)
    : m_evaluator(evaluator),
    m_num_concurrent_games(num_concurrent_games),
    m_simulations_per_move(simulations_per_move)
{
    m_boards.resize(num_concurrent_games);
    m_roots.resize(num_concurrent_games);
    m_sims_completed.resize(num_concurrent_games, 0);

    m_game_states.resize(num_concurrent_games);
    m_game_policies.resize(num_concurrent_games);

    // Pré-allocation du tenseur de batch
    m_batch_input.resize(num_concurrent_games * 119 * 64);

    for (int i = 0; i < num_concurrent_games; ++i) {
        m_mcts_instances.push_back(std::make_unique<MCTS>(m_evaluator));
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
    float dummy_val;
    m_mcts_instances[game_idx]->expand_node_single(m_roots[game_idx].get(), m_boards[game_idx]);
    m_mcts_instances[game_idx]->add_dirichlet_noise(m_roots[game_idx].get());
}

void SelfPlayManager::execute_gpu_batch() {
    if (m_waiting_leaves.empty()) return;
    int current_batch_size = m_waiting_leaves.size();

    // Inférence
    m_evaluator->evaluate_batch(m_batch_input, m_batch_policies, m_batch_values, current_batch_size);

    for (int i = 0; i < current_batch_size; ++i) {
        int game_idx = m_waiting_game_indices[i];
        int moves_played = m_waiting_moves_played[i];

        auto policy_start = m_batch_policies.begin() + (i * 4672);
        std::vector<float> single_policy(policy_start, policy_start + 4672);
        float value = m_batch_values[i];

        // Rétropropagation
        m_mcts_instances[game_idx]->expand_and_backup(m_waiting_leaves[i], m_boards[game_idx], single_policy, value);

        // RESTAURATION DE L'ECHIQUIER
        for (int k = 0; k < moves_played; ++k) {
            m_boards[game_idx].undoMove();
        }

        m_sims_completed[game_idx]++;
    }

    m_waiting_leaves.clear();
    m_waiting_game_indices.clear();
    m_waiting_moves_played.clear();
}

void SelfPlayManager::play_best_move(int game_idx) {
    // 1. Calcul des probabilités de visite
    std::vector<float> pi(4672, 0.0f);
    float sum_visits = 0.0f;
    for (const auto& pair : m_roots[game_idx]->children) {
        pi[pair.first] = pair.second->visit_count;
        sum_visits += pair.second->visit_count;
    }
    if (sum_visits > 0.0f) {
        for (float& p : pi) p /= sum_visits;
    }

    // 2. Sélection (Température pour les 30 premiers coups, Argmax ensuite)
    int best_move = -1;
    if (m_boards[game_idx].getMoveHistory().size() < 30) {
        // Sélection proportionnelle (Température = 1)
        std::mt19937 gen(std::random_device{}());
        std::uniform_real_distribution<float> dis(0.0f, 1.0f);
        float r = dis(gen);
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
        if (best_move == -1) best_move = m_roots[game_idx]->children.begin()->first;
    }
    else {
        // Argmax pur (Température = 0)
        float max_p = -1.0f;
        for (int i = 0; i < 4672; ++i) {
            if (pi[i] > max_p) { max_p = pi[i]; best_move = i; }
        }
    }

    // 3. Sauvegarde des données pour l'entraînement
    std::vector<float> tensor;
    m_boards[game_idx].getAlphaZeroTensor(tensor);
    m_game_states[game_idx].push_back(tensor);
    m_game_policies[game_idx].push_back(pi);

    // 4. On joue le coup sur le vrai échiquier
    m_mcts_instances[game_idx]->apply_move_by_index(m_boards[game_idx], best_move);

    // 5. On descend la racine de l'arbre
    if (m_roots[game_idx]->children.count(best_move)) {
        m_roots[game_idx] = std::move(m_roots[game_idx]->children[best_move]);
        m_roots[game_idx]->parent = nullptr;
    }
    else {
        m_roots[game_idx] = std::make_unique<MCTSNode>(0.0f);
        m_mcts_instances[game_idx]->expand_node_single(m_roots[game_idx].get(), m_boards[game_idx]);
    }

    m_mcts_instances[game_idx]->add_dirichlet_noise(m_roots[game_idx].get());
    m_sims_completed[game_idx] = 0;
}

std::vector<GameResult> SelfPlayManager::generate_games(int total_games_to_play) {
    std::cout << "Debut generate_games" << std::endl;
    int games_completed = 0;

    while (games_completed < total_games_to_play) {
        bool batch_executed = false;

        for (int i = 0; i < m_num_concurrent_games; ++i) {
            if (games_completed >= total_games_to_play) break;

            // Si la partie attend le GPU, on passe à la suivante
            if (std::find(
                m_waiting_game_indices.begin(), m_waiting_game_indices.end(), i
            ) != m_waiting_game_indices.end()) {
                continue;
            }

            // Phase de simulation MCTS
            if (m_sims_completed[i] < m_simulations_per_move) {
                int moves_played = 0;
                MCTSNode* leaf = m_mcts_instances[i]->advance_to_leaf(m_roots[i].get(), m_boards[i], 1.4f, moves_played);

                if (leaf != nullptr) {
                    m_waiting_leaves.push_back(leaf);
                    m_waiting_game_indices.push_back(i);
                    m_waiting_moves_played.push_back(moves_played);

                    std::vector<float> tensor;
                    m_boards[i].getAlphaZeroTensor(tensor);
                    int offset = (m_waiting_leaves.size() - 1) * 119 * 64;
                    std::copy(tensor.begin(), tensor.end(), m_batch_input.begin() + offset);

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

                // Vérification de fin de partie
                if (m_boards[i].getGameState() != ONGOING || m_boards[i].getHalfMoveClock() >= 100) {
                    GameResult res;
                    res.state_tensors = m_game_states[i];
                    res.policies = m_game_policies[i];

                    if (m_boards[i].checkThreefoldRepetition() || 
                        m_boards[i].getHalfMoveClock() >= 100 || 
                        m_boards[i].checkInsufficientMaterial()) {
                        res.final_outcome = 0.0f;
                    }
                    else {
                        res.final_outcome = (m_boards[i].getTurn() == WHITE) ? -1.0f : 1.0f;
                    }

                    m_finished_games.push_back(res);
                    games_completed++;

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
                if (m_sims_completed[i] < m_simulations_per_move &&
                    std::find(
                        m_waiting_game_indices.begin(), m_waiting_game_indices.end(), i
                    ) == m_waiting_game_indices.end()) {
                    all_blocked = false;
                    break;
                }
            }
            if (all_blocked) execute_gpu_batch();
        }
    }

    return m_finished_games;
}
#include <iostream>
#include <random>
#include <chrono>
#include <iomanip>
#include <omp.h>
#include <algorithm>
#include "selfplay_manager.hpp"
#include <piece.hpp>

SelfPlayManager::SelfPlayManager(
    ONNXEvaluator* evaluator,
    int num_concurrent_games,
    int slow_sims, int fast_sims, float slow_ratio,
    size_t tt_size)
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

    m_batch_input.resize(num_concurrent_games * 119 * 64);

    m_shared_mcts = std::make_unique<MCTS>(m_evaluator, tt_size);
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

    m_shared_mcts->expand_node_single(m_roots[game_idx].get(), m_boards[game_idx]);
    roll_next_move(game_idx);
    m_shared_mcts->add_dirichlet_noise(m_roots[game_idx].get());
}

void SelfPlayManager::execute_gpu_batch() {
    if (m_waiting_leaves.empty()) return;
    int current_batch_size = m_waiting_leaves.size();

    m_evaluator->evaluate_batch(m_batch_input, m_batch_policies, m_batch_values, current_batch_size);

    for (int i = 0; i < current_batch_size; ++i) {
        int game_idx = m_waiting_game_indices[i];
        int moves_played = m_waiting_moves_played[i];

        float value = m_batch_values[i];
        const float* single_policy = m_batch_policies.data() + (i * 4672);
        m_shared_mcts->expand_and_backup(m_waiting_leaves[i], m_boards[game_idx], single_policy, value);

        if (m_waiting_leaves[i] == m_roots[game_idx].get()) {
            m_shared_mcts->add_dirichlet_noise(m_roots[game_idx].get());
        }

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
    for (const auto& pair : m_roots[game_idx]->children) {
        pi[pair.first] = pair.second->visit_count;
        sum_visits += pair.second->visit_count;
    }
    if (sum_visits > 0.0f) {
        for (float& p : pi) p /= sum_visits;
    }

    // 2. Sélection
    int best_move = -1;

    // Sélection proportionnelle (30 premiers demi-coups)
    if (m_boards[game_idx].getMoveHistory().size() < 30) {
        std::uniform_real_distribution<float> dis(0.0f, 1.0f);
        float r = dis(m_rng);
        float accum = 0.0f;

        for (const auto& pair : m_roots[game_idx]->children) {
            float p = pi[pair.first];
            if (p > 0.0f) {
                accum += p;
                if (r <= accum) {
                    best_move = pair.first;
                    break;
                }
            }
        }
        if (best_move == -1) best_move = m_roots[game_idx]->children.front().first;
    }
    else { // argmax
        float max_p = -1.0f;
        for (const auto& pair : m_roots[game_idx]->children) {
            float p = pi[pair.first];
            if (p > max_p) { max_p = p; best_move = pair.first; }
        }
    }

    // 3. Sauvegarde (slow moves uniquement)
    if (m_is_slow_move[game_idx]) {
        std::vector<float> tensor;
        m_boards[game_idx].getAlphaZeroTensor(tensor);
        m_game_states[game_idx].push_back(std::move(tensor));
        m_game_policies[game_idx].push_back(std::move(pi));
    }

    // 4. Jouer le coup
    m_shared_mcts->apply_move_by_index(m_boards[game_idx], best_move);

    // 5. Détection fin de partie
    bool game_over = false;
    if (m_boards[game_idx].checkThreefoldRepetition() ||
        m_boards[game_idx].getHalfMoveClock() >= 100 ||
        m_boards[game_idx].checkInsufficientMaterial()) {
        game_over = true;
    }
    else if (!m_boards[game_idx].hasAnyLegalMove()) {
        game_over = true;
    }

    if (game_over) {
        m_roots[game_idx].reset();
        m_sims_target[game_idx] = 0;
        m_sims_completed[game_idx] = 0;
        return;
    }

    // 6. Descente de racine
    if (m_roots[game_idx]->has_child(best_move)) {
        m_roots[game_idx] = m_roots[game_idx]->extract_child(best_move);
        m_roots[game_idx]->parent = nullptr;
    }
    else {
        m_roots[game_idx] = std::make_unique<MCTSNode>(0.0f);
        m_shared_mcts->expand_node_single(m_roots[game_idx].get(), m_boards[game_idx]);
    }

    roll_next_move(game_idx);

    // Si la racine réutilisée avait déjà des enfants (rare mais possible), 
    // on applique le bruit de suite. Sinon, ça sera fait dans execute_gpu_batch.
    if (!m_roots[game_idx]->children.empty()) {
        m_shared_mcts->add_dirichlet_noise(m_roots[game_idx].get());
    }
}

void SelfPlayManager::roll_next_move(int game_idx) {
    // logique slow/fast moves pour accélérer la production de games.
    // en général : 1/4 des coups sont slow
    // quand 6 pièces ou moins : slow move + souvent
    // ça permet d'accélérer la compréhension des finales
    // (training supervisé sur des parties de GM :
    // peu d'exemples de mats)

    std::uniform_real_distribution<float> dis(0.0f, 1.0f);
    float random_val = dis(m_rng);

    int piece_count = m_boards[game_idx].getNumberOfOccupiedSquares();

    float effective_slow_ratio = (piece_count <= 6) ? 
        std::max(m_slow_ratio, 0.60f) : // 60% (au moins) si finale
        m_slow_ratio; // ratio normal sinon

    m_is_slow_move[game_idx] = (random_val < effective_slow_ratio);

    m_sims_target[game_idx] = m_is_slow_move[game_idx] ? m_slow_sims : m_fast_sims;
    m_sims_completed[game_idx] = 0;
}

std::vector<GameResult> SelfPlayManager::generate_games(int total_games_to_play) {
    int games_completed = 0;
    auto start_time = std::chrono::steady_clock::now();

    // Initialisation OpenMP
    const int num_threads = std::min(8, m_num_concurrent_games);
    std::vector<ThreadLocalBuffer> thread_buffers(num_threads);

    for (auto& buf : thread_buffers) {
        buf.tensors.resize(m_num_concurrent_games * 119 * 64);
        buf.tensor_scratch.resize(119 * 64);
    }

    while (games_completed < total_games_to_play) {

        // ==========================================================
        // PHASE 1 : Séquentiel — Jouer les coups, gérer les fins
        // ==========================================================
        for (int i = 0; i < m_num_concurrent_games; ++i) {
            if (games_completed >= total_games_to_play) break;
            if (m_is_waiting[i]) continue;

            if (m_sims_completed[i] >= m_sims_target[i] && m_sims_target[i] > 0) {
                play_best_move(i);

                if (m_roots[i] != nullptr && m_boards[i].getMoveHistory().size() >= 200) {
                    // on force la nulle : partie trop longue
                    m_roots[i].reset();
                    m_sims_target[i] = 0;
                    m_sims_completed[i] = 0;
                }

                if (m_roots[i] == nullptr) {
                    GameResult res;
                    res.move_count = m_game_states[i].size();
                    res.total_real_moves = m_boards[i].getMoveHistory().size();
                    res.flat_states.reserve(res.move_count * 119 * 64);
                    res.flat_policies.reserve(res.move_count * 4672);

                    for (const auto& t : m_game_states[i])
                        res.flat_states.insert(res.flat_states.end(), t.begin(), t.end());
                    for (const auto& p : m_game_policies[i])
                        res.flat_policies.insert(res.flat_policies.end(), p.begin(), p.end());

                    if (!m_boards[i].hasAnyLegalMove() && m_boards[i].isInCheck()) {
                        res.final_outcome = (m_boards[i].getTurn() == WHITE) ? -1.0f : 1.0f;
                        res.end_reason = 0; // Checkmate
                    }
                    else if (m_boards[i].getMoveHistory().size() >= 200) {
                        res.final_outcome = 0.0f;
                        res.end_reason = 5; // Max Moves (200 coups)
                    }
                    else if (m_boards[i].checkThreefoldRepetition()) {
                        res.final_outcome = 0.0f;
                        res.end_reason = 2; // Répétition
                    }
                    else if (m_boards[i].getHalfMoveClock() >= 100) {
                        res.final_outcome = 0.0f;
                        res.end_reason = 3; // Règle des 50 coups
                    }
                    else if (m_boards[i].checkInsufficientMaterial()) {
                        res.final_outcome = 0.0f;
                        res.end_reason = 4; // Matériel insuffisant
                    }
                    else {
                        res.final_outcome = 0.0f;
                        res.end_reason = 1; // Pat (Stalemate)
                    }

                    m_finished_games.push_back(res);
                    games_completed++;

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

                    if (games_completed < total_games_to_play)
                        reset_game(i);
                }
            }
        }

        // ==========================================================
        // PHASE 2 : Parallèle (OpenMP) — Traversée MCTS
        // ==========================================================
        for (auto& buf : thread_buffers) buf.clear();

#pragma omp parallel num_threads(num_threads)
        {
            int tid = omp_get_thread_num();
            auto& buf = thread_buffers[tid];

#pragma omp for schedule(dynamic, 4)
            for (int i = 0; i < m_num_concurrent_games; ++i) {
                if (m_is_waiting[i] || m_sims_completed[i] >= m_sims_target[i]) continue;

                int moves_played = 0;
                MCTSNode* leaf = m_shared_mcts->advance_to_leaf(
                    m_roots[i].get(), m_boards[i], 1.4f, moves_played);

                if (leaf != nullptr) {
                    buf.leaves.push_back(leaf);
                    buf.game_indices.push_back(i);
                    buf.moves_played.push_back(moves_played);

                    m_boards[i].getAlphaZeroTensor(buf.tensor_scratch);
                    int offset = (buf.leaves.size() - 1) * 119 * 64;
                    std::copy(buf.tensor_scratch.begin(),
                        buf.tensor_scratch.end(),
                        buf.tensors.begin() + offset);

                    m_is_waiting[i] = true;
                }
                else {
                    m_sims_completed[i]++;
                }
            }
        }

        // ==========================================================
        // PHASE 3 : Séquentiel — Fusion et batch GPU
        // ==========================================================
        for (const auto& buf : thread_buffers) {
            for (size_t j = 0; j < buf.leaves.size(); ++j) {
                if ((int)m_waiting_leaves.size() >= m_num_concurrent_games) break;

                m_waiting_leaves.push_back(buf.leaves[j]);
                m_waiting_game_indices.push_back(buf.game_indices[j]);
                m_waiting_moves_played.push_back(buf.moves_played[j]);

                int batch_offset = m_waiting_leaves.size() - 1;
                std::copy(buf.tensors.begin() + j * 119 * 64,
                    buf.tensors.begin() + (j + 1) * 119 * 64,
                    m_batch_input.begin() + batch_offset * 119 * 64);
            }
        }

        // Exécution : batch plein OU tout le monde est bloqué
        bool batch_full = ((int)m_waiting_leaves.size() >= m_num_concurrent_games);

        bool all_blocked = true;
        for (int i = 0; i < m_num_concurrent_games; ++i) {
            if (m_sims_completed[i] < m_sims_target[i] && !m_is_waiting[i]) {
                all_blocked = false;
                break;
            }
        }

        if ((batch_full || all_blocked) && !m_waiting_leaves.empty()) {
            execute_gpu_batch();
        }
    }

    std::cout << std::endl;
    return m_finished_games;
}

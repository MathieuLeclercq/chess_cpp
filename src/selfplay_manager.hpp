#pragma once
#include <vector>
#include <memory>
#include <random>
#include <omp.h>
#include "chessboard.hpp"
#include "mcts.hpp"
#include "onnx_evaluator.hpp"


struct GameResult {
    std::vector<float> flat_states; // Taille : [NbCoups * 119 * 64]
    std::vector<float> flat_policies; // Taille : [NbCoups * 4672]
    float final_outcome;
    int move_count; // Pour savoir comment découper le vecteur plat
};

struct ThreadLocalBuffer {
    std::vector<MCTSNode*> leaves;
    std::vector<int> game_indices;
    std::vector<int> moves_played;
    std::vector<float> tensors;
    std::vector<float> tensor_scratch;

    void clear() {
        leaves.clear();
        game_indices.clear();
        moves_played.clear();
    }
};

class SelfPlayManager {
private:
    int m_num_concurrent_games;
    int m_slow_sims;
    int m_fast_sims;
    float m_slow_ratio;
    std::vector<int> m_sims_target;  // sims à faire pour le coup en cours
    std::vector<bool> m_is_slow_move;

    ONNXEvaluator* m_evaluator;

    // L'état complet des parties en cours
    std::vector<Chessboard> m_boards;
    std::vector<std::unique_ptr<MCTSNode>> m_roots;
    std::unique_ptr<MCTS> m_shared_mcts;

    // Suivi de l'avancement de chaque arbre (combien de simulations terminées pour ce coup)
    std::vector<int> m_sims_completed;

    // Données accumulées pour l'entraînement final
    std::vector<GameResult> m_finished_games;
    std::vector<std::vector<std::vector<float>>> m_game_states;
    std::vector<std::vector<std::vector<float>>> m_game_policies;

    // Buffers pour le GPU
    std::vector<float> m_batch_input;
    std::vector<float> m_batch_policies;
    std::vector<float> m_batch_values;

    // Suivi de l'état de la boucle asynchrone
    std::vector<MCTSNode*> m_waiting_leaves;
    std::vector<int> m_waiting_game_indices;
    std::vector<int> m_waiting_moves_played;
    std::vector<bool> m_is_waiting;

    std::vector<float> m_tensor_buffer;

    std::mt19937 m_rng{ std::random_device{}() };


public:
    SelfPlayManager(ONNXEvaluator* evaluator, int num_concurrent_games, 
                    int slow_sims, int fast_sims, float slow_ratio);
    std::vector<GameResult> generate_games(int total_games_to_play);

private:
    void reset_game(int game_idx);
    void play_best_move(int game_idx);
    void roll_next_move(int game_idx);
    void execute_gpu_batch();
};

#pragma once

#include "chessboard.hpp"
#include <onnxruntime_cxx_api.h>
#include <vector>
#include <unordered_map>
#include <memory>
#include <utility>
#include <cstdint>
#include <mutex>

#include "onnx_evaluator.hpp"

struct MCTSNode {
    int visit_count;
    int move_idx;
    bool is_terminal;
    float prior;
    float total_value;

    MCTSNode* parent;
    std::unordered_map<int, std::unique_ptr<MCTSNode>> children;

    MCTSNode(float prior, int move_idx = -1, MCTSNode* parent = nullptr);
    float q_value() const;
    float ucb_score(float exploration_factor, float parent_q, float fpu_reduction) const;
};

struct TTEntry {
    uint64_t hash = 0;
    float value = 0.0f;
    std::vector<std::pair<int, float>> legal_policy;
};

struct MoveStats {
    int move_idx;
    int visits;
    float q_value;
    float prior;
};

class MCTS {
private:
    Ort::AllocatorWithDefaultOptions allocator;
    std::vector<TTEntry> transposition_table;
    static constexpr size_t TT_SIZE = 2097143;
    std::vector<float> m_eval_tensor;
    std::vector<float> m_eval_policy;
    std::unique_ptr<MCTSNode> m_analysis_root;
    std::mutex m_mutex;
    ONNXEvaluator* m_evaluator;

public:
    MCTS(ONNXEvaluator* evaluator);

    void step_analysis(Chessboard& board, int num_simulations, float c_puct);
    void reset_analysis();
    void update_root(int move_idx);
    float get_root_q() const;
    std::vector<MoveStats> get_analysis_results() const;
    std::vector<float> mcts_search(Chessboard& board, int num_simulations, float c_puct, bool add_dirichlet);
    float expand_node_single(MCTSNode* node, Chessboard& board);
    bool apply_move_by_index(Chessboard& board, int idx);
    void add_dirichlet_noise(MCTSNode* root);

    // recherche mcts asynchrone
    MCTSNode* advance_to_leaf(MCTSNode* root, Chessboard& board, float c_puct, int& moves_played);
    void expand_and_backup(MCTSNode* leaf_node, Chessboard& board, const float* policy, float value);

private:
    void backup(MCTSNode* node, float value);
    std::pair<MCTSNode*, int> select_leaf(MCTSNode* root, Chessboard& board, float c_puct, bool& aborted);

};
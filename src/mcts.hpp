#pragma once

#include "chessboard.hpp"
#include <onnxruntime_cxx_api.h>
#include <vector>
#include <unordered_map>
#include <memory>
#include <utility>
#include <cstdint>

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


struct TranspositionEntry {
    std::vector<std::pair<int, float>> legal_policy; // Ne stocke que {index_du_coup, probabilité}
    float value;
};

struct MoveStats {
    int move_idx;
    int visits;
    float q_value;
    float prior;
};

class MCTS {
private:
    Ort::Env env;
    Ort::SessionOptions session_options;
    std::unique_ptr<Ort::Session> session;
    Ort::AllocatorWithDefaultOptions allocator;
    std::unordered_map<uint64_t, TranspositionEntry> transposition_table;

    std::vector<float> m_eval_tensor;
    std::vector<float> m_eval_policy;

public:
    MCTS(const std::string& model_path);

    void step_analysis(Chessboard& board, int num_simulations, float c_puct);
    void reset_analysis();
    float get_root_q() const;
    std::vector<MoveStats> get_analysis_results() const;
    std::vector<float> mcts_search(Chessboard& board, int num_simulations, float c_puct, bool add_dirichlet);

private:
    void backup(MCTSNode* node, float value);
    void evaluate_onnx(const std::vector<float>& input_tensor, std::vector<float>& policy, float& value);
    bool apply_move_by_index(Chessboard& board, int idx);
    float expand_node_single(MCTSNode* node, Chessboard& board);
    std::pair<MCTSNode*, int> select_leaf(MCTSNode* root, Chessboard& board, float c_puct, bool& aborted);
    std::unique_ptr<MCTSNode> m_analysis_root;

};
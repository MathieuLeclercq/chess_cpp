#pragma once

#include "chessboard.hpp"
#include <onnxruntime_cxx_api.h>
#include <vector>
#include <unordered_map>
#include <memory>
#include <cmath>
#include <random>

struct MCTSNode {
    int move_idx;
    MCTSNode* parent;
    std::unordered_map<int, std::unique_ptr<MCTSNode>> children;
    float prior;
    int visit_count;
    float total_value;
    bool is_terminal;

    MCTSNode(float prior, int move_idx = -1, MCTSNode* parent = nullptr)
        : prior(prior), move_idx(move_idx), parent(parent),
        visit_count(0), total_value(0.0f), is_terminal(false) {
    }

    float q_value() const {
        if (visit_count == 0) return 0.0f;
        return total_value / visit_count;
    }

    float ucb_score(int parent_visits, float c_puct = 1.4f) const {
        float u = c_puct * prior * std::sqrt(static_cast<float>(parent_visits)) / (1.0f + visit_count);
        return -q_value() + u;
    }
};

class MCTS {
private:
    Ort::Env env;
    Ort::SessionOptions session_options;
    std::unique_ptr<Ort::Session> session;
    Ort::AllocatorWithDefaultOptions allocator;

public:
    MCTS(const std::string& model_path);

    // Retourne le vecteur de probabilités Pi de taille 4672
    std::vector<float> mcts_search(Chessboard& board, int num_simulations, float c_puct, bool add_dirichlet);

private:
    float expand_node_single(MCTSNode* node, Chessboard& board);
    std::pair<MCTSNode*, int> select_leaf(MCTSNode* root, Chessboard& board, float c_puct, bool& aborted);
    void backup(MCTSNode* node, float value);
    void evaluate_onnx(const std::vector<float>& input_tensor, std::vector<float>& policy, float& value);
    bool apply_move_by_index(Chessboard& board, int idx);
};
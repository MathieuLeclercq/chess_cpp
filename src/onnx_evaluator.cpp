#include "onnx_evaluator.hpp"
#include <algorithm>
#include <cmath>

ONNXEvaluator::ONNXEvaluator(const std::string& model_path)
    : env(ORT_LOGGING_LEVEL_WARNING, "AlphaZeroMCTS")
{
    session_options.SetIntraOpNumThreads(1);
    session_options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);

    std::wstring w_model_path(model_path.begin(), model_path.end());
    session = std::make_unique<Ort::Session>(env, w_model_path.c_str(), session_options);
}

void ONNXEvaluator::evaluate(const std::vector<float>& input_tensor, std::vector<float>& policy, float& value) {
    static const std::array<int64_t, 4> input_shape = { 1, 119, 8, 8 };
    static const char* input_names[] = { "input" };
    static const char* output_names[] = { "policy", "value" };
    static auto memory_info = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);

    Ort::Value input_ort = Ort::Value::CreateTensor<float>(
        memory_info, const_cast<float*>(input_tensor.data()), input_tensor.size(),
        input_shape.data(), input_shape.size()
    );

    auto output_tensors = session->Run(Ort::RunOptions{ nullptr }, input_names, &input_ort, 1, output_names, 2);

    const float* policy_data = output_tensors[0].GetTensorData<float>();
    const float* value_data = output_tensors[1].GetTensorData<float>();

    value = value_data[0];
    policy.resize(4672);

    float max_logit = *std::max_element(policy_data, policy_data + 4672);
    float sum_exp = 0.0f;

    for (int i = 0; i < 4672; ++i) {
        float e = std::exp(policy_data[i] - max_logit);
        policy[i] = e;
        sum_exp += e;
    }

    float inv_sum = 1.0f / sum_exp;
    for (int i = 0; i < 4672; ++i) {
        policy[i] *= inv_sum;
    }
}
#pragma once
#include <string>
#include <vector>
#include <memory>
#include <onnxruntime_cxx_api.h>

class ONNXEvaluator {
private:
    Ort::Env env;
    Ort::SessionOptions session_options;
    std::unique_ptr<Ort::Session> session;

public:
    ONNXEvaluator(const std::string& model_path);

    void evaluate(const std::vector<float>& input_tensor, std::vector<float>& policy, float& value);
};
import torch
from model import ChessNet

model = ChessNet(num_res_blocks=10, num_filters=128)
checkpoint = torch.load("checkpoints/2026_04_12_19h17_iter34_unsupervised.pt", map_location="cpu", weights_only=True)
model.load_state_dict(checkpoint["model_state_dict"])
model.eval()

dummy_input = torch.randn(1, 119, 8, 8) # La taille initiale n'a plus d'importance

# Export AVEC axes dynamiques (La clé de la flexibilité)
torch.onnx.export(
    model,
    dummy_input,
    "checkpoints/model_dynamic.onnx", # Nouveau nom
    input_names=["input"],
    output_names=["policy", "value"],
    dynamic_axes={
        "input": {0: "batch_size"},
        "policy": {0: "batch_size"},
        "value": {0: "batch_size"}
    }
)
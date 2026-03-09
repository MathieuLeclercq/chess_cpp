import torch
from lib import load_model


def export_to_onnx(checkpoint_path, output_path="checkpoints/model.onnx"):
    # Chargement du modèle sur CPU
    device = torch.device("cpu")
    model = load_model(checkpoint_path, num_res_blocks=10, num_filters=128, device=device)
    model.eval()

    # Création d'un tenseur factice (batch_size=1, 119 channels, 8x8)
    dummy_input = torch.randn(1, 119, 8, 8, device=device)

    # Export avec opset 14 (standard stable)
    torch.onnx.export(
        model,
        dummy_input,
        output_path,
        export_params=True,
        opset_version=14,
        do_constant_folding=True,
        input_names=['input'],
        output_names=['policy', 'value'],
        dynamic_axes={
            'input': {0: 'batch_size'},
            'policy': {0: 'batch_size'},
            'value': {0: 'batch_size'}
        }
    )
    print(f"Modèle exporté avec succès vers : {output_path}")


if __name__ == "__main__":
    export_to_onnx("checkpoints/2026_03_09_14h42_multi_iter2.pt")

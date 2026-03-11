import torch
import os
from model import ChessNet


def transfer_weights(old_ckpt_path, new_ckpt_path):
    # Désactivation de l'avertissement de sécurité pour les anciens ckpt
    os.environ["TORCH_SKIP_WEIGHTS_ONLY_WARNING"] = "1"

    print(f"Chargement de l'ancien checkpoint : {old_ckpt_path}")
    old_ckpt = torch.load(old_ckpt_path, map_location='cpu', weights_only=False)

    # Extraction du dictionnaire de poids
    if 'state_dict' in old_ckpt:
        # Checkpoint provenant de PyTorch Lightning
        raw_state_dict = old_ckpt['state_dict']
        # Suppression du préfixe 'model.' ajouté par Lightning
        old_state_dict = {k.replace('model.', ''): v for k, v in raw_state_dict.items()}
    elif 'model_state_dict' in old_ckpt:
        # Checkpoint standard
        old_state_dict = old_ckpt['model_state_dict']
    else:
        # Dictionnaire brut
        old_state_dict = old_ckpt

    print("Initialisation du nouveau modèle...")
    new_model = ChessNet(num_res_blocks=10, num_filters=128)
    new_state_dict = new_model.state_dict()

    transferred = 0
    ignored = 0

    for name, param in old_state_dict.items():
        if name in new_state_dict:
            if param.shape == new_state_dict[name].shape:
                new_state_dict[name].copy_(param)
                transferred += 1
            else:
                ignored += 1
                print(
                    f"Ignoré (dimension modifiée) : {name} | {param.shape} -> {new_state_dict[name].shape}")
        else:
            ignored += 1
            if hasattr(param, 'shape'):
                print(f"Ignoré (supprimé) : {name} | shape: {param.shape}")
            else:
                print(f"Ignoré (métadonnée non-tenseur) : {name}")

    new_model.load_state_dict(new_state_dict)

    # Sauvegarde au format standard .pt
    new_ckpt = {
        'model_state_dict': new_model.state_dict(),
        'iteration': 0,
        'global_step': 0
    }

    torch.save(new_ckpt, new_ckpt_path)
    print(f"\nTransfert terminé : {transferred} tenseurs copiés, {ignored} ignorés.")
    print(f"Nouveau modèle sauvegardé sous : {new_ckpt_path}")


if __name__ == '__main__':
    OLD_PATH = "checkpoints/supervised_best_03_07.ckpt"
    NEW_PATH = "checkpoints/supervised_best_03_07_V2_fixed.pt"
    transfer_weights(OLD_PATH, NEW_PATH)
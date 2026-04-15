import os
import numpy as np
from datetime import datetime


def migrate_old_buffer(old_filepath, new_folder, chunk_size=50000):
    if not os.path.exists(old_filepath):
        print(f"Erreur : Ancien buffer introuvable à {old_filepath}")
        return

    if not os.path.exists(new_folder):
        os.makedirs(new_folder)

    print(f"Chargement de l'ancien buffer ({old_filepath})...")
    print("La RAM va monter une dernière fois pendant cette opération.")

    # Chargement brut via NumPy (plus rapide que ta boucle avec liste de tuples)
    data = np.load(old_filepath)
    states = data['states']
    policies = data['policies']
    values = data['values']

    total_size = len(states)
    print(f"{total_size} positions trouvées. Début du sharding...")

    # On fige le timestamp pour tout le lot de migration
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for i in range(0, total_size, chunk_size):
        end_idx = min(i + chunk_size, total_size)
        actual_chunk_size = end_idx - i

        chunk_states = states[i:end_idx]
        chunk_policies = policies[i:end_idx]
        chunk_values = values[i:end_idx]

        # On ajoute un index (ex: 000, 001, 002) pour garantir que Python
        # les triera dans l'ordre exact de création, même s'ils ont la même seconde
        chunk_idx = i // chunk_size
        filename = f"shard_{timestamp}_{chunk_idx:03d}_{actual_chunk_size}.npz"
        filepath = os.path.join(new_folder, filename)

        np.savez_compressed(filepath, states=chunk_states, policies=chunk_policies,
                            values=chunk_values)
        print(f"  -> Sauvegardé : {filename} ({actual_chunk_size} positions)")

    print("\nMigration terminée ! Tu peux maintenant supprimer l'ancien replay_buffer.npz.")


if __name__ == "__main__":
    old_file = "checkpoints/replay_buffer.npz"
    new_dir = "replay_buffer"

    migrate_old_buffer(old_file, new_dir)

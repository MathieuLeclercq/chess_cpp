import sys
import time
import os
import gc
import threading
import torch
sys.path.append("./python_src")
import chess_engine

# Configuration
MODEL_PATH = r"C:\Users\M47h1\Documents\chess_cpp\python_src\checkpoints\model_dynamic.onnx"
SAVE_DIR = "selfplay_data"
os.makedirs(SAVE_DIR, exist_ok=True)


def save_chunk(games, chunk_id):
    """Sauvegarde un bloc de parties sur le disque."""
    filename = os.path.join(SAVE_DIR, f"batch_{chunk_id}_{int(time.time())}.pth")

    data_to_save = []
    for g in games:
        data_to_save.append({
            'states': g.state_tensors,
            'policies': g.policies,
            'outcome': g.final_outcome
        })

    torch.save(data_to_save, filename)
    print(f"  -> Sauvegardé : {filename}")


def run_with_interrupt(fn, *args):
    """Lance fn(*args) dans un thread séparé pour que Ctrl+C reste réactif."""
    result = [None]
    exc = [None]

    def target():
        try:
            result[0] = fn(*args)
        except Exception as e:
            exc[0] = e

    t = threading.Thread(target=target)
    t.start()

    try:
        while t.is_alive():
            t.join(timeout=0.5)
    except KeyboardInterrupt:
        print("\n[Interruption détectée] Le chunk C++ en cours va se terminer...")
        raise

    if exc[0]:
        raise exc[0]
    return result[0]


def main():
    print("Chargement du modèle sur GPU...")
    evaluator = chess_engine.ONNXEvaluator(MODEL_PATH, True)

    # --- PARAMÈTRES D'OPTIMISATION ---
    CONCURRENT_GAMES = 8
    SIMS_PER_MOVE = 200
    GAMES_PER_CHUNK = 8
    TOTAL_GOAL = 32
    # ----------------------------------

    print(f"\nObjectif : {TOTAL_GOAL} parties.")
    print(f"Batch GPU (Largeur) : {CONCURRENT_GAMES}")
    print(f"Chunk Size (Fréquence de vidage RAM) : {GAMES_PER_CHUNK}")

    total_generated = 0
    chunk_count = 0
    start_global = time.time()

    try:
        while total_generated < TOTAL_GOAL:
            chunk_count += 1
            print(f"\n[Chunk {chunk_count}] Génération en cours...")

            start_chunk = time.time()

            games = run_with_interrupt(
                chess_engine.generate_self_play_games,
                evaluator,
                CONCURRENT_GAMES,
                SIMS_PER_MOVE,
                GAMES_PER_CHUNK
            )

            duration_chunk = time.time() - start_chunk
            num_games = len(games)
            total_generated += num_games

            save_chunk(games, chunk_count)
            vitesse = num_games / duration_chunk

            del games
            gc.collect()

            print(f"Chunk terminé en {duration_chunk:.1f}s ({vitesse:.2f} parties/s)")
            print(f"Progression totale : {total_generated}/{TOTAL_GOAL}")

    except KeyboardInterrupt:
        print("\n[Interruption] Arrêt propre.")

    end_global = time.time()
    elapsed = end_global - start_global
    print(f"\n=== SESSION TERMINÉE EN {elapsed:.1f}s ===")
    if total_generated > 0:
        print(f"Parties générées : {total_generated}")
        print(f"Vitesse moyenne : {total_generated / elapsed:.2f} parties/s")


if __name__ == "__main__":
    main()
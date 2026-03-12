import time
import chess_engine

# --- PARAMÈTRES ---
# Remplace par le chemin valide vers ton modèle ONNX actuel
ONNX_PATH = "checkpoints/2026_03_12_02h16_iter18_unsupervised.onnx"
SIMULATIONS = 1000


def run_benchmark():
    board = chess_engine.Chessboard()
    board.set_startup_pieces()

    print("Chargement du moteur MCTS...")
    mcts_engine = chess_engine.MCTS(ONNX_PATH)

    print("Préchauffage (initialisation ONNX)...")
    _ = mcts_engine.mcts_search(board, 10, 1.4, False)

    print(f"Lancement du benchmark sur {SIMULATIONS} simulations...")
    start_time = time.perf_counter()

    # Exécution de la recherche
    _ = mcts_engine.mcts_search(board, SIMULATIONS, 1.4, False)

    end_time = time.perf_counter()
    elapsed = end_time - start_time
    nps = SIMULATIONS / elapsed

    print("\n=== RÉSULTATS DU BENCHMARK ===")
    print(f"Temps écoulé : {elapsed:.3f} secondes")
    print(f"Vitesse      : {nps:.1f} nœuds / seconde (NPS)")
    print("==============================\n")


if __name__ == "__main__":
    run_benchmark()
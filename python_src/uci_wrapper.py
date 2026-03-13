import sys
import os
import numpy as np


# On ne fait aucun import lourd ici pour répondre instantanément à 'uci'
def log(msg):
    print(f"DEBUG: {msg}", file=sys.stderr, flush=True)


def main():
    # Variables globales pour conserver l'état entre les commandes
    mcts_engine = None
    board = None
    chess_engine_module = None
    lib_module = None

    # Chemins
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    model_name = "2026_03_13_01h31_iter18_unsupervised.onnx"

    # On cherche le modèle là où ton log disait qu'il était
    model_path = os.path.join(script_dir, "checkpoints", model_name)
    if not os.path.exists(model_path):
        # Fallback à la racine si pas trouvé
        model_path = os.path.join(root_dir, "checkpoints", model_name)

    while True:
        line = sys.stdin.readline()
        if not line: break
        cmd = line.strip()

        if cmd == "uci":
            # RÉPONSE INSTANTANÉE
            print("id name MonBot_AlphaZero")
            print("id author Mathieu_Leclercq")
            print("uciok", flush=True)

        elif cmd == "isready":
            # On ne charge le moteur que maintenant
            if mcts_engine is None:
                log("Initialisation différée du moteur...")
                try:
                    sys.path.append(script_dir)
                    import chess_engine
                    import lib
                    chess_engine_module = chess_engine
                    lib_module = lib

                    mcts_engine = chess_engine.MCTS(model_path)
                    board = chess_engine.Chessboard()
                    board.set_startup_pieces()
                    log(f"Moteur pret (Modele: {model_path})")
                except Exception as e:
                    log(f"ERREUR : {e}")
                    sys.exit(1)
            print("readyok", flush=True)

        elif cmd.startswith("position"):
            if board:
                board.set_startup_pieces()
                if "moves" in cmd:
                    for m in cmd.split("moves ")[1].split():
                        board.move_piece_san(m)

        elif cmd.startswith("go"):
            # Inférence
            pi_raw = mcts_engine.mcts_search(board, 1200, 1.4, False)
            pi = np.array(pi_raw, dtype=np.float32)

            # Masking + Température
            mask = pi > 0
            logits = np.full_like(pi, -1e20, dtype=np.float64)
            logits[mask] = np.log(pi[mask].astype(np.float64)) / 0.01
            logits -= np.max(logits)
            probs = np.exp(logits)
            probs[~mask] = 0
            probs /= probs.sum()

            idx = int(np.random.choice(len(probs), p=probs))
            f_o, r_o, f_d, r_d, p = lib_module.decode_move_index(board, idx,
                                                                 board.turn == chess_engine_module.Color.BLACK)

            # Format UCI
            files = "abcdefgh"
            mv = f"{files[f_o]}{r_o + 1}{files[f_d]}{r_d + 1}"
            promos = {chess_engine_module.PieceType.QUEEN: "q",
                      chess_engine_module.PieceType.ROOK: "r",
                      chess_engine_module.PieceType.BISHOP: "b",
                      chess_engine_module.PieceType.KNIGHT: "n"}
            if p in promos: mv += promos[p]
            print(f"bestmove {mv}", flush=True)

        elif cmd == "quit":
            break


if __name__ == "__main__":
    main()
import os
import torch
import numpy as np
from whr import whole_history_rating
import chess_engine
from model import ChessNet
from mcts import MCTS
from lib import decode_move_index

# ============================================================
#                     CONFIGURATION
# ============================================================
CHECKPOINT_DIR = "checkpoints"
NUM_RES_BLOCKS = 10
NUM_FILTERS = 128
SIMULATIONS_EVAL = 1
GAMES_PER_PAIR = 4  # Nombre de parties entre chaque version (2 Blancs, 2 Noirs)


def load_model_pure(path, device):
    model = ChessNet(num_res_blocks=NUM_RES_BLOCKS, num_filters=NUM_FILTERS)
    checkpoint = torch.load(path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device).eval()
    return model


def play_game(model_white, model_black, device, sims):
    board = chess_engine.Chessboard()
    board.set_startup_pieces()

    while board.game_state == chess_engine.GameState.ONGOING:
        current_model = model_white if board.turn == chess_engine.Color.WHITE else model_black

        # Inférence pure : pas de bruit, pas de température
        pi, _ = MCTS.mcts_search(board, current_model, device, num_simulations=sims,
                                 add_dirichlet=False)
        best_idx = np.argmax(pi)

        is_black = (board.turn == chess_engine.Color.BLACK)
        f_o, r_o, f_d, r_d, p = decode_move_index(board, best_idx, is_black)
        board.move_piece(f_o, r_o, f_d, r_d, p)

        # Limite pour éviter les parties infinies
        if len(board.get_board_history()) > 300:
            break

    if board.game_state == chess_engine.GameState.CHECKMATE:
        # Si c'est au tour du Blanc, c'est que le Noir vient de gagner
        return "black" if board.turn == chess_engine.Color.WHITE else "white"
    return "draw"


def run_tournament():
    device = torch.device("cuda")
    whr = whole_history_rating.Base({"w2": 14})

    files = sorted([f for f in os.listdir(CHECKPOINT_DIR) if f.endswith(".pt")])
    if len(files) < 2:
        print("Besoin d'au moins 2 checkpoints pour un tournoi.")
        return

    for i in range(len(files) - 1):
        p1_name = files[i]
        p2_name = files[i + 1]

        print(f"\nMatch: {p1_name} vs {p2_name}")
        m1 = load_model_pure(os.path.join(CHECKPOINT_DIR, p1_name), device)
        m2 = load_model_pure(os.path.join(CHECKPOINT_DIR, p2_name), device)

        # for g in range(GAMES_PER_PAIR):
        #     if g % 2 == 0:
        #         # m1 est Blanc, m2 est Noir
        #         res = play_game(m1, m2, device, SIMULATIONS_EVAL)
        #         outcome = "W" if res == "white" else ("B" if res == "black" else "D")
        #         whr.create_game(p2_name, p1_name, outcome, i, 0)
        #     else:
        #         # m2 est Blanc, m1 est Noir
        #         res = play_game(m2, m1, device, SIMULATIONS_EVAL)
        #         outcome = "W" if res == "white" else ("B" if res == "black" else "D")
        #         whr.create_game(p1_name, p2_name, outcome, i, 0)
        #
        #     print(f"  Partie {g + 1}: {res} wins (WHR label: {outcome})")

        for g in range(GAMES_PER_PAIR):
            # Détermination des couleurs pour cette partie
            if g % 2 == 0:
                white_p, black_p = p1_name, p2_name
            else:
                white_p, black_p = p2_name, p1_name

            res = play_game(load_model_pure(os.path.join(CHECKPOINT_DIR, white_p), device),
                            load_model_pure(os.path.join(CHECKPOINT_DIR, black_p), device),
                            device, SIMULATIONS_EVAL)

            if res == "draw":
                # Pour un nul, on crée deux entrées : une victoire pour chaque camp.
                # C'est la méthode mathématique standard pour WHR.
                whr.create_game(black_p, white_p, "B", i, 0)
                whr.create_game(black_p, white_p, "W", i, 0)
                outcome_label = "Draw (Split)"
            elif res == "white":
                whr.create_game(black_p, white_p, "W", i, 0)
                outcome_label = "White Wins"
            else:  # black
                whr.create_game(black_p, white_p, "B", i, 0)
                outcome_label = "Black Wins"

            print(f"  Partie {g + 1}: {outcome_label}")


    # 3. Calcul de l'Elo
    whr.iterate(100)
    print("\n" + "=" * 30)
    print(" RÉSULTATS ELO (BAYES-WHR)")
    print("=" * 30)

    for f in files:
        rating_data = whr.ratings_for_player(f)
        last_elo = rating_data[-1][1]
        uncertainty = rating_data[-1][2]
        print(f"{f:25} : {last_elo:+.1f} Elo (±{uncertainty:.1f})")


if __name__ == "__main__":
    run_tournament()

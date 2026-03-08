import os
import torch
import numpy as np
from whr import whole_history_rating
import chess_engine
from model import ChessNet
from mcts import MCTS
from lib import decode_move_index, move_to_san

# ============================================================
#                     CONFIGURATION
# ============================================================
NUM_RES_BLOCKS = 10
NUM_FILTERS = 128

CHECKPOINT_DIR = "checkpoints"
SIMULATIONS_EVAL = 200
GAMES_PER_PAIR = 2
WHR_STATE_FILE = "tournament_state.whr"


def load_model_pure(path, device):
    model = ChessNet(num_res_blocks=NUM_RES_BLOCKS, num_filters=NUM_FILTERS)
    checkpoint = torch.load(path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device).eval()
    return model


def play_game(model_white, model_black, device, sims):
    board = chess_engine.Chessboard()
    board.set_startup_pieces()
    san_moves = []

    while board.game_state == chess_engine.GameState.ONGOING:
        current_model = model_white if board.turn == chess_engine.Color.WHITE else model_black
        pi, _ = MCTS.mcts_search(board, current_model, device, num_simulations=sims,
                                 add_dirichlet=False, batch_size=2)
        # best_idx = np.argmax(pi)
        move_count = len(san_moves)
        current_tau = 1.0 if move_count < 10 else 0.01
        tau = max(current_tau, 0.01)
        log_pi = np.log(pi.astype(np.float64) + 1e-10)
        logits = log_pi / tau
        logits -= np.max(logits)
        pi_temp = np.exp(logits)
        pi_temp /= pi_temp.sum()

        best_idx = np.random.choice(len(pi), p=pi_temp)

        is_black = (board.turn == chess_engine.Color.BLACK)
        f_o, r_o, f_d, r_d, p = decode_move_index(board, best_idx, is_black)

        san = move_to_san(board, f_o, r_o, f_d, r_d, p)
        board.move_piece(f_o, r_o, f_d, r_d, p)

        if board.game_state == chess_engine.GameState.CHECKMATE:
            san += "#"
        elif board.is_in_check():
            san += "+"

        san_moves.append(san)
        if len(san_moves) > 300: break

    winner = "draw"
    if board.game_state == chess_engine.GameState.CHECKMATE:
        winner = "black" if board.turn == chess_engine.Color.WHITE else "white"

    return winner, san_moves


def format_pgn(white_name, black_name, winner, moves):
    result = "1/2-1/2"
    if winner == "white":
        result = "1-0"
    elif winner == "black":
        result = "0-1"

    pgn = f'[White "{white_name}"]\n[Black "{black_name}"]\n[Result "{result}"]\n\n'
    for i in range(0, len(moves), 2):
        move_num = (i // 2) + 1
        pgn += f"{move_num}. {moves[i]} "
        if i + 1 < len(moves):
            pgn += f"{moves[i + 1]} "
    pgn += f" {result}\n"
    return pgn


def run_tournament():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # 1. Charger l'ancienne base ou en créer une nouvelle
    if os.path.exists(WHR_STATE_FILE):
        print(f"Chargement de l'historique Elo depuis {WHR_STATE_FILE}...")
        whr = whole_history_rating.Base.load_base(WHR_STATE_FILE)
    else:
        whr = whole_history_rating.Base({"w2": 14})

    files = sorted([f for f in os.listdir(CHECKPOINT_DIR) if f.endswith(".pt")])
    if len(files) < 2:
        print("Besoin d'au moins 2 checkpoints pour un tournoi.")
        return

    # On identifie les joueurs déjà présents pour ne pas rejouer leurs matchs
    existing_players = whr.players.keys()

    # 2. Boucle de tournoi
    for i in range(len(files) - 1):
        p1, p2 = files[i], files[i + 1]

        # On ne joue le match que si l'un des deux modèles est "nouveau" dans la base
        if p1 not in existing_players or p2 not in existing_players:
            print(f"\n--- Nouveau match nécessaire: {p1} vs {p2} ---")
            m1 = load_model_pure(os.path.join(CHECKPOINT_DIR, p1), device)
            m2 = load_model_pure(os.path.join(CHECKPOINT_DIR, p2), device)

            for g in range(GAMES_PER_PAIR):
                if g % 2 == 0:
                    white_name, black_name = p1, p2
                    white_m, black_m = m1, m2
                else:
                    white_name, black_name = p2, p1
                    white_m, black_m = m2, m1

                winner, moves = play_game(white_m, black_m, device, SIMULATIONS_EVAL)

                print(format_pgn(white_name, black_name, winner, moves))

                if winner == "draw":
                    whr.create_game(black_name, white_name, "B", i, 0)
                    whr.create_game(black_name, white_name, "W", i, 0)
                    outcome_label = "Draw (Split)"
                elif winner == "white":
                    whr.create_game(black_name, white_name, "W", i, 0)
                    outcome_label = "White Wins"
                else:
                    whr.create_game(black_name, white_name, "B", i, 0)
                    outcome_label = "Black Wins"

                print(f"  Partie {g + 1}: {outcome_label}")
        else:
            print(f"Match {p1} vs {p2} déjà enregistré, passage au suivant...")

    # 3. Calcul et Sauvegarde
    print("\nCalcul des Elos via convergence Newton...")
    whr.iterate(100)
    whr.save_base(WHR_STATE_FILE)
    print(f"État du tournoi sauvegardé dans {WHR_STATE_FILE}")

    print("\n" + "=" * 30)
    print(" RÉSULTATS ELO (BAYES-WHR)")
    print("=" * 30)

    for f in files:
        rating_data = whr.ratings_for_player(f)
        if rating_data:
            last_elo = rating_data[-1][1]
            uncertainty = rating_data[-1][2]
            print(f"{f:40} : {last_elo:+.1f} Elo (±{uncertainty:.1f})")


if __name__ == "__main__":
    run_tournament()

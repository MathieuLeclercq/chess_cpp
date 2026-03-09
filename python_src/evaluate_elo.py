import os
import torch
import numpy as np
from whr import whole_history_rating
import chess_engine
from mcts import MCTS
from lib import decode_move_index, move_to_san, load_model

# ============================================================
#                     CONFIGURATION
# ============================================================
NUM_RES_BLOCKS = 10
NUM_FILTERS = 128

CHECKPOINT_DIR = "checkpoints"
SIMULATIONS_EVAL = 200
GAMES_PER_PAIR = 2  # Nombre total de parties par face-à-face
WHR_STATE_FILE = "tournament_state.whr"


def play_game(model_white, model_black, device, sims):
    board = chess_engine.Chessboard()
    board.set_startup_pieces()
    san_moves = []

    while board.game_state == chess_engine.GameState.ONGOING:
        current_model = model_white if board.turn == chess_engine.Color.WHITE else model_black
        pi, _ = MCTS.mcts_search(board, current_model, device, num_simulations=sims,
                                 add_dirichlet=False)

        move_count = len(san_moves)
        current_tau = 0.3 if move_count < 8 else 0.01

        log_pi = np.log(pi.astype(np.float64) + 1e-10)
        logits = log_pi / current_tau
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
        if i + 1 < len(moves): pgn += f"{moves[i + 1]} "
    pgn += f" {result}\n"
    return pgn


def count_games_between(whr, p1, p2):
    """Compte combien de matchs existent déjà entre deux joueurs dans la base."""
    count = 0
    for game in whr.games:
        if (game.black_player.name == p1 and game.white_player.name == p2) or \
                (game.black_player.name == p2 and game.white_player.name == p1):
            count += 1
    # Note: Dans WHR, un Draw est souvent enregistré comme 2 games (B et W).
    # Si ton code enregistre les draws en split, il faut diviser par 2 ou adapter.
    # Ici, ton code enregistre 2 games par Draw, donc on divise par 2 pour le compte "humain".
    return count


def run_tournament():
    device = torch.device("cpu")

    if os.path.exists(WHR_STATE_FILE):
        print(f"Chargement de l'historique Elo depuis {WHR_STATE_FILE}...")
        whr = whole_history_rating.Base.load_base(WHR_STATE_FILE)
    else:
        whr = whole_history_rating.Base({"w2": 14})

    files = sorted([f for f in os.listdir(CHECKPOINT_DIR) if
                    f.endswith(".pt") or f.endswith(".ckpt")])
    print(f"{files=}")
    if len(files) < 2:
        return

    for i in range(len(files) - 1):
        p1, p2 = files[i], files[i + 1]

        # Logique de saut améliorée : on compte les parties réelles
        # Un Draw compte pour 2 dans whr.games (B et W), une victoire pour 1.
        # On vérifie si on a atteint le quota GAMES_PER_PAIR
        games_played = count_games_between(whr, p1, p2)

        # Approximation : comme un Draw = 2 slots dans WHR, on ajuste le seuil
        if games_played < GAMES_PER_PAIR:
            print(f"\n--- Match: {p1} vs {p2} ({games_played}/{GAMES_PER_PAIR} joués) ---")

            m1 = load_model(os.path.join(CHECKPOINT_DIR, p1), NUM_RES_BLOCKS, NUM_FILTERS, device)
            m2 = load_model(os.path.join(CHECKPOINT_DIR, p2), NUM_RES_BLOCKS, NUM_FILTERS, device)

            for g in range(games_played, GAMES_PER_PAIR):
                if g % 2 == 0:
                    white_n, black_n, white_m, black_m = p1, p2, m1, m2
                else:
                    white_n, black_n, white_m, black_m = p2, p1, m2, m1

                winner, moves = play_game(white_m, black_m, device, SIMULATIONS_EVAL)
                print(format_pgn(white_n, black_n, winner, moves))

                if winner == "draw":
                    whr.create_game(black_n, white_n, "B", i, 0)
                    whr.create_game(black_n, white_n, "W", i, 0)
                else:
                    outcome = "W" if winner == "white" else "B"
                    whr.create_game(black_n, white_n, outcome, i, 0)

                # --- SAUVEGARDE ET MISE À JOUR LIVE ---
                # On fait 5 itérations pour rafraîchir l'Elo sans bloquer le script
                whr.iterate(5)
                whr.save_base(WHR_STATE_FILE)

                p1_elo = whr.ratings_for_player(p1)[-1][1]
                p2_elo = whr.ratings_for_player(p2)[-1][1]
                print(f"  Sauvegarde effectuée. Elo live : {p1}: {p1_elo} | {p2}: {p2_elo}")
        else:
            print(f"Match {p1} vs {p2} complet, passage au suivant...")

    # Fin du tournoi : Grosse optimisation finale
    print("\nOptimisation finale de la courbe Elo...")
    whr.iterate(100)
    whr.save_base(WHR_STATE_FILE)

    print("\n" + "=" * 30 + "\n RÉSULTATS FINAUX\n" + "=" * 30)
    for f in files:
        rating = whr.ratings_for_player(f)
        if rating:
            print(f"{f:40} : {rating[-1][1]:+.1f} Elo (±{rating[-1][2]:.1f})")


if __name__ == "__main__":
    run_tournament()

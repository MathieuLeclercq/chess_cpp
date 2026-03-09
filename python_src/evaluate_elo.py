import os
import torch
import itertools
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
SIMULATIONS_EVAL = 600
GAMES_PER_PAIR = 4
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


def get_ranked_players(whr, files):
    """Retourne la liste des joueurs triée par Elo décroissant."""
    players = []
    for f in files:
        rating = whr.ratings_for_player(f)
        if rating:
            players.append((f, rating[-1][1]))  # (nom, elo)
    players.sort(key=lambda x: x[1], reverse=True)
    return players


def play_match(p1, p2, whr, device):
    """Lance un face-à-face entre deux bots et met à jour le WHR."""
    print(f"\n--- MATCH : {p1} vs {p2} ---")

    # Initialisation des scores du match
    score_p1 = 0.0
    score_p2 = 0.0

    # Chargement des modèles
    res1 = load_model(os.path.join(CHECKPOINT_DIR, p1), NUM_RES_BLOCKS, NUM_FILTERS, device)
    res2 = load_model(os.path.join(CHECKPOINT_DIR, p2), NUM_RES_BLOCKS, NUM_FILTERS, device)
    m1 = res1[0] if isinstance(res1, tuple) else res1
    m2 = res2[0] if isinstance(res2, tuple) else res2

    for g in range(GAMES_PER_PAIR):
        if g % 2 == 0:
            white_n, black_n, white_m, black_m = p1, p2, m1, m2
        else:
            white_n, black_n, white_m, black_m = p2, p1, m2, m1

        winner, moves = play_game(white_m, black_m, device, SIMULATIONS_EVAL)
        print(format_pgn(white_n, black_n, winner, moves))

        if winner == "draw":
            score_p1 += 0.5
            score_p2 += 0.5
            whr.create_game(black_n, white_n, "B", 0, 0)
            whr.create_game(black_n, white_n, "W", 0, 0)
        else:
            if winner == "white":
                if white_n == p1:
                    score_p1 += 1
                else:
                    score_p2 += 1
            else:
                if black_n == p1:
                    score_p1 += 1
                else:
                    score_p2 += 1

            outcome = "W" if winner == "white" else "B"
            whr.create_game(black_n, white_n, outcome, 0, 0)

    print(f"\n>>>> FIN DU MATCH : {p1} ({score_p1}) - {p2} ({score_p2})")

    whr.iterate(10)
    whr.save_base(WHR_STATE_FILE)


def run_tournament():
    device = torch.device("cpu")
    if os.path.exists(WHR_STATE_FILE):
        whr = whole_history_rating.Base.load_base(WHR_STATE_FILE)
    else:
        whr = whole_history_rating.Base({"w2": 14})

    all_files = sorted([f for f in os.listdir(CHECKPOINT_DIR) if f.endswith((".pt", ".ckpt"))])

    # Identifier les nouveaux venus
    known_players = [p.name for p in whr.players.values()]
    new_bots = [f for f in all_files if f not in known_players]

    # Obtenir le classement actuel
    ranked_existing = get_ranked_players(whr, all_files)

    # --- LOGIQUE DE SELECTION DES MATCHS ---
    pairs_to_play = []

    if new_bots:
        print(f"Nouveaux bots détectés : {new_bots}")
        # 1. Chaque nouveau bot contre le champion
        if ranked_existing:
            champion = ranked_existing[0][0]
            for nb in new_bots:
                pairs_to_play.append((nb, champion))

        # 2. Les nouveaux bots entre eux
        if len(new_bots) > 1:
            for pair in itertools.combinations(new_bots, 2):
                pairs_to_play.append(pair)

    elif len(ranked_existing) >= 2:
        # 3. 0 nouveau bot : Match au sommet (n°1 vs n°2)
        p1, p2 = ranked_existing[0][0], ranked_existing[1][0]
        print(f"Aucun nouveau bot. Choc des titans : {p1} vs {p2}")
        pairs_to_play.append((p1, p2))

    # --- EXECUTION DES MATCHS ---
    for p1, p2 in pairs_to_play:
        play_match(p1, p2, whr, device)

    # --- RESULTATS FINAUX ---
    whr.iterate(100)
    whr.save_base(WHR_STATE_FILE)

    print("\n" + "=" * 30 + "\n CLASSEMENT MIS À JOUR\n" + "=" * 30)
    final_ranking = get_ranked_players(whr, all_files)
    for name, elo in final_ranking:
        print(f"{name:40} : {elo:+.1f} Elo")


if __name__ == "__main__":
    run_tournament()

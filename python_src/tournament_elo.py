import os
import itertools
import numpy as np
from whr import whole_history_rating

import chess_engine
from lib import (
    decode_move_index, move_to_san, get_model_hash, chose_move_idx, parse_uci_to_coords,
    coords_to_uci)
from stockfish_player import StockfishPlayer

STOCKFISH_PATH = r"D:\logiciels\stockfish\stockfish.exe"

# ============================================================
#                     CONFIGURATION
# ============================================================
CHECKPOINT_DIR = "checkpoints"
SIMULATIONS_EVAL = 600
GAMES_PER_PAIR = 2
WHR_STATE_FILE = "tournament_state.whr"
MODE = "7-9"  # Options : "default", "all", ou "x-y"


def play_game(model_white, model_black, sims):
    board = chess_engine.Chessboard()
    board.set_startup_pieces()

    # On garde la liste des coups en format UCI pour Stockfish
    uci_moves = []
    san_moves = []

    while board.game_state == chess_engine.GameState.ONGOING:
        current_model = model_white if board.turn == chess_engine.Color.WHITE else model_black

        if isinstance(current_model, StockfishPlayer):
            move_uci = current_model.get_move(uci_moves)
            f_o, r_o, f_d, r_d, p = parse_uci_to_coords(move_uci)

        else:
            # Appel au moteur MCTS C++ / ONNX
            pi_raw = current_model.mcts_search(board, sims, 1.4, False)
            pi = np.array(pi_raw, dtype=np.float32)
            move_count = len(san_moves)
            if move_count < 2:
                current_tau = 2
            elif move_count < 8:
                current_tau = 1.0
            else:
                current_tau = 0.1

            best_idx = chose_move_idx(pi, current_tau)
            is_black = (board.turn == chess_engine.Color.BLACK)
            f_o, r_o, f_d, r_d, p = decode_move_index(board, best_idx, is_black)
            move_uci = coords_to_uci(f_o, r_o, f_d, r_d, p)

        san = move_to_san(board, f_o, r_o, f_d, r_d, p)
        board.move_piece(f_o, r_o, f_d, r_d, p)
        if board.game_state == chess_engine.GameState.CHECKMATE:
            san += "#"
        elif board.is_in_check():
            san += "+"

        san_moves.append(san)
        uci_moves.append(move_uci)

        if len(san_moves) > 300:
            break

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
    """Retourne la liste des joueurs triée par Elo décroissant avec le nombre de parties."""
    # 1. Comptage des parties pour chaque hash
    game_counts = {f: 0 for f in files}
    for game in whr.games:
        w_name = game.white_player.name
        b_name = game.black_player.name
        if w_name in game_counts:
            game_counts[w_name] += 1
        if b_name in game_counts:
            game_counts[b_name] += 1

    # 2. Construction du classement
    players = []
    for f in files:
        rating = whr.ratings_for_player(f)
        if rating:
            players.append((f, rating[-1][1], game_counts[f]))

    players.sort(key=lambda x: x[1], reverse=True)
    return players


def play_match(h1, h2, hash_to_filename, whr):
    """Lance un face-à-face entre deux bots et met à jour le WHR."""

    p1 = hash_to_filename[h1]
    p2 = hash_to_filename[h2]

    print(f"\n--- MATCH : {p1} vs {p2} ---")

    # Chargement intelligent
    if h1 == "STOCKFISH_FIXED_1500":
        m1 = StockfishPlayer(STOCKFISH_PATH, elo=1500)
    else:
        m1 = chess_engine.MCTS(os.path.join(CHECKPOINT_DIR, p1))

    if h2 == "STOCKFISH_FIXED_1500":
        m2 = StockfishPlayer(STOCKFISH_PATH, elo=1500)
    else:
        m2 = chess_engine.MCTS(os.path.join(CHECKPOINT_DIR, p2))

    # Initialisation des scores du match
    score_p1 = 0.0
    score_p2 = 0.0

    for g in range(GAMES_PER_PAIR):
        if g % 2 == 0:
            white_n, black_n, white_m, black_m = p1, p2, m1, m2
            white_h, black_h = h1, h2  # Ajout des identifiants Hash
        else:
            white_n, black_n, white_m, black_m = p2, p1, m2, m1
            white_h, black_h = h2, h1  # Ajout des identifiants Hash

        winner, moves = play_game(white_m, black_m, SIMULATIONS_EVAL)
        print(format_pgn(white_n, black_n, winner, moves))

        if winner == "draw":
            score_p1 += 0.5
            score_p2 += 0.5
            # On passe bien les Hashs au WHR
            whr.create_game(black_h, white_h, "B", 0, 0)
            whr.create_game(black_h, white_h, "W", 0, 0)
        else:
            if winner == "white":
                if white_h == h1:
                    score_p1 += 1
                else:
                    score_p2 += 1
            else:
                if black_h == h1:
                    score_p1 += 1
                else:
                    score_p2 += 1

            outcome = "W" if winner == "white" else "B"
            # On passe bien les Hashs au WHR
            whr.create_game(black_h, white_h, outcome, 0, 0)

    print(f"\n>>>> FIN DU MATCH : {p1} ({score_p1}) - {p2} ({score_p2})")

    whr.iterate(10)
    whr.save_base(WHR_STATE_FILE)


def run_tournament():
    if os.path.exists(WHR_STATE_FILE):
        whr = whole_history_rating.Base.load_base(WHR_STATE_FILE)
    else:
        whr = whole_history_rating.Base({"w2": 14})

    # 1. Scan des fichiers physiques
    onnx_files = [f for f in os.listdir(CHECKPOINT_DIR) if f.endswith(".onnx")]

    # 2. Création du mapping Hash -> Filename
    hash_to_filename = {}
    for f in onnx_files:
        h = get_model_hash(os.path.join(CHECKPOINT_DIR, f))
        hash_to_filename[h] = f

    SF_HASH = "STOCKFISH_FIXED_1500"
    hash_to_filename[SF_HASH] = "STOCKFISH_1500_ANCHOR"

    all_hashes = list(hash_to_filename.keys())

    # 3. Identification des nouveaux venus par rapport au WHR
    known_hashes = [p.name for p in whr.players.values()]
    new_hashes = [h for h in all_hashes if h not in known_hashes]

    # 4. Classement actuel
    ranked_existing_hashes = get_ranked_players(whr, all_hashes)

    print("\n" + "=" * 30 + "\n CLASSEMENT ACTUEL\n" + "=" * 30)
    for h, elo, games in ranked_existing_hashes:
        print(f"{hash_to_filename[h]:35} : {elo:>6.1f} Elo | {games:>3} parties ({h})")

    # --- LOGIQUE DE SELECTION DES MATCHS ---
    pairs_to_play = []

    if MODE == "all":
        print(f"\nMode 'all' activé : Tournoi complet entre les {len(all_hashes)} bots.")
        # Génère toutes les paires uniques possibles
        pairs_to_play = list(itertools.combinations(all_hashes, 2))

    elif "-" in str(MODE):
        try:
            rank1, rank2 = map(int, str(MODE).split('-'))
            idx1, idx2 = rank1 - 1, rank2 - 1  # Conversion en index 0-based

            if max(idx1, idx2) >= len(ranked_existing_hashes):
                print(
                    f"\nErreur : Le classement ne contient que "
                    f"{len(ranked_existing_hashes)} bots. Impossible de jouer le match {MODE}.")
            elif min(idx1, idx2) < 0 or idx1 == idx2:
                print(f"\nErreur : Les rangs doivent être valides et différents (ex: '1-3').")
            else:
                h1 = ranked_existing_hashes[idx1][0]
                h2 = ranked_existing_hashes[idx2][0]
                print(f"\nMode spécifique activé : Match entre le rang {rank1} et le rang {rank2}.")
                pairs_to_play.append((h1, h2))
        except ValueError:
            print(f"\nErreur : Format de MODE invalide '{MODE}'. Utilisez un format comme '1-3'.")

    else:
        # Mode par défaut
        if new_hashes:
            print(f"\nNouveaux modèles détectés (via Hash) : {len(new_hashes)}")
            # On utilise le meilleur hash connu comme champion
            if ranked_existing_hashes:
                champion_hash = ranked_existing_hashes[0][0]
                for nh in new_hashes:
                    pairs_to_play.append((nh, champion_hash))

            # Les nouveaux entre eux
            if len(new_hashes) > 1:
                for pair in itertools.combinations(new_hashes, 2):
                    pairs_to_play.append(pair)

        elif len(ranked_existing_hashes) >= 2:
            p1_h, p2_h = ranked_existing_hashes[0][0], ranked_existing_hashes[1][0]
            print(
                f"\nAucun nouveau bot. Choc des titans : "
                f"{hash_to_filename[p1_h]} vs {hash_to_filename[p2_h]}")
            pairs_to_play.append((p1_h, p2_h))

    # --- EXECUTION DES MATCHS ---
    total_matches = len(pairs_to_play)

    for i, (h1, h2) in enumerate(pairs_to_play):
        play_match(h1, h2, hash_to_filename, whr)

        # Calcul du reste
        matches_left = total_matches - (i + 1)
        games_left = matches_left * GAMES_PER_PAIR

        if matches_left > 0:
            print(f"\n" + "-" * 50)
            print(f"[PROGRESSION] Match {i + 1}/{total_matches} terminé.")
            print(
                f"[PROGRESSION] Il reste {matches_left} match(s) "
                f"soit environ {games_left} partie(s).")
            print("-" * 50 + "\n")

    # --- RESULTATS FINAUX ---

    whr.auto_iterate()
    whr.save_base(WHR_STATE_FILE)

    final_ranking = get_ranked_players(whr, all_hashes)

    sf_raw_elo = None
    for h, elo, games in final_ranking:
        if h == "STOCKFISH_FIXED_1500":
            sf_raw_elo = elo
            break

    # Si SF a joué au moins une partie, on calibre. Sinon offset = 0.
    anchor_offset = 1500 - sf_raw_elo if sf_raw_elo is not None else 0

    print("\n" + "=" * 40 + f"\n CLASSEMENT ANCRÉ (Stockfish = 1500)\n" + "=" * 40)
    for h, elo, games in final_ranking:
        name = hash_to_filename.get(h, "Unknown")
        print(f"{name:35} : {elo + anchor_offset:>6.1f} Elo | {games:>3} parties")


if __name__ == "__main__":
    run_tournament()

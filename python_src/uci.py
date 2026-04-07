import sys
import threading
import time
import math

import chess_engine
from lib import parse_uci_to_coords, coords_to_uci, decode_move_index, encode_move

# ============================================================
#                     CONFIGURATION EN DUR
# ============================================================
MODEL_PATH = (r"C:\Users\M47h1\Documents\chess_cpp\python_src"
              r"\checkpoints/2026_04_07_00h34_iter7_unsupervised.onnx")
DEFAULT_SIMULATIONS = 1200
BATCH_SIZE = 100


# ============================================================
#                     MOTEUR UCI
# ============================================================
class UCIEngine:
    def __init__(self):
        self.board = chess_engine.Chessboard()
        self.mcts = chess_engine.MCTS(MODEL_PATH)
        self.search_thread = None

        self.stop_event = threading.Event()

        # Variables de contrôle de l'horloge
        self.is_pondering = False
        self.target_time = 10.0
        self.search_start_time = 0.0

        # Historique pour le Root Shifting
        self.last_move_list = []

    @staticmethod
    def q_to_cp(q_value):
        q = max(-0.999999, min(0.999999, q_value))
        return int(round(290.0 * math.atanh(q)))

    def loop(self):
        while True:
            try:
                line = sys.stdin.readline().strip()
                if not line:
                    continue
            except EOFError:
                break

            tokens = line.split()
            command = tokens[0]

            if command == "uci":
                print("id name Lc0 Custom")
                print("id author Mathieu Leclercq")
                print("option name WeightsFile type string default <internal>")
                print("uciok")
                sys.stdout.flush()

            elif command == "isready":
                print("readyok")
                sys.stdout.flush()

            elif command == "ucinewgame":
                self.mcts.reset_analysis()
                self.last_move_list = []

            elif command == "position":
                self.parse_position(tokens[1:])

            elif command == "go":
                self.start_search(tokens[1:])

            elif command == "ponderhit":
                # L'adversaire a joué notre ponder move !
                # On bascule en temps normal sans arrêter la recherche C++
                self.is_pondering = False
                self.search_start_time = time.time()  # Le chrono démarre !

            elif command == "stop":
                self.stop_search()

            elif command == "quit":
                self.stop_search()
                break

    def parse_position(self, tokens):
        moves_idx = -1
        if len(tokens) > 0 and tokens[0] == "startpos":
            moves_idx = 2 if len(tokens) > 1 and tokens[1] == "moves" else -1
        elif len(tokens) > 0 and tokens[0] == "fen":
            moves_idx = 8 if len(tokens) > 7 and tokens[7] == "moves" else -1

        new_move_list = tokens[moves_idx:] if moves_idx != -1 else []

        # 1. Ponder Hit Parfait ou redondance GUI (On ne touche à rien)
        # SÉCURITÉ : On s'assure qu'on a déjà un historique valide
        if len(self.last_move_list) > 0 and new_move_list == self.last_move_list:
            pass

        # 2. Avancée normale d'un coup (On décale la racine)
        # SÉCURITÉ : len(self.last_move_list) > 0 garantit que le plateau a été initialisé avec ses pièces
        elif len(self.last_move_list) > 0 and len(new_move_list) == len(
                self.last_move_list) + 1 and new_move_list[:-1] == self.last_move_list:
            last_uci = new_move_list[-1]
            is_black = (self.board.turn == chess_engine.Color.BLACK)
            orig_f, orig_r, dest_f, dest_r, promo = parse_uci_to_coords(last_uci)

            move_idx = encode_move(orig_f, orig_r, dest_f, dest_r, promo, is_black)
            self.mcts.update_root(move_idx)
            self.board.move_piece(orig_f, orig_r, dest_f, dest_r, promo)

        # 3. 1er coup de la partie, Ponder Miss, ou Nouvelle Partie : on reconstruit tout PROPREMENT
        else:
            self.mcts.reset_analysis()
            self.board = chess_engine.Chessboard()

            if len(tokens) > 0 and tokens[0] == "startpos":
                self.board.set_startup_pieces()
            elif len(tokens) > 0 and tokens[0] == "fen":
                fen_string = " ".join(tokens[1:7])
                self.board.load_fen(fen_string)

            for uci_move in new_move_list:
                orig_f, orig_r, dest_f, dest_r, promo = parse_uci_to_coords(uci_move)
                self.board.move_piece(orig_f, orig_r, dest_f, dest_r, promo)

        self.last_move_list = new_move_list

    def start_search(self, tokens):
        self.stop_search()
        self.stop_event.clear()

        my_time = None
        my_inc = 0
        movetime_ms = None

        # Détection de l'ordre de Pondering par la GUI
        self.is_pondering = "ponder" in tokens
        is_infinite = "infinite" in tokens
        is_black = (self.board.turn == chess_engine.Color.BLACK)

        for i in range(len(tokens) - 1):
            if tokens[i] == "wtime" and not is_black:
                my_time = int(tokens[i + 1])
            elif tokens[i] == "btime" and is_black:
                my_time = int(tokens[i + 1])
            elif tokens[i] == "winc" and not is_black:
                my_inc = int(tokens[i + 1])
            elif tokens[i] == "binc" and is_black:
                my_inc = int(tokens[i + 1])
            elif tokens[i] == "movetime":
                movetime_ms = int(tokens[i + 1])

        # Calcul du budget temps
        if is_infinite:
            self.target_time = 1e9
        elif movetime_ms is not None:
            self.target_time = (movetime_ms / 1000.0) * 0.95
        elif my_time is not None:
            self.target_time = ((my_time / 25) + (my_inc * 0.7)) / 1000.0
        else:
            self.target_time = 10.0

        self.search_start_time = time.time()
        self.search_thread = threading.Thread(target=self.search_worker)
        self.search_thread.start()

    def stop_search(self):
        if self.search_thread and self.search_thread.is_alive():
            self.stop_event.set()
            self.search_thread.join()

    def search_worker(self):
        total_sims = 0
        max_sims = 10_000_000

        # --- 1. BOUCLE DE RECHERCHE ---
        while total_sims < max_sims and not self.stop_event.is_set():

            # Si on est en "Ponder", on ignore le chrono. L'arbitre c'est la GUI.
            if not self.is_pondering:
                elapsed = time.time() - self.search_start_time
                if elapsed >= self.target_time:
                    break

            sims_to_do = BATCH_SIZE
            self.mcts.step_analysis(self.board, sims_to_do, 1.4)
            total_sims += sims_to_do

            stats = self.mcts.get_analysis_results()
            if not stats:
                break

            stats_sorted = sorted(stats, key=lambda stat: stat.visits, reverse=True)

            # 1. On calcule le vrai total des visites de la racine actuelle
            real_total_nodes = sum(stat.visits for stat in stats_sorted)

            # (Optionnel) Éviter la division par zéro tout au début
            if real_total_nodes == 0:
                real_total_nodes = 1

            for multipv_idx in range(len(stats_sorted) - 1, -1, -1):
                move_stat = stats_sorted[multipv_idx]
                is_black = (self.board.turn == chess_engine.Color.BLACK)
                o_f, o_r, d_f, d_r, promo = decode_move_index(self.board, move_stat.move_idx,
                                                              is_black)
                uci_str = coords_to_uci(o_f, o_r, d_f, d_r, promo)
                cp_score = self.q_to_cp(move_stat.q_value)

                # 2. On envoie le vrai total à la GUI
                print(
                    f"info depth {total_sims} multipv {multipv_idx + 1} score cp "
                    f"{cp_score} nodes {real_total_nodes} pv {uci_str}"
                )

                n = move_stat.visits
                p = move_stat.prior * 100.0
                q = move_stat.q_value

                print(
                    f"info string {uci_str} (0 ) N: {n} (+ 0) "
                    f"(P: {p:.2f}%) (Q: {q:.5f}) (V: {q:.5f})"
                )
            sys.stdout.flush()

        # --- 2. FIN DE RECHERCHE ET NORME UCI ---
        best_stats = self.mcts.get_analysis_results()
        if not best_stats:
            print("bestmove 0000")
            sys.stdout.flush()
            return

        my_best = best_stats[0]
        is_black = (self.board.turn == chess_engine.Color.BLACK)
        o_f, o_r, d_f, d_r, promo = decode_move_index(self.board, my_best.move_idx, is_black)
        my_best_uci = coords_to_uci(o_f, o_r, d_f, d_r, promo)

        # --- CORRECTION 2 : GARANTIE DU BESTMOVE ---
        # Si la GUI a forcé l'arrêt (ex: changement de coup dans Nibbler)
        # OU si on est en analyse libre (target_time infini), on rend le bestmove et on coupe net.
        # On s'interdit formellement de muter l'état interne.
        if self.stop_event.is_set() or self.target_time == 1e9:
            print(f"bestmove {my_best_uci}")
            sys.stdout.flush()
            return

        # --- 3. MODE PARTIE (Lichess) : PRÉPARATION DU PONDERING ---
        # Si on arrive ici, c'est que notre tour de jeu normal est terminé naturellement (chrono écoulé).
        ponder_uci = ""

        # On pré-calcule secrètement notre coup pour voir les réponses de l'adversaire
        if self.board.move_piece(o_f, o_r, d_f, d_r, promo):
            self.mcts.update_root(my_best.move_idx)
            self.last_move_list.append(my_best_uci)

            opp_stats = self.mcts.get_analysis_results()
            if opp_stats:
                opp_best = opp_stats[0]
                opp_is_black = (self.board.turn == chess_engine.Color.BLACK)
                opp_o_f, opp_o_r, opp_d_f, opp_d_r, opp_promo = decode_move_index(self.board,
                                                                                  opp_best.move_idx,
                                                                                  opp_is_black)
                ponder_uci = coords_to_uci(opp_o_f, opp_o_r, opp_d_f, opp_d_r, opp_promo)

        if ponder_uci:
            print(f"bestmove {my_best_uci} ponder {ponder_uci}")
        else:
            print(f"bestmove {my_best_uci}")

        sys.stdout.flush()


if __name__ == "__main__":
    engine = UCIEngine()
    engine.loop()

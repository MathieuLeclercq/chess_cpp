import sys
import os
import math
import threading
import time

import chess_engine
from lib import parse_uci_to_coords, coords_to_uci, decode_move_index

# ============================================================
#                     CONFIGURATION EN DUR
# ============================================================
# Mets ici le chemin exact vers ton modèle ONNX
MODEL_PATH = (r"C:\Users\M47h1\Documents\chess_cpp\python_src"
              r"\checkpoints/2026_04_03_02h07_iter338_unsupervised.onnx")
DEFAULT_SIMULATIONS = 1200
BATCH_SIZE = 100  # On ajoute 100 simulations à la fois pour fluidifier l'affichage


# ============================================================
#                     MOTEUR UCI
# ============================================================
class UCIEngine:
    def __init__(self):
        self.board = chess_engine.Chessboard()
        self.mcts = chess_engine.MCTS(MODEL_PATH)
        self.search_thread = None
        self.stop_event = threading.Event()

    @staticmethod
    def q_to_cp(q_value):
        """
        Convertit une probabilité de victoire AlphaZero (-1.0 à 1.0)
        en centipions classiques (ex: +150) pour les interfaces.
        La formule utilise la tangente hyperbolique inverse (standard Lc0).
        """
        q = max(-0.999999, min(0.999999, q_value))
        return int(round(290.0 * math.atanh(q)))

    def loop(self):
        """Boucle principale qui écoute les commandes de la GUI (CuteChess)."""
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
                print("uciok")
                sys.stdout.flush()

            elif command == "isready":
                print("readyok")
                sys.stdout.flush()

            elif command == "setoption":
                # On ignore silencieusement les demandes de configuration
                continue

            elif command == "ucinewgame":
                self.mcts.reset_analysis()

            elif command == "position":
                self.parse_position(tokens[1:])

            elif command == "go":
                self.start_search(tokens[1:])

            elif command == "stop":
                self.stop_search()

            elif command == "quit":
                self.stop_search()
                break

    def parse_position(self, tokens):
        """Reconstruit le plateau à partir de la commande position de CuteChess."""
        self.board = chess_engine.Chessboard()

        moves_idx = -1

        if len(tokens) > 0 and tokens[0] == "startpos":
            self.board.set_startup_pieces()
            moves_idx = 2 if len(tokens) > 1 and tokens[1] == "moves" else -1

        elif len(tokens) > 0 and tokens[0] == "fen":
            # Reconstruction de la chaîne FEN (les 6 blocs suivants)
            fen_string = " ".join(tokens[1:7])
            self.board.load_fen(fen_string)
            moves_idx = 8 if len(tokens) > 7 and tokens[7] == "moves" else -1

        # Application des coups joués par-dessus la position initiale ou le FEN
        if moves_idx != -1:
            for uci_move in tokens[moves_idx:]:
                orig_f, orig_r, dest_f, dest_r, promo = parse_uci_to_coords(uci_move)
                success = self.board.move_piece(orig_f, orig_r, dest_f, dest_r, promo)

                if not success:
                    print(f"info string ERREUR C++ : Impossible de jouer le coup {uci_move}")

        self.mcts.reset_analysis()

    def start_search(self, tokens):
        """Lance la recherche MCTS avec une gestion intelligente du temps."""
        self.stop_search()
        self.stop_event.clear()

        # On initialise à None pour savoir si l'info a été reçue
        my_time = None
        my_inc = 0
        movetime_ms = None
        is_infinite = "infinite" in tokens

        is_black = (self.board.turn == chess_engine.Color.BLACK)

        # Parsing des tokens UCI
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

        # --- LOGIQUE DE DÉCISION DU TEMPS ---
        if is_infinite:
            time_limit = 1e9
        elif movetime_ms is not None:
            # Ordre explicite de Lichess (ex: coup 1 ou défi à temps fixe)
            time_limit = (movetime_ms / 1000.0) * 0.95
        elif my_time is not None:
            # Gestion de l'horloge (Rapid, Blitz, Classical)
            # Pas de limite à 6s ici, ça scalera avec my_time
            time_to_spend_ms = (my_time / 25) + (my_inc * 0.7)
            time_limit = time_to_spend_ms / 1000.0
        else:
            # Fallback si on n'a strictement aucune info sur le temps
            # On peut mettre 10s ou se baser sur DEFAULT_SIMULATIONS
            time_limit = 10.0

        self.search_thread = threading.Thread(target=self.search_worker, args=(time_limit,))
        self.search_thread.start()

    def stop_search(self):
        """Arrête proprement le thread de recherche."""
        if self.search_thread and self.search_thread.is_alive():
            self.stop_event.set()
            self.search_thread.join()

    def search_worker(self, time_limit):
        """La boucle d'analyse qui tourne en arrière-plan jusqu'à la limite ou au signal d'arrêt."""
        start_time = time.time()
        total_sims = 0

        # On définit tout de même un maximum de simulations par sécurité
        max_sims = 100_000

        while total_sims < max_sims and not self.stop_event.is_set():
            # 1. Vérification du temps écoulé
            elapsed = time.time() - start_time
            if elapsed >= time_limit:
                break

            # 2. On lance un batch de simulations
            # On réduit un peu le BATCH_SIZE en blitz pour être plus précis sur le temps
            sims_to_do = BATCH_SIZE
            self.mcts.step_analysis(self.board, sims_to_do, 1.4)
            total_sims += sims_to_do

            stats = self.mcts.get_analysis_results()
            if not stats:
                break

            # 1. On trie du meilleur au pire (stats[0] sera le meilleur)
            stats = sorted(stats, key=lambda stat: stat.visits, reverse=True)

            # 2. On itère à l'envers : du pire coup jusqu'au meilleur
            for multipv_idx in range(len(stats) - 1, -1, -1):
                move_stat = stats[multipv_idx]

                is_black = (self.board.turn == chess_engine.Color.BLACK)
                o_f, o_r, d_f, d_r, promo = decode_move_index(self.board, move_stat.move_idx,
                                                              is_black)
                uci_str = coords_to_uci(o_f, o_r, d_f, d_r, promo)

                cp_score = self.q_to_cp(move_stat.q_value)

                n = move_stat.visits
                p = move_stat.prior * 100.0
                q = move_stat.q_value

                # 3. L'affichage UCI standard
                print(
                    f"info depth {total_sims} multipv {multipv_idx + 1} "
                    f"score cp {cp_score} nodes {total_sims} pv {uci_str}"
                )

                # 4. L'affichage spécifique Lc0 pour Nibbler
                print(
                    f"info string {uci_str} (0 ) N: {n} (+ 0) "
                    f"(P: {p:.2f}%) (Q: {q:.5f}) (V: {q:.5f})"
                )

            sys.stdout.flush()

        best_stats = self.mcts.get_analysis_results()
        if best_stats:
            best = best_stats[0]
            is_black = (self.board.turn == chess_engine.Color.BLACK)
            o_f, o_r, d_f, d_r, promo = decode_move_index(self.board, best.move_idx, is_black)
            best_uci = coords_to_uci(o_f, o_r, d_f, d_r, promo)
            print(f"bestmove {best_uci}")
        else:
            print("bestmove 0000")

        sys.stdout.flush()


if __name__ == "__main__":
    engine = UCIEngine()
    engine.loop()

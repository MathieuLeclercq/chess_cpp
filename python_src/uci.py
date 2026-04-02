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
MODEL_PATH = r"C:\Users\M47h1\Documents\chess_cpp\python_src\checkpoints/2026_04_01_23h02_iter309_unsupervised.onnx"
DEFAULT_SIMULATIONS = 700
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

    def q_to_cp(self, q_value):
        """
        Convertit une probabilité de victoire AlphaZero (-1.0 à 1.0)
        en centipions classiques (ex: +150) pour les interfaces.
        La formule utilise la tangente hyperbolique inverse (standard Lc0).
        """
        # On contraint la valeur entre -0.99 et 0.99
        # pour éviter les erreurs mathématiques (division par zéro)
        q = max(-0.9999, min(0.9999, q_value))
        return int(290.0 * math.atanh(q))

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
                print("id name AlphaZero_Custom")
                print("id author Mathieu Leclercq")
                print("uciok")
                sys.stdout.flush()

            elif command == "isready":
                print("readyok")
                sys.stdout.flush()

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

        if len(tokens) > 0 and tokens[0] == "startpos":
            self.board.set_startup_pieces()
            moves_idx = 2 if len(tokens) > 1 and tokens[1] == "moves" else -1
        else:
            self.board.set_startup_pieces()
            moves_idx = -1

        if moves_idx != -1:
            for uci_move in tokens[moves_idx:]:
                orig_f, orig_r, dest_f, dest_r, promo = parse_uci_to_coords(uci_move)
                success = self.board.move_piece(orig_f, orig_r, dest_f, dest_r, promo)

                if not success:
                    print(f"info string ERREUR C++ : Impossible de jouer le coup {uci_move}")

        self.mcts.reset_analysis()

    def start_search(self, tokens):
        """Lance la recherche MCTS dans un thread séparé pour ne pas bloquer l'écoute UCI."""
        self.stop_search()  # Coupe l'ancienne recherche s'il y en avait une
        self.stop_event.clear()

        # On lance le thread d'analyse
        self.search_thread = threading.Thread(target=self.search_worker)
        self.search_thread.start()

    def stop_search(self):
        """Arrête proprement le thread de recherche."""
        if self.search_thread and self.search_thread.is_alive():
            self.stop_event.set()
            self.search_thread.join()

    def search_worker(self):
        """La boucle d'analyse qui tourne en arrière-plan."""
        total_sims = 0
        target_sims = DEFAULT_SIMULATIONS

        # On fait l'analyse par "paquets" (batch)
        # pour pouvoir interrompre la recherche et afficher l'évolution
        while total_sims < target_sims and not self.stop_event.is_set():
            sims_to_do = min(BATCH_SIZE, target_sims - total_sims)
            self.mcts.step_analysis(self.board, sims_to_do, 1.4)
            total_sims += sims_to_do

            # Récupération des résultats
            stats = self.mcts.get_analysis_results()
            if not stats:
                break

            # Affichage en temps réel des 3 meilleurs coups (MultiPV)
            num_lines = min(3, len(stats))
            for multipv_idx in range(num_lines):
                move_stat = stats[multipv_idx]

                # Conversion de l'index 0-4671 vers UCI (ex: e2e4)
                is_black = (self.board.turn == chess_engine.Color.BLACK)
                o_f, o_r, d_f, d_r, promo = decode_move_index(self.board,
                                                              move_stat.move_idx,
                                                              is_black)
                uci_str = coords_to_uci(o_f, o_r, d_f, d_r, promo)

                # Conversion Q-Value en Centipions
                cp_score = self.q_to_cp(move_stat.q_value)

                # Formatage standard UCI
                print(
                    f"info depth {total_sims} multipv {multipv_idx + 1} score cp "
                    f"{cp_score} nodes {total_sims} pv {uci_str}")

            sys.stdout.flush()

        # Fin de la recherche : on annonce le meilleur coup
        best_stats = self.mcts.get_analysis_results()
        if best_stats:
            best = best_stats[0]
            is_black = (self.board.turn == chess_engine.Color.BLACK)
            o_f, o_r, d_f, d_r, promo = decode_move_index(self.board, best.move_idx,
                                                                       is_black)
            best_uci = coords_to_uci(o_f, o_r, d_f, d_r, promo)
            print(f"bestmove {best_uci}")
        else:
            # Sécurité si aucun coup légal (mat/pat)
            print("bestmove 0000")

        sys.stdout.flush()


if __name__ == "__main__":
    engine = UCIEngine()
    engine.loop()

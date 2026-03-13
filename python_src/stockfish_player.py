import chess
import os
import chess.engine
import numpy as np


class StockfishPlayer:
    def __init__(self, path="stockfish.exe", elo=1500):
        # On vérifie si le fichier existe avant de tenter de le lancer
        if not os.path.exists(path):
            raise FileNotFoundError(f"Stockfish introuvable à l'adresse : {os.path.abspath(path)}")

        self.engine = chess.engine.SimpleEngine.popen_uci(path)
        self.engine.configure({"UCI_LimitStrength": True, "UCI_Elo": elo})

    def get_move(self, board_moves_uci):
        # On recrée un objet Board de la lib python-chess pour l'engine
        # (C'est juste pour que Stockfish comprenne la position)
        internal_board = chess.Board()
        for move_uci in board_moves_uci:
            internal_board.push_uci(move_uci)

        # On demande à Stockfish de jouer (limite en temps ou en noeuds)
        result = self.engine.play(internal_board, chess.engine.Limit(nodes=5000))

        # On récupère le coup au format UCI (ex: "e2e4")
        return result.move.uci()

    def __del__(self):
        if hasattr(self, 'engine'):
            self.engine.quit()

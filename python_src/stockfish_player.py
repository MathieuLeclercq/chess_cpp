import chess
import os
import chess.engine
import numpy as np
import multiprocessing as mp
import chess_engine
from lib import chose_move_idx, decode_move_index, parse_uci_to_coords, coords_to_uci, move_to_san


class StockfishPlayer:
    def __init__(self, path="stockfish.exe", elo=None):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Stockfish introuvable à l'adresse : {os.path.abspath(path)}")

        self.engine = chess.engine.SimpleEngine.popen_uci(path)
        self.engine.configure({"UCI_LimitStrength": True, "UCI_Elo": elo})

    def get_move(self, board_moves_uci):
        internal_board = chess.Board()
        for move_uci in board_moves_uci:
            internal_board.push_uci(move_uci)

        result = self.engine.play(internal_board, chess.engine.Limit(nodes=325_000))
        return result.move.uci()

    def __del__(self):
        if hasattr(self, 'engine'):
            try:
                self.engine.quit()
            except chess.engine.EngineTerminatedError:
                pass


def eval_worker(args):
    """
    Worker isolé pour jouer une seule partie d'évaluation.
    Instancie les moteurs localement pour la sécurité mémoire.
    """
    onnx_path, stockfish_path, mcts_sims, sf_elo, sf_nodes, is_mcts_white = args

    sf = StockfishPlayer(stockfish_path, elo=sf_elo)
    mcts = chess_engine.MCTS(onnx_path)

    board = chess_engine.Chessboard()
    board.set_startup_pieces()

    uci_moves = []
    san_moves = []

    while board.game_state == chess_engine.GameState.ONGOING:
        is_mcts_turn = (board.turn == chess_engine.Color.WHITE and is_mcts_white) or \
                       (board.turn == chess_engine.Color.BLACK and not is_mcts_white)

        if is_mcts_turn:
            pi_raw = mcts.mcts_search(board, mcts_sims, 1.4, False)
            pi = np.array(pi_raw, dtype=np.float32)

            # Température 1.0 pour forcer des ouvertures différentes (8 demi-coups)
            if len(san_moves) < 8:
                best_idx = chose_move_idx(pi, 1.0)
            else:
                best_idx = np.argmax(pi)

            is_black = (board.turn == chess_engine.Color.BLACK)
            f_o, r_o, f_d, r_d, p = decode_move_index(board, best_idx, is_black)
            move_uci = coords_to_uci(f_o, r_o, f_d, r_d, p)
        else:
            internal_board = chess.Board()
            for u in uci_moves:
                internal_board.push_uci(u)
            result = sf.engine.play(internal_board, chess.engine.Limit(nodes=sf_nodes))
            move_uci = result.move.uci()
            f_o, r_o, f_d, r_d, p = parse_uci_to_coords(move_uci)

        san = move_to_san(board, f_o, r_o, f_d, r_d, p)
        board.move_piece(f_o, r_o, f_d, r_d, p)
        san_moves.append(san)
        uci_moves.append(move_uci)

        if len(san_moves) > 250:
            break

    # Fermeture explicite et immédiate du moteur pour éviter les processus zombies
    sf.engine.quit()

    # Détermination du résultat
    if board.game_state == chess_engine.GameState.CHECKMATE:
        winner_is_white = (board.turn == chess_engine.Color.BLACK)
        if winner_is_white == is_mcts_white:
            return "win"
        else:
            return "loss"
    else:
        return "draw"


def evaluate_against_anchor(onnx_path, stockfish_path, num_games=16, mcts_sims=100, sf_elo=2500,
                            sf_nodes=200_000, num_workers=8):
    """
    Lance un pool de workers pour évaluer le modèle en parallèle.
    """
    print(f"  Évaluation contre Stockfish {sf_elo} Elo ({num_games} parties, {mcts_sims} sims)...")
    wins, draws, losses = 0, 0, 0

    # Préparation des arguments pour chaque worker
    tasks = []
    for g in range(num_games):
        is_mcts_white = (g % 2 == 0)  # Alternance stricte des couleurs
        tasks.append((onnx_path, stockfish_path, mcts_sims, sf_elo, sf_nodes, is_mcts_white))

    # Lancement du pool
    with mp.Pool(processes=min(num_workers, num_games)) as pool:
        for result in pool.imap_unordered(eval_worker, tasks):
            if result == "win":
                wins += 1
            elif result == "loss":
                losses += 1
            else:
                draws += 1

    winrate = (wins + 0.5 * draws) / num_games
    print(f"  Résultat Éval : {wins} V | {draws} N | {losses} D (Score: {winrate * 100:.1f}%)")

    return winrate, wins, draws, losses

import os
import re
import torch
from torch.utils.data import IterableDataset
import chess_engine


def encode_move(orig_f, orig_r, dest_f, dest_r, promotion_type, is_black_turn):
    """Convertit un coup en un index plat (0 à 4671). Retourne -1 en cas d'erreur de parsing."""
    if is_black_turn:
        orig_r = 7 - orig_r
        dest_r = 7 - dest_r

    df = dest_f - orig_f
    dr = dest_r - orig_r
    plane = -1

    try:
        if promotion_type in [chess_engine.PieceType.KNIGHT, chess_engine.PieceType.BISHOP,
                              chess_engine.PieceType.ROOK]:
            dir_idx = df + 1
            if promotion_type == chess_engine.PieceType.KNIGHT:
                p_idx = 0
            elif promotion_type == chess_engine.PieceType.BISHOP:
                p_idx = 1
            elif promotion_type == chess_engine.PieceType.ROOK:
                p_idx = 2
            plane = 64 + dir_idx * 3 + p_idx

        elif (abs(df) == 2 and abs(dr) == 1) or (abs(df) == 1 and abs(dr) == 2):
            knight_moves = [(1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2)]
            plane = 56 + knight_moves.index((df, dr))

        else:
            dirs = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)]
            dist = max(abs(df), abs(dr))
            dir_tuple = (df // dist, dr // dist)
            dir_idx = dirs.index(dir_tuple)
            plane = dir_idx * 7 + (dist - 1)

        return plane * 64 + orig_r * 8 + orig_f
    except ValueError:
        # Si le tuple de direction n'existe pas (ex: coup illégal échappé)
        return -1


def extract_result_from_pgn(filepath):
    """Extrait le résultat brut de la partie depuis l'en-tête PGN."""
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if line.startswith('[Result'):
                if '"1-0"' in line:
                    return 1.0
                elif '"0-1"' in line:
                    return -1.0
                elif '"1/2-1/2"' in line:
                    return 0.0
    return None


def extract_sans_from_pgn(filepath):
    """Extrait la liste des coups SAN d'un fichier PGN."""
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # DOTALL permet au point '.' d'inclure les sauts de ligne pour les commentaires multi-lignes
    content = re.sub(r'\[.*?\]', '', content, flags=re.DOTALL)
    content = re.sub(r'\{.*?\}', '', content, flags=re.DOTALL)
    content = re.sub(r'\d+\.+', '', content)
    content = re.sub(r'1-0|0-1|1/2-1/2|\*', '', content)

    return content.split()


class ChessDataset(IterableDataset):
    def __init__(self, pgn_dir):
        super().__init__()
        self.pgn_dir = pgn_dir
        self.pgn_files = [os.path.join(pgn_dir, f) for f in os.listdir(pgn_dir) if
                          f.endswith('.pgn')]

    def __iter__(self):
        for pgn_file in self.pgn_files:
            # Récupération de l'issue de la partie (le "Value Target")
            game_result = extract_result_from_pgn(pgn_file)
            if game_result is None:
                continue

            sans = extract_sans_from_pgn(pgn_file)
            if not sans:
                continue

            board = chess_engine.Chessboard()
            board.set_startup_pieces()

            for san in sans:
                tensor_numpy = board.get_alphazero_tensor()
                x = torch.from_numpy(tensor_numpy).float()

                is_black = (board.turn == chess_engine.Color.BLACK)

                success = board.move_piece_san(san)
                if not success:
                    break

                orig_f, orig_r, dest_f, dest_r, promo = board.get_last_move_data()

                target_move_index = encode_move(orig_f, orig_r, dest_f, dest_r, promo, is_black)
                if target_move_index == -1:
                    break  # Ignorer le reste de la partie si un coup est mathématiquement erroné

                y_policy = torch.tensor(target_move_index, dtype=torch.long)

                # Ajustement du résultat selon le point de vue du joueur au trait
                current_player_result = game_result if not is_black else -game_result
                y_value = torch.tensor([current_player_result], dtype=torch.float32)

                # On yield le triplet : État, Coup à jouer, Résultat de la position
                yield x, y_policy, y_value
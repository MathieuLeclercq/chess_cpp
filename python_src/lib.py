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


def decode_move_index(index, is_black):
    """Inverse de encodeMove : transforme un index (0-4671) en coordonnées de coup."""
    plane = index // 64
    remainder = index % 64
    orig_r = remainder // 8
    orig_f = remainder % 8

    df, dr = 0, 0
    promotion = chess_engine.PieceType.NONE

    if plane < 56:
        # Queen-like moves : 8 directions × 7 distances
        dir_idx = plane // 7
        dist = (plane % 7) + 1
        dirs = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)]
        df, dr = dirs[dir_idx][0] * dist, dirs[dir_idx][1] * dist

    elif plane < 64:
        # Knight moves
        knight_idx = plane - 56
        knight_moves = [(1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2)]
        df, dr = knight_moves[knight_idx]

    else:
        sub_idx = plane - 64
        dir_idx = sub_idx // 3  # 0=gauche, 1=tout droit, 2=droite
        p_idx = sub_idx % 3     # 0=knight, 1=bishop, 2=rook

        df = dir_idx - 1  # -1, 0, +1
        dr = 1             # Toujours avance d'un rang (du point de vue du joueur)

        if p_idx == 0:
            promotion = chess_engine.PieceType.KNIGHT
        elif p_idx == 1:
            promotion = chess_engine.PieceType.BISHOP
        else:
            promotion = chess_engine.PieceType.ROOK

    dest_f = orig_f + df
    dest_r = orig_r + dr

    # Dé-flip pour les noirs
    if is_black:
        orig_r = 7 - orig_r
        dest_r = 7 - dest_r

    return orig_f, orig_r, dest_f, dest_r, promotion

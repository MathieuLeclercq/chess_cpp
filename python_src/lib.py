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


def move_to_san(board, orig_f, orig_r, dest_f, dest_r, promo):
    """Génère la notation SAN d'un coup AVANT qu'il soit joué sur le board."""
    piece = board.get_square(orig_f, orig_r).get_piece()
    p_type = piece.get_type()

    # Roque
    if p_type == chess_engine.PieceType.KING and abs(orig_f - dest_f) == 2:
        san = "O-O" if dest_f == 6 else "O-O-O"
    else:
        san = ""
        piece_letters = {
            chess_engine.PieceType.KNIGHT: "N",
            chess_engine.PieceType.BISHOP: "B",
            chess_engine.PieceType.ROOK: "R",
            chess_engine.PieceType.QUEEN: "Q",
            chess_engine.PieceType.KING: "K",
        }

        is_capture = board.get_square(dest_f, dest_r).is_occupied()
        # En passant
        if p_type == chess_engine.PieceType.PAWN and abs(orig_f - dest_f) == 1 and not is_capture:
            is_capture = True

        if p_type != chess_engine.PieceType.PAWN:
            san += piece_letters[p_type]

            # Désambiguïsation
            need_file, need_rank = False, False
            for f in range(8):
                for r in range(8):
                    if f == orig_f and r == orig_r:
                        continue
                    sq = board.get_square(f, r)
                    if not sq.is_occupied():
                        continue
                    if sq.get_piece().get_type() != p_type or sq.get_piece().get_color() != piece.get_color():
                        continue
                    for m in board.get_naive_legal_moves(f, r):
                        if m.get_dest_square().get_file() == dest_f and m.get_dest_square().get_rank() == dest_r:
                            if f == orig_f:
                                need_rank = True
                            else:
                                need_file = True

            if need_file:
                san += chr(ord('a') + orig_f)
            if need_rank:
                san += chr(ord('1') + orig_r)
        else:
            if is_capture:
                san += chr(ord('a') + orig_f)

        if is_capture:
            san += "x"

        san += chr(ord('a') + dest_f) + chr(ord('1') + dest_r)

        # Promotion
        promo_letters = {
            chess_engine.PieceType.QUEEN: "Q",
            chess_engine.PieceType.ROOK: "R",
            chess_engine.PieceType.BISHOP: "B",
            chess_engine.PieceType.KNIGHT: "N",
        }
        if promo in promo_letters:
            san += "=" + promo_letters[promo]

    return san


def print_pgn(board, san_move_list):
    # Après la boucle while, avant pygame.quit()
    pgn = ""
    for i, san in enumerate(san_move_list):
        if i % 2 == 0:
            pgn += f"{i // 2 + 1}. "
        pgn += san + " "

    results = {
        chess_engine.GameState.CHECKMATE: "1-0" if board.turn == chess_engine.Color.BLACK else "0-1",
        chess_engine.GameState.STALEMATE: "1/2-1/2",
        chess_engine.GameState.DRAW_REPETITION: "1/2-1/2",
        chess_engine.GameState.DRAW_50_MOVES: "1/2-1/2",
    }
    pgn += results.get(board.game_state, "*")

    print("\n===== PGN =====")
    print(pgn)
    print("===============\n")

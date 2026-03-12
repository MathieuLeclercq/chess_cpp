import os
import pygame
import chess_engine

# ============================================================
#                     RENDU GRAPHIQUE
# ============================================================

WHITE_COLOR = (240, 217, 181)
BLACK_COLOR = (181, 136, 99)
WIDTH, HEIGHT = 800, 800
SQUARE_SIZE = WIDTH // 8
HIGHLIGHT_COLOR = (186, 202, 68)
RED_HIGHLIGHT_LIGHT = (235, 105, 95)
RED_HIGHLIGHT_DARK = (215, 75, 65)
DOT_COLOR = (130, 151, 105)
LAST_MOVE_COLOR = (205, 210, 106)
IMAGES = {}


def pygame_init():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("AlphaZero Maison — Jouer contre l'IA")
    clock = pygame.time.Clock()
    return screen, clock

def rendu(screen,
          board,
          selected_square,
          current_legal_moves,
          clock,
          dragging=False,
          drag_pos=(0, 0),
          red_squares=None,
          perspective=chess_engine.Color.WHITE  # Ajout du paramètre
          ):
    if red_squares is None:
        red_squares = set()

    # Note : Toutes les fonctions ci-dessous doivent maintenant accepter 'perspective'
    draw_board(screen, perspective)
    draw_last_move(screen, board, perspective)
    draw_red_squares(screen, red_squares, perspective)
    draw_highlights(screen, selected_square, current_legal_moves, perspective)

    dragged_square = selected_square if dragging else None
    draw_pieces(screen, board, dragged_square, perspective)

    # La pièce qui glisse suit la souris (pas besoin de flip pour drag_pos)
    draw_dragged_piece(screen, board, selected_square, dragging, drag_pos)

    draw_game_over(screen, board)
    pygame.display.flip()
    clock.tick(60)
    return clock


def get_screen_coords(file, rank, perspective):
    """Calcule les pixels X, Y selon la vue (Blancs ou Noirs)."""
    if perspective == chess_engine.Color.WHITE:
        x = file * SQUARE_SIZE
        y = (7 - rank) * SQUARE_SIZE
    else:
        x = (7 - file) * SQUARE_SIZE
        y = rank * SQUARE_SIZE
    return x, y


def load_images():
    pieces = {
        (chess_engine.Color.WHITE, chess_engine.PieceType.PAWN): "white-pawn.png",
        (chess_engine.Color.WHITE, chess_engine.PieceType.ROOK): "white-rook.png",
        (chess_engine.Color.WHITE, chess_engine.PieceType.KNIGHT): "white-knight.png",
        (chess_engine.Color.WHITE, chess_engine.PieceType.BISHOP): "white-bishop.png",
        (chess_engine.Color.WHITE, chess_engine.PieceType.QUEEN): "white-queen.png",
        (chess_engine.Color.WHITE, chess_engine.PieceType.KING): "white-king.png",
        (chess_engine.Color.BLACK, chess_engine.PieceType.PAWN): "black-pawn.png",
        (chess_engine.Color.BLACK, chess_engine.PieceType.ROOK): "black-rook.png",
        (chess_engine.Color.BLACK, chess_engine.PieceType.KNIGHT): "black-knight.png",
        (chess_engine.Color.BLACK, chess_engine.PieceType.BISHOP): "black-bishop.png",
        (chess_engine.Color.BLACK, chess_engine.PieceType.QUEEN): "black-queen.png",
        (chess_engine.Color.BLACK, chess_engine.PieceType.KING): "black-king.png",
    }
    for key, filename in pieces.items():
        path = os.path.join("assets", filename)
        if os.path.exists(path):
            img = pygame.image.load(path).convert_alpha()
            IMAGES[key] = pygame.transform.smoothscale(img, (SQUARE_SIZE, SQUARE_SIZE))


def draw_board(screen, perspective):
    for rank in range(8):
        for file in range(8):
            dx, dy = get_screen_coords(file, rank, perspective)
            color = WHITE_COLOR if (rank + file) % 2 != 0 else BLACK_COLOR
            pygame.draw.rect(screen, color, pygame.Rect(dx, dy, SQUARE_SIZE, SQUARE_SIZE))


def draw_last_move(screen, board, perspective):
    try:
        orig_f, orig_r, dest_f, dest_r, _ = board.get_last_move_data()
        if orig_f == -1: return

        for f, r in [(orig_f, orig_r), (dest_f, dest_r)]:
            dx, dy = get_screen_coords(f, r, perspective)
            s = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE))
            s.set_alpha(90)
            s.fill(LAST_MOVE_COLOR)
            screen.blit(s, (dx, dy))
    except Exception:
        pass


def draw_red_squares(screen, red_squares, perspective):
    for file, rank in red_squares:
        dx, dy = get_screen_coords(file, rank, perspective)
        color = RED_HIGHLIGHT_LIGHT if (rank + file) % 2 != 0 else RED_HIGHLIGHT_DARK
        pygame.draw.rect(screen, color, pygame.Rect(dx, dy, SQUARE_SIZE, SQUARE_SIZE))


def draw_highlights(screen, selected_square, legal_moves, perspective):
    if selected_square is not None:
        f_sel, r_sel = selected_square
        dx_sel, dy_sel = get_screen_coords(f_sel, r_sel, perspective)

        s = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE))
        s.set_alpha(100)
        s.fill(HIGHLIGHT_COLOR)
        screen.blit(s, (dx_sel, dy_sel))

        for move in legal_moves:
            d_file = move.get_dest_square().get_file()
            d_rank = move.get_dest_square().get_rank()
            dx, dy = get_screen_coords(d_file, d_rank, perspective)

            cx = dx + SQUARE_SIZE // 2
            cy = dy + SQUARE_SIZE // 2
            pygame.draw.circle(screen, DOT_COLOR, (cx, cy), SQUARE_SIZE // 6)


def draw_pieces(screen, board, dragged_square, perspective):
    for rank in range(8):
        for file in range(8):
            if dragged_square == (file, rank):
                continue

            sq = board.get_square(file, rank)
            if sq.is_occupied():
                dx, dy = get_screen_coords(file, rank, perspective)
                key = (sq.get_piece().get_color(), sq.get_piece().get_type())
                if key in IMAGES:
                    screen.blit(IMAGES[key], (dx, dy))


def draw_dragged_piece(screen, board, selected_square, dragging, drag_pos):
    if dragging and selected_square is not None:
        file, rank = selected_square
        sq = board.get_square(file, rank)
        if sq.is_occupied():
            key = (sq.get_piece().get_color(), sq.get_piece().get_type())
            if key in IMAGES:
                image = IMAGES[key]
                img_rect = image.get_rect(center=drag_pos)
                screen.blit(image, img_rect)


def draw_game_over(screen, board):
    """Affiche un bandeau si la partie est terminée."""
    state = board.game_state
    if state == chess_engine.GameState.ONGOING:
        return

    messages = {
        chess_engine.GameState.CHECKMATE: "Échec et mat !",
        chess_engine.GameState.STALEMATE: "Pat — Nulle",
        chess_engine.GameState.DRAW_REPETITION: "Nulle par répétition",
        chess_engine.GameState.DRAW_50_MOVES: "Nulle — règle des 50 coups",
        chess_engine.GameState.DRAW_INSUFF_MATERIAL: "Nulle - Manque de matériel"
    }
    text = messages.get(state, "Partie terminée")

    font = pygame.font.SysFont("Arial", 48, bold=True)
    overlay = pygame.Surface((WIDTH, HEIGHT))
    overlay.set_alpha(160)
    overlay.fill((0, 0, 0))
    screen.blit(overlay, (0, 0))

    rendered = font.render(text, True, (255, 255, 255))
    rect = rendered.get_rect(center=(WIDTH // 2, HEIGHT // 2))
    screen.blit(rendered, rect)

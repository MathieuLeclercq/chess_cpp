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
          clock
          ):
    draw_board(screen)
    draw_last_move(screen, board)
    draw_highlights(screen, selected_square, current_legal_moves)
    draw_pieces(screen, board)
    draw_game_over(screen, board)
    pygame.display.flip()
    clock.tick(60)
    return clock


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


def draw_board(screen):
    for rank in range(8):
        for file in range(8):
            dy = (7 - rank) * SQUARE_SIZE
            dx = file * SQUARE_SIZE
            color = WHITE_COLOR if (rank + file) % 2 != 0 else BLACK_COLOR
            pygame.draw.rect(screen, color, pygame.Rect(dx, dy, SQUARE_SIZE, SQUARE_SIZE))


def draw_last_move(screen, board):
    """Surligne les cases du dernier coup joué."""
    # if board.getMoveHistory is None:
    #     return
    try:
        orig_f, orig_r, dest_f, dest_r, _ = board.get_last_move_data()
        if orig_f == -1:
            return
        for f, r in [(orig_f, orig_r), (dest_f, dest_r)]:
            s = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE))
            s.set_alpha(90)
            s.fill(LAST_MOVE_COLOR)
            screen.blit(s, (f * SQUARE_SIZE, (7 - r) * SQUARE_SIZE))
    except Exception:
        pass


def draw_highlights(screen, selected_square, legal_moves):
    if selected_square is not None:
        file, rank = selected_square
        s = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE))
        s.set_alpha(100)
        s.fill(HIGHLIGHT_COLOR)
        screen.blit(s, (file * SQUARE_SIZE, (7 - rank) * SQUARE_SIZE))

        for move in legal_moves:
            d_file = move.get_dest_square().get_file()
            d_rank = move.get_dest_square().get_rank()
            cx = d_file * SQUARE_SIZE + SQUARE_SIZE // 2
            cy = (7 - d_rank) * SQUARE_SIZE + SQUARE_SIZE // 2
            pygame.draw.circle(screen, DOT_COLOR, (cx, cy), SQUARE_SIZE // 6)


def draw_pieces(screen, board):
    for rank in range(8):
        for file in range(8):
            sq = board.get_square(file, rank)
            if sq.is_occupied():
                key = (sq.get_piece().get_color(), sq.get_piece().get_type())
                if key in IMAGES:
                    screen.blit(IMAGES[key], (file * SQUARE_SIZE, (7 - rank) * SQUARE_SIZE))


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

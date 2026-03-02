import warnings

warnings.filterwarnings("ignore", category=UserWarning, message="pkg_resources is deprecated")

import pygame
import sys
import os
import chess_engine

# Constantes
WIDTH, HEIGHT = 800, 800
SQUARE_SIZE = WIDTH // 8
WHITE_COLOR = (240, 217, 181)
BLACK_COLOR = (181, 136, 99)
HIGHLIGHT_COLOR = (186, 202, 68)  # Couleur pour la case sélectionnée
DOT_COLOR = (130, 151, 105)  # Couleur pour les coups légaux

IMAGES = {}


def load_images():
    """Charge les images depuis gui/assets et les associe aux enums C++."""
    # Fais correspondre tes noms de fichiers ici si nécessaire
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
        else:
            print(f"Attention: Image manquante -> {path}")


def draw_board(screen):
    """Dessine les cases de l'échiquier."""
    for rank in range(8):
        for file in range(8):
            display_y = (7 - rank) * SQUARE_SIZE
            display_x = file * SQUARE_SIZE
            color = WHITE_COLOR if (rank + file) % 2 != 0 else BLACK_COLOR
            pygame.draw.rect(screen, color,
                             pygame.Rect(display_x, display_y, SQUARE_SIZE, SQUARE_SIZE))


def draw_highlights(screen, selected_square, legal_moves):
    """Met en surbrillance la pièce sélectionnée et ses destinations possibles."""
    if selected_square is not None:
        file, rank = selected_square
        display_y = (7 - rank) * SQUARE_SIZE
        display_x = file * SQUARE_SIZE

        # Surligner la case d'origine
        s = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE))
        s.set_alpha(100)  # Transparence
        s.fill(HIGHLIGHT_COLOR)
        screen.blit(s, (display_x, display_y))

        # Dessiner des cercles pour les coups légaux
        for move in legal_moves:
            dest_sq = move.get_dest_square()
            d_file = dest_sq.get_file()
            d_rank = dest_sq.get_rank()

            center_x = d_file * SQUARE_SIZE + SQUARE_SIZE // 2
            center_y = (7 - d_rank) * SQUARE_SIZE + SQUARE_SIZE // 2
            pygame.draw.circle(screen, DOT_COLOR, (center_x, center_y), SQUARE_SIZE // 6)


def draw_pieces(screen, board):
    """Interroge le moteur C++ et dessine les pièces."""
    for rank in range(8):
        for file in range(8):
            square = board.get_square(file, rank)
            if square.is_occupied():
                piece = square.get_piece()
                key = (piece.get_color(), piece.get_type())
                if key in IMAGES:
                    display_y = (7 - rank) * SQUARE_SIZE
                    display_x = file * SQUARE_SIZE
                    screen.blit(IMAGES[key], (display_x, display_y))


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Chess Engine - C++ Backend")
    clock = pygame.time.Clock()

    load_images()

    # Initialisation du backend C++
    board = chess_engine.Chessboard()
    board.set_startup_pieces()

    # Variables d'état
    running = True
    selected_square = None  # Tuple (file, rank)
    current_legal_moves = []  # Liste d'objets Move

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.MOUSEBUTTONDOWN:
                x, y = pygame.mouse.get_pos()
                clicked_file = x // SQUARE_SIZE
                clicked_rank = 7 - (y // SQUARE_SIZE)

                # Si aucune pièce n'est sélectionnée
                if selected_square is None:
                    sq = board.get_square(clicked_file, clicked_rank)
                    if sq.is_occupied():
                        piece_color = sq.get_piece().get_color()
                        expected_color = board.turn

                        if piece_color == expected_color:
                            selected_square = (clicked_file, clicked_rank)
                            current_legal_moves = board.get_legal_moves(clicked_file, clicked_rank)

                # Si une pièce est déjà sélectionnée
                else:
                    # On vérifie si la case cliquée correspond à une destination d'un coup légal
                    valid_move = None
                    promotion_type = chess_engine.PieceType.NONE

                    for move in current_legal_moves:
                        if (move.get_dest_square().get_file() == clicked_file and
                                move.get_dest_square().get_rank() == clicked_rank):
                            valid_move = move
                            # Choix par défaut arbitraire pour la GUI : promotion auto en Dame
                            if move.get_promotion() == chess_engine.PieceType.QUEEN:
                                promotion_type = chess_engine.PieceType.QUEEN
                                break

                    if valid_move is not None:
                        # Exécution du coup dans le moteur C++
                        orig_file, orig_rank = selected_square
                        success = board.move_piece(orig_file, orig_rank, clicked_file, clicked_rank,
                                                   promotion_type)
                        print(board.game_state)


                    # Peu importe le résultat du clic, on désélectionne
                    selected_square = None
                    current_legal_moves = []

        # Rendu graphique
        draw_board(screen)
        draw_highlights(screen, selected_square, current_legal_moves)
        draw_pieces(screen, board)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
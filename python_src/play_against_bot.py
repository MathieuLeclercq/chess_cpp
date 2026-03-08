"""
Script pour jouer contre le modèle AlphaZero entraîné.
Utilise le moteur C++ via pybind11 + le réseau de neurones pour l'IA.
"""

import warnings
warnings.filterwarnings("ignore", category=UserWarning, message="pkg_resources is deprecated")
warnings.filterwarnings("ignore", message=".*weights_only=False.*")
import pygame
import sys

import chess_engine
from lib_gui import (
    SQUARE_SIZE,
    pygame_init,
    load_images,
    rendu
)
from lib import (
    move_to_san, print_pgn, load_supervised_model,
    ai_pick_move_instant)


# ============================================================
#                     CONFIGURATION
# ============================================================


# Couleur jouée par l'humain (WHITE ou BLACK)
HUMAN_COLOR = chess_engine.Color.WHITE

# Chemin vers le checkpoint Lightning
CHECKPOINT_PATH = "checkpoints/supervised_best_03_07.ckpt"

# Architecture (doit correspondre à l'entraînement)
NUM_RES_BLOCKS = 10
NUM_FILTERS = 128

# Température pour le sampling (0 = déterministe, 0.5 = léger aléa)
TEMPERATURE = 0.1

# ============================================================
#                     BOUCLE PRINCIPALE
# ============================================================

def main():
    screen, clock = pygame_init()
    load_images()

    # Chargement du modèle
    device = "cuda"
    model = load_supervised_model(CHECKPOINT_PATH, NUM_RES_BLOCKS, NUM_FILTERS, device)

    # Initialisation du plateau
    board = chess_engine.Chessboard()
    board.set_startup_pieces()
    san_moves = []

    running = True
    selected_square = None
    current_legal_moves = []
    game_over = False

    while running:
        is_human_turn = (board.turn == HUMAN_COLOR)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            # Clic humain uniquement pendant son tour
            elif event.type == pygame.MOUSEBUTTONDOWN and is_human_turn and not game_over:
                x, y = pygame.mouse.get_pos()
                clicked_file = x // SQUARE_SIZE
                clicked_rank = 7 - (y // SQUARE_SIZE)

                if selected_square is None:
                    sq = board.get_square(clicked_file, clicked_rank)
                    if sq.is_occupied() and sq.get_piece().get_color() == board.turn:
                        selected_square = (clicked_file, clicked_rank)
                        current_legal_moves = board.get_legal_moves(
                            clicked_file, clicked_rank)
                else:
                    valid_move = None
                    promotion_type = chess_engine.PieceType.NONE

                    for move in current_legal_moves:
                        if (move.get_dest_square().get_file() == clicked_file and
                                move.get_dest_square().get_rank() == clicked_rank):
                            valid_move = move
                            if move.get_promotion() == chess_engine.PieceType.QUEEN:
                                promotion_type = chess_engine.PieceType.QUEEN
                                break

                    if valid_move is not None:
                        orig_f, orig_r = selected_square
                        san = move_to_san(board, orig_f, orig_r, clicked_file, clicked_rank,
                                          promotion_type)
                        success = board.move_piece(orig_f, orig_r, clicked_file, clicked_rank,
                                                   promotion_type)
                        if success:
                            if board.game_state == chess_engine.GameState.CHECKMATE:
                                san += "#"
                            elif board.is_in_check():
                                san += "+"
                            san_moves.append(san)

                            if board.game_state != chess_engine.GameState.ONGOING:
                                game_over = True
                        if board.game_state != chess_engine.GameState.ONGOING:
                            game_over = True

                    selected_square = None
                    current_legal_moves = []

        # Tour de l'IA
        if not is_human_turn and not game_over:
            result = ai_pick_move_instant(board, model, device, TEMPERATURE)
            if result is not None:
                orig_f, orig_r, dest_f, dest_r, promo = result
                san = move_to_san(board, orig_f, orig_r, dest_f, dest_r, promo)
                board.move_piece(orig_f, orig_r, dest_f, dest_r, promo)
                if board.game_state == chess_engine.GameState.CHECKMATE:
                    san += "#"
                elif board.is_in_check():
                    san += "+"
                san_moves.append(san)

        # Rendu
        clock = rendu(
            screen,
            board,
            selected_square,
            current_legal_moves,
            clock
        )

    print_pgn(board, san_moves)
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()

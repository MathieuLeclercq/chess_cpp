import warnings
import threading
import pygame
import sys
import numpy as np

warnings.filterwarnings("ignore", category=UserWarning, message="pkg_resources is deprecated")
warnings.filterwarnings("ignore", message=".*weights_only=False.*")

import chess_engine
from mcts import MCTS
from lib_gui import (
    SQUARE_SIZE,
    pygame_init,
    load_images,
    rendu
)
from lib import (decode_move_index, move_to_san, print_pgn,
                 load_unsupervised_model, load_supervised_model)

# ============================================================
#                     CONFIGURATION
# ============================================================

HUMAN_COLOR = chess_engine.Color.WHITE
CHECKPOINT_PATH = "checkpoints/supervised_best_03_07.ckpt"

NUM_RES_BLOCKS = 10
NUM_FILTERS = 128
NUM_SIMULATIONS = 1000


# ============================================================
#                     FONCTION WORKER (THREAD)
# ============================================================

def mcts_worker(san_moves_copy, model, device, num_simulations, result_container):
    """
    Exécute le MCTS en arrière-plan sur une copie indépendante du plateau
    pour éviter les conflits de mémoire avec le thread principal (Pygame).
    """
    # 1. Recréation de l'état du plateau
    temp_board = chess_engine.Chessboard()
    temp_board.set_startup_pieces()
    for move in san_moves_copy:
        temp_board.move_piece_san(move)

    # 2. Lancement de la recherche
    result = MCTS.ai_pick_move_mcts(temp_board, model, device, num_simulations)

    # 3. Stockage du résultat (passage par référence via la liste)
    result_container.append(result)


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

    # Variables de gestion du Threading
    ai_thinking = False
    ai_result_container = []

    running = True
    selected_square = None
    current_legal_moves = []
    game_over = False

    while running:
        is_human_turn = (board.turn == HUMAN_COLOR)

        # 1. Gestion des événements (souris, clavier)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            # Clic humain uniquement pendant son tour ET si l'IA ne réfléchit pas
            elif (event.type == pygame.MOUSEBUTTONDOWN and
                  is_human_turn and
                  not game_over and
                  not ai_thinking):
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

        # 2. Tour de l'IA (Non bloquant)
        if not is_human_turn and not game_over:

            # A. Démarrage de la réflexion
            if not ai_thinking:
                ai_thinking = True
                ai_result_container.clear()

                # On lance le worker dans un thread séparé
                thread = threading.Thread(
                    target=mcts_worker,
                    args=(san_moves.copy(), model, device, NUM_SIMULATIONS, ai_result_container)
                )
                thread.start()

            # B. Récupération du résultat (une fois le thread terminé)
            elif len(ai_result_container) > 0:
                result = ai_result_container.pop()
                if result is not None:
                    orig_f, orig_r, dest_f, dest_r, promo = result
                    san = move_to_san(board, orig_f, orig_r, dest_f, dest_r, promo)
                    board.move_piece(orig_f, orig_r, dest_f, dest_r, promo)

                    if board.game_state == chess_engine.GameState.CHECKMATE:
                        san += "#"
                    elif board.is_in_check():
                        san += "+"
                    san_moves.append(san)

                if board.game_state != chess_engine.GameState.ONGOING:
                    game_over = True

                ai_thinking = False

        # 3. Rendu (s'exécute à 60 FPS sans interruption)
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

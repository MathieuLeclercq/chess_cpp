import warnings
import threading
import pygame
import sys
import numpy as np

warnings.filterwarnings("ignore", category=UserWarning, message="pkg_resources is deprecated")
warnings.filterwarnings("ignore", message=".*weights_only=False.*")

import chess_engine
from lib_gui import (
    SQUARE_SIZE,
    pygame_init,
    load_images,
    rendu
)
from lib import (move_to_san, print_pgn, decode_move_index)

# ============================================================
#                     CONFIGURATION
# ============================================================

HUMAN_COLOR = chess_engine.Color.WHITE
CHECKPOINT_PATH = "checkpoints/2026_03_10_20h08_iter2_unsupervised.onnx"

NUM_SIMULATIONS = 1200


# ============================================================
#                     FONCTION WORKER (THREAD)
# ============================================================

def mcts_worker(san_moves_copy, mcts_engine, num_simulations, result_container):
    """
    Exécute le MCTS en arrière-plan sur une copie indépendante du plateau
    pour éviter les conflits de mémoire avec le thread principal (Pygame).
    """
    # 1. Recréation de l'état du plateau
    temp_board = chess_engine.Chessboard()
    temp_board.set_startup_pieces()
    for move in san_moves_copy:
        temp_board.move_piece_san(move)

    # 2. Lancement de la recherche C++ / ONNX
    # On désactive le bruit de Dirichlet (False) car on joue un vrai match
    pi_raw = mcts_engine.mcts_search(temp_board, num_simulations, 1.4, False)
    pi = np.array(pi_raw, dtype=np.float32)

    # 3. Sélection du meilleur coup (celui avec le plus de visites MCTS)
    best_idx = int(np.argmax(pi))

    # 4. Décodage et retour au thread principal
    is_black = (temp_board.turn == chess_engine.Color.BLACK)
    orig_f, orig_r, dest_f, dest_r, promo = decode_move_index(temp_board, best_idx, is_black)

    # Affichage optionnel dans la console
    best_prob = pi[best_idx] * 100
    san = move_to_san(temp_board, orig_f, orig_r, dest_f, dest_r, promo)
    print(f"\n[AI] Coup choisi : {san} (Confiance : {best_prob:.1f}%)")

    # Stockage du résultat (passage par référence via la liste)
    result_container.append((orig_f, orig_r, dest_f, dest_r, promo))


# ============================================================
#                     BOUCLE PRINCIPALE
# ============================================================

def main():
    screen, clock = pygame_init()
    load_images()

    print(f"Chargement du moteur MCTS avec {CHECKPOINT_PATH}...")
    mcts_engine = chess_engine.MCTS(CHECKPOINT_PATH)

    board = chess_engine.Chessboard()
    board.set_startup_pieces()
    san_moves = []

    ai_thinking = False
    ai_result_container = []

    running = True
    selected_square = None
    current_legal_moves = []
    game_over = False

    # Nouvelles variables pour l'UI
    dragging = False
    drag_pos = (0, 0)
    red_squares = set()

    while running:
        is_human_turn = (board.turn == HUMAN_COLOR)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            # --- CLIC DROIT : Surlignage rouge ---
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                x, y = pygame.mouse.get_pos()
                clicked_file = x // SQUARE_SIZE
                clicked_rank = 7 - (y // SQUARE_SIZE)
                sq = (clicked_file, clicked_rank)

                # Toggle (ajoute si n'y est pas, retire si y est)
                if sq in red_squares:
                    red_squares.remove(sq)
                else:
                    red_squares.add(sq)

            # --- CLIC GAUCHE (DOWN) : Saisir ou Cliquer-pour-bouger ---
            elif (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and
                  is_human_turn and not game_over and not ai_thinking):

                red_squares.clear()  # Nettoie les cases rouges quand on interagit

                x, y = pygame.mouse.get_pos()
                clicked_file = x // SQUARE_SIZE
                clicked_rank = 7 - (y // SQUARE_SIZE)
                clicked_sq = (clicked_file, clicked_rank)

                if selected_square is None:
                    # Cas 1 : Aucune pièce sélectionnée, on en saisit une
                    sq = board.get_square(clicked_file, clicked_rank)
                    if sq.is_occupied() and sq.get_piece().get_color() == board.turn:
                        selected_square = clicked_sq
                        current_legal_moves = board.get_legal_moves(clicked_file, clicked_rank)
                        dragging = True
                        drag_pos = (x, y)
                else:
                    # Cas 2 : Une pièce est déjà sélectionnée (Click-to-Click)
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
                        # C'est un coup valide via clic
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
                            if board.game_state != chess_engine.GameState.ONGOING: game_over = True

                        selected_square = None
                        current_legal_moves = []
                    else:
                        # Clic invalide. A-t-on cliqué sur une AUTRE de nos pièces ?
                        sq = board.get_square(clicked_file, clicked_rank)
                        if sq.is_occupied() and sq.get_piece().get_color() == board.turn:
                            # On change la sélection
                            selected_square = clicked_sq
                            current_legal_moves = board.get_legal_moves(clicked_file,
                                                                        clicked_rank)
                            dragging = True
                            drag_pos = (x, y)
                        else:
                            # Clic dans le vide : on annule la sélection
                            selected_square = None
                            current_legal_moves = []

            # --- SOURIS (MOTION) : Faire glisser ---
            elif event.type == pygame.MOUSEMOTION:
                if dragging:
                    drag_pos = event.pos

            # --- CLIC GAUCHE (UP) : Relâcher la pièce (Drag-and-Drop) ---
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if dragging:
                    dragging = False
                    x, y = event.pos
                    clicked_file = x // SQUARE_SIZE
                    clicked_rank = 7 - (y // SQUARE_SIZE)

                    # Si on lâche sur la case de départ, on garde la sélection (permet le click-to-click ensuite)
                    if (clicked_file, clicked_rank) == selected_square:
                        pass
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
                                if board.game_state != chess_engine.GameState.ONGOING: game_over = True

                            selected_square = None
                            current_legal_moves = []
                        else:
                            pass

        # 2. Tour de l'IA (inchangé)
        if not is_human_turn and not game_over:
            if not ai_thinking:
                ai_thinking = True
                ai_result_container.clear()
                thread = threading.Thread(
                    target=mcts_worker,
                    args=(san_moves.copy(), mcts_engine, NUM_SIMULATIONS, ai_result_container)
                )
                thread.start()

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

        # 3. Appel de rendu mis à jour
        clock = rendu(
            screen,
            board,
            selected_square,
            current_legal_moves,
            clock,
            dragging,  # NOUVEAU
            drag_pos,  # NOUVEAU
            red_squares  # NOUVEAU
        )

    print_pgn(board, san_moves)
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()

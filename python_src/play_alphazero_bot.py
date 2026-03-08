import warnings

warnings.filterwarnings("ignore", category=UserWarning, message="pkg_resources is deprecated")
warnings.filterwarnings("ignore", message=".*weights_only=False.*")
import pygame
import sys
import os

import numpy as np
import torch

import chess_engine
from model import ChessNet
from mcts import MCTS  # NOUVEL IMPORT
from lib_gui import (
    SQUARE_SIZE,
    pygame_init,
    load_images,
    rendu
)
from lib import decode_move_index, move_to_san, print_pgn

# ============================================================
#                     CONFIGURATION
# ============================================================

HUMAN_COLOR = chess_engine.Color.WHITE

# Met à jour ce chemin vers ton checkpoint issu du self-play
CHECKPOINT_PATH = "checkpoints/selfplay_iter3.pt"

NUM_RES_BLOCKS = 10
NUM_FILTERS = 128

# Règle le nombre de simulations selon la puissance de ton CPU/GPU
NUM_SIMULATIONS = 400


# ============================================================
#                     CHARGEMENT DU MODÈLE
# ============================================================

def load_model(checkpoint_path, num_res_blocks, num_filters):
    """Charge le modèle depuis un checkpoint standard PyTorch."""
    os.environ["TORCH_SKIP_WEIGHTS_ONLY_WARNING"] = "1"
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # 1. Instanciation de l'architecture vide
    model = ChessNet(num_res_blocks=num_res_blocks, num_filters=num_filters)

    # 2. Chargement du fichier
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)

    # 3. Injection des poids
    # Note : Ton script de self-play sauvegarde les poids sous la clé "model_state_dict"
    model.load_state_dict(checkpoint["model_state_dict"])

    model.to(device)
    model.eval()

    print(f"Modèle chargé depuis {checkpoint_path} (device: {device})")
    return model, device


# ============================================================
#                     LOGIQUE DE L'IA
# ============================================================

def ai_pick_move(board, model, device, num_simulations):
    """
    Utilise le MCTS pour choisir un coup.
    """
    legal_indices = board.get_legal_move_indices()
    if not legal_indices:
        return None

    # Lancement de l'arbre de recherche. add_dirichlet=False pour l'inférence.
    pi, _ = MCTS.mcts_search(
        board, model, device, num_simulations=num_simulations, add_dirichlet=False)

    # En mode compétition, on joue toujours le coup le plus exploré par le MCTS
    best_idx = np.argmax(pi)

    # Décodage
    is_black = (board.turn == chess_engine.Color.BLACK)
    orig_f, orig_r, dest_f, dest_r, promo = decode_move_index(board, best_idx, is_black)

    print(f"IA joue: ({orig_f},{orig_r}) -> ({dest_f},{dest_r}), promo={promo}")

    return orig_f, orig_r, dest_f, dest_r, promo


# ============================================================
#                     BOUCLE PRINCIPALE
# ============================================================

def main():
    screen, clock = pygame_init()
    load_images()

    # Chargement du modèle
    model, device = load_model(CHECKPOINT_PATH, NUM_RES_BLOCKS, NUM_FILTERS)

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

            result = ai_pick_move(board, model, device, NUM_SIMULATIONS)
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

"""
Script pour jouer contre le modèle AlphaZero entraîné.
Utilise le moteur C++ via pybind11 + le réseau de neurones pour l'IA.
"""

import warnings
warnings.filterwarnings("ignore", category=UserWarning, message="pkg_resources is deprecated")
warnings.filterwarnings("ignore", message=".*weights_only=False.*")
import pygame
import sys
import os

import numpy as np
import torch

import chess_engine
from train_supervised import AlphaZeroLightning
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
#                     CHARGEMENT DU MODÈLE
# ============================================================

def load_model(checkpoint_path, num_res_blocks, num_filters):
    """Charge le modèle depuis un checkpoint Lightning."""
    os.environ["TORCH_SKIP_WEIGHTS_ONLY_WARNING"] = "1"
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    lit_model = AlphaZeroLightning.load_from_checkpoint(
        checkpoint_path,
        num_res_blocks=num_res_blocks,
        num_filters=num_filters,
    )
    model = lit_model.model
    model.to(device)
    model.eval()
    print(f"Modèle chargé depuis {checkpoint_path} (device: {device})")
    return model, device


# ============================================================
#                     LOGIQUE DE L'IA
# ============================================================

def ai_pick_move(board, model, device, temperature=0.1):
    """
    Utilise le réseau pour choisir un coup.
    1. Encode la position en tensor 119×8×8
    2. Forward pass → policy logits + value
    3. Masque les coups illégaux
    4. Sélectionne le meilleur coup (avec température optionnelle)
    5. Décode l'index en coordonnées
    """
    # Tensor d'entrée
    tensor_np = board.get_alphazero_tensor()
    x = torch.from_numpy(tensor_np).float().unsqueeze(0).to(device)  # [1, 119, 8, 8]

    # Indices des coups légaux (déjà encodés par le moteur C++)
    legal_indices = board.get_legal_move_indices()
    if not legal_indices:
        return None

    # Inférence
    with torch.no_grad():
        p_logits, v_pred = model(x)

    p_logits = p_logits.squeeze(0).cpu().numpy()  # [4672]
    value = v_pred.item()

    # Masquage : on met -inf partout sauf les coups légaux
    mask = np.full(4672, -np.inf)
    for idx in legal_indices:
        mask[idx] = p_logits[idx]

    # Sélection du coup
    if temperature <= 0:
        best_idx = legal_indices[np.argmax(mask[legal_indices])]
    else:
        # Softmax avec température sur les coups légaux uniquement
        legal_logits = np.array([p_logits[i] for i in legal_indices])
        legal_logits = legal_logits / temperature
        legal_logits -= legal_logits.max()  # stabilité numérique
        probs = np.exp(legal_logits)
        probs /= probs.sum()
        chosen = np.random.choice(len(legal_indices), p=probs)
        best_idx = legal_indices[chosen]

    # Décodage
    is_black = (board.turn == chess_engine.Color.BLACK)
    orig_f, orig_r, dest_f, dest_r, promo = decode_move_index(board, best_idx, is_black)

    print(f"IA joue: ({orig_f},{orig_r}) -> ({dest_f},{dest_r}), promo={promo}, value={value:.3f}")

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
            result = ai_pick_move(board, model, device, TEMPERATURE)
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

"""
Script pour jouer contre le modèle AlphaZero entraîné.
Utilise le moteur C++ via pybind11 + le réseau de neurones pour l'IA.
"""

import warnings

from lib import decode_move_index
# from lib_gui import load_images, draw_board, draw_last_move, draw_highlights, draw_pieces, \
#     draw_game_over

warnings.filterwarnings("ignore", category=UserWarning, message="pkg_resources is deprecated")

import pygame
import sys
import numpy as np
import torch
import os

import chess_engine
from train import AlphaZeroLightning

# ============================================================
#                     CONFIGURATION
# ============================================================

WIDTH, HEIGHT = 800, 800
SQUARE_SIZE = WIDTH // 8
WHITE_COLOR = (240, 217, 181)
BLACK_COLOR = (181, 136, 99)
HIGHLIGHT_COLOR = (186, 202, 68)
DOT_COLOR = (130, 151, 105)
LAST_MOVE_COLOR = (205, 210, 106)

# Couleur jouée par l'humain (WHITE ou BLACK)
HUMAN_COLOR = chess_engine.Color.WHITE

# Chemin vers le checkpoint Lightning
CHECKPOINT_PATH = "checkpoints/last.ckpt"

# Architecture (doit correspondre à l'entraînement)
NUM_RES_BLOCKS = 10
NUM_FILTERS = 128

# Température pour le sampling (0 = déterministe, 0.5 = léger aléa)
TEMPERATURE = 0.1

IMAGES = {}


# ============================================================
#                     CHARGEMENT DU MODÈLE
# ============================================================

def load_model(checkpoint_path, num_res_blocks, num_filters):
    """Charge le modèle depuis un checkpoint Lightning."""
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
    orig_f, orig_r, dest_f, dest_r, promo = decode_move_index(best_idx, is_black)

    # Promotion dame implicite (convention AlphaZero)
    piece = board.get_square(orig_f, orig_r).get_piece()
    if (piece.get_type() == chess_engine.PieceType.PAWN
            and promo == chess_engine.PieceType.NONE
            and (dest_r == 0 or dest_r == 7)):
        promo = chess_engine.PieceType.QUEEN

    print(f"IA joue: ({orig_f},{orig_r}) -> ({dest_f},{dest_r}), promo={promo}, value={value:.3f}")

    return orig_f, orig_r, dest_f, dest_r, promo


# ============================================================
#                     RENDU GRAPHIQUE
# ============================================================

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


# ============================================================
#                     BOUCLE PRINCIPALE
# ============================================================

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("AlphaZero Maison — Jouer contre l'IA")
    clock = pygame.time.Clock()
    load_images()

    # Chargement du modèle
    model, device = load_model(CHECKPOINT_PATH, NUM_RES_BLOCKS, NUM_FILTERS)

    # Initialisation du plateau
    board = chess_engine.Chessboard()
    board.set_startup_pieces()

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
                        current_legal_moves = board.get_legal_moves(clicked_file, clicked_rank)
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
                        board.move_piece(orig_f, orig_r, clicked_file, clicked_rank, promotion_type)

                        if board.game_state != chess_engine.GameState.ONGOING:
                            game_over = True

                    selected_square = None
                    current_legal_moves = []

        # Tour de l'IA
        if not is_human_turn and not game_over:
            result = ai_pick_move(board, model, device, TEMPERATURE)
            if result is not None:
                orig_f, orig_r, dest_f, dest_r, promo = result
                board.move_piece(orig_f, orig_r, dest_f, dest_r, promo)

                if board.game_state != chess_engine.GameState.ONGOING:
                    game_over = True

        # Rendu
        draw_board(screen)
        draw_last_move(screen, board)
        draw_highlights(screen, selected_square, current_legal_moves)
        draw_pieces(screen, board)
        draw_game_over(screen, board)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()

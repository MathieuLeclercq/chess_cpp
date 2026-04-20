import os
import math
import torch
import warnings
import hashlib
import threading
import glob
import numpy as np

from datetime import datetime
from typing import Any
import chess_engine
from model import ChessNet


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
        return -1


def decode_move_index(board, index, is_black):
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
        p_idx = sub_idx % 3  # 0=knight, 1=bishop, 2=rook

        df = dir_idx - 1  # -1, 0, +1
        dr = 1  # Toujours avance d'un rang (du point de vue du joueur)

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

    promotion = gestion_promo_dame(board, orig_f, orig_r, dest_r, promotion)
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
                    if (sq.get_piece().get_type() != p_type or
                            sq.get_piece().get_color() != piece.get_color()):
                        continue
                    for m in board.get_legal_moves(f, r):
                        if (m.get_dest_square().get_file() == dest_f and
                                m.get_dest_square().get_rank() == dest_r):
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
        chess_engine.GameState.CHECKMATE: ("1-0" if board.turn == chess_engine.Color.BLACK
                                           else "0-1"),
        chess_engine.GameState.STALEMATE: "1/2-1/2",
        chess_engine.GameState.DRAW_REPETITION: "1/2-1/2",
        chess_engine.GameState.DRAW_50_MOVES: "1/2-1/2",
        chess_engine.GameState.DRAW_INSUFF_MATERIAL: "1/2-1/2"
    }
    pgn += results.get(board.game_state, "*")

    print("\n===== PGN =====")
    print(pgn)
    print("===============\n")


def gestion_promo_dame(board, orig_f, orig_r, dest_r, promo):
    # Promotion dame implicite (convention AlphaZero)
    piece = board.get_square(orig_f, orig_r).get_piece()
    if (piece.get_type() == chess_engine.PieceType.PAWN
            and promo == chess_engine.PieceType.NONE
            and (dest_r == 0 or dest_r == 7)):
        promo = chess_engine.PieceType.QUEEN
    return promo


def load_supervised_model(checkpoint_path, num_res_blocks, num_filters, device):
    from train_supervised import AlphaZeroLightning
    """Charge le modèle depuis un checkpoint Lightning."""
    os.environ["TORCH_SKIP_WEIGHTS_ONLY_WARNING"] = "1"
    device = torch.device(device)

    lit_model = AlphaZeroLightning.load_from_checkpoint(
        checkpoint_path,
        num_res_blocks=num_res_blocks,
        num_filters=num_filters,
    )
    model = lit_model.model
    model.to(device)
    model.eval()
    print(f"Modèle chargé depuis {checkpoint_path} (device: {device})")
    return model


def load_unsupervised_model(checkpoint_path, num_res_blocks, num_filters, device):
    """Charge le modèle depuis un checkpoint standard PyTorch."""
    os.environ["TORCH_SKIP_WEIGHTS_ONLY_WARNING"] = "1"

    # 1. Instanciation de l'architecture vide
    model = ChessNet(num_res_blocks=num_res_blocks, num_filters=num_filters)

    # 2. Chargement du fichier
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=True)

    # 3. Injection des poids
    model.load_state_dict(checkpoint["model_state_dict"])

    model.to(device)
    model.eval()

    print(f"Modèle chargé depuis {checkpoint_path} (device: {device})")
    return model


def load_model(checkpoint_path, num_res_blocks, num_filters, device):
    if checkpoint_path.endswith('.ckpt'):
        # il faut load le modèle supervisé
        model = load_supervised_model(checkpoint_path, num_res_blocks, num_filters, device)
    elif checkpoint_path.endswith('.pt'):
        # il faut load le modèle "alphazero"
        model = load_unsupervised_model(checkpoint_path, num_res_blocks, num_filters, device)
    else:
        raise Exception('Extension inconnue pour le fichier checkpoint '
                        '(doit être ".pt" ou ".ckpt"')
    return model


def ai_pick_move_instant(board, model, device, temperature=0.1):
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


def append_to_disk_buffer(new_data, folder_path, max_buffer_size):
    """Sauvegarde les nouvelles positions sur disque et supprime les shards les plus anciens."""
    if not new_data:
        remaining = 0
        if os.path.exists(folder_path):
            for s in glob.glob(os.path.join(folder_path, "shard_*.npz")):
                try:
                    remaining += int(os.path.splitext(s)[0].split("_")[-1])
                except (ValueError, IndexError):
                    continue
        print(f"  [Disque] +0 positions. Buffer total : ~{remaining} / {max_buffer_size}")
        return remaining

    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    num_new = len(new_data)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"shard_{timestamp}_{num_new}.npz"
    filepath = os.path.join(folder_path, filename)

    states = np.array([item[0] for item in new_data], dtype=np.float16)
    policies = np.array([item[1] for item in new_data], dtype=np.float16)
    values = np.array([item[2] for item in new_data], dtype=np.float32)

    np.savez_compressed(filepath, states=states, policies=policies, values=values)

    shards = sorted(glob.glob(os.path.join(folder_path, "shard_*.npz")))
    total = 0
    keep_from = 0
    for i in range(len(shards) - 1, -1, -1):
        try:
            size = int(os.path.splitext(shards[i])[0].split("_")[-1])
        except (ValueError, IndexError):
            continue
        total += size
        if total > max_buffer_size:
            keep_from = i + 1
            break

    for shard in shards[:keep_from]:
        try:
            os.remove(shard)
        except OSError:
            pass

    remaining = sum(
        int(os.path.splitext(s)[0].split("_")[-1])
        for s in shards[keep_from:]
        if os.path.exists(s)
    )
    print(f"  [Disque] +{num_new} positions. Buffer total : ~{remaining} / {max_buffer_size}")
    return remaining


# ============================================================
#                     EXPORT ONNX & QUANTIFICATION
# ============================================================

def export_model_to_onnx(model, onnx_path, device):
    """
    Export ONNX avec batch dynamique, FP32, pour inférence GPU batchée.
    """
    model.eval()
    dummy_input = (torch.randn(1, 119, 8, 8, device=device),)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        torch.onnx.export(
            model,
            dummy_input,
            onnx_path,
            export_params=True,
            opset_version=18,
            do_constant_folding=True,
            input_names=['input'],
            output_names=['policy', 'value'],
            dynamic_axes={
                'input': {0: 'batch'},
                'policy': {0: 'batch'},
                'value': {0: 'batch'}
            },
            verbose=False
        )


def get_model_hash(filepath):
    """Génère un hash unique basé sur le contenu du fichier."""
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()[:16]


def chose_move_idx(pi, tau):
    mask = pi > 0
    logits = np.full_like(pi, -1e20, dtype=np.float64)
    logits[mask] = np.log(pi[mask].astype(np.float64)) / tau

    logits -= np.max(logits)
    probs = np.exp(logits)
    probs[~mask] = 0
    probs /= np.sum(probs)

    chosen_idx = np.random.choice(4672, p=probs)
    return chosen_idx


def parse_uci_to_coords(uci_str):
    """
    Transforme 'e2e4' ou 'a7a8q' en (orig_f, orig_r, dest_f, dest_r, promotion)
    """
    # 1. Coordonnées de base (a-h -> 0-7, 1-8 -> 0-7)
    orig_f = ord(uci_str[0]) - ord('a')
    orig_r = int(uci_str[1]) - 1
    dest_f = ord(uci_str[2]) - ord('a')
    dest_r = int(uci_str[3]) - 1

    # 2. Gestion de la promotion (si la chaîne fait 5 caractères)
    promotion = chess_engine.PieceType.NONE
    if len(uci_str) == 5:
        promo_char = uci_str[4].lower()
        mapping = {
            'q': chess_engine.PieceType.QUEEN,
            'r': chess_engine.PieceType.ROOK,
            'b': chess_engine.PieceType.BISHOP,
            'n': chess_engine.PieceType.KNIGHT
        }
        promotion = mapping.get(promo_char, chess_engine.PieceType.NONE)

    return orig_f, orig_r, dest_f, dest_r, promotion


def coords_to_uci(orig_f, orig_r, dest_f, dest_r, promotion):
    """
    Transforme les coordonnées et le type de promotion en string UCI (ex: 'e7e8q')
    """
    files = "abcdefgh"
    # Les rangs dans ton moteur sont 0-indexed, en UCI ils sont 1-8
    move_uci = f"{files[orig_f]}{orig_r + 1}{files[dest_f]}{dest_r + 1}"

    # Ajout du suffixe de promotion si nécessaire
    if promotion != chess_engine.PieceType.NONE:
        mapping = {
            chess_engine.PieceType.QUEEN: 'q',
            chess_engine.PieceType.ROOK: 'r',
            chess_engine.PieceType.BISHOP: 'b',
            chess_engine.PieceType.KNIGHT: 'n'
        }
        move_uci += mapping.get(promotion, '')

    return move_uci


def calculate_performance_rating(sf_elo, wins, draws, losses):
    total_games = wins + draws + losses
    if total_games == 0:
        return sf_elo

    # Calcul du score réel (1 pour win, 0.5 pour draw)
    score = wins + 0.5 * draws
    percentage = score / total_games

    # Correction pour éviter log(0) ou division par zéro sur de petits échantillons
    # On cape le pourcentage entre un demi-point de défaite et un demi-point de victoire
    percentage = max(0.5 / total_games, min((total_games - 0.5) / total_games, percentage))

    # Formule Elo inverse
    elo_diff = 400 * math.log10(percentage / (1 - percentage))

    return int(sf_elo + elo_diff)


def run_with_interrupt(fn, *args) -> Any:
    """Lance fn(*args) dans un thread pour que Ctrl+C reste réactif."""
    result = [None]
    exc = [None]

    def target():
        try:
            result[0] = fn(*args)
        except Exception as e:
            exc[0] = e

    t = threading.Thread(target=target)
    t.start()

    try:
        while t.is_alive():
            t.join(timeout=0.5)
    except KeyboardInterrupt:
        print("\n[Interruption détectée] En attente de la fin du self-play C++...")
        raise

    if exc[0]:
        raise exc[0]
    return result[0]


def convert_game_results(games):
    data = []
    stats = {
        "checkmates": 0, "stalemates": 0, "repetition": 0,
        "50_moves": 0, "insuff_mat": 0, "max_moves": 0,
        "total_saved_moves": 0
    }

    # Mapping entre l'entier C++ et la clé du dictionnaire
    reason_keys = ["checkmates", "stalemates", "repetition", "50_moves", "insuff_mat", "max_moves"]

    for game in games:
        states = game.state_tensors
        policies = game.policies
        outcome = game.final_outcome
        reason_idx = game.end_reason
        n = states.shape[0]

        stats["total_saved_moves"] += n

        # Comptage détaillé
        if 0 <= reason_idx <= 5:
            key = reason_keys[reason_idx]
            stats[key] += 1

        for i in range(n):
            tensor_np = states[i].astype(np.float16)
            pi_np = policies[i].astype(np.float16)
            is_white_turn = states[i][112, 0, 0] > 0.5
            value = outcome if is_white_turn else -outcome

            data.append((tensor_np, pi_np, value))

    return data, stats

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from torch.cuda.amp import GradScaler
import wandb
import os

import chess_engine
from lib import decode_move_index, move_to_san, print_pgn
from mcts import MCTS
from model import ChessNet


# ============================================================
#                     DATASET
# ============================================================

class SelfPlayDataset(Dataset):
    def __init__(self, buffer):
        self.buffer = buffer

    def __len__(self):
        return len(self.buffer)

    def __getitem__(self, idx):
        tensor_np, pi, value = self.buffer[idx]
        return (
            torch.from_numpy(tensor_np).float(),
            torch.from_numpy(pi).float(),
            torch.tensor(value, dtype=torch.float32)
        )


# ============================================================
#                     SELF-PLAY
# ============================================================

def self_play_game(model, device, num_simulations=200, max_moves=100):
    board = chess_engine.Chessboard()
    board.set_startup_pieces()

    history = []
    san_moves = []
    move_num = 0

    while board.game_state == chess_engine.GameState.ONGOING and move_num < max_moves:
        tensor_np = board.get_alphazero_tensor()
        pi, _ = MCTS.mcts_search(board, model, device, num_simulations, add_dirichlet=True)

        if move_num < 30:
            probs = pi.copy()
            probs /= probs.sum()
            chosen_idx = np.random.choice(4672, p=probs)
        else:
            chosen_idx = np.argmax(pi)

        history.append((tensor_np, pi))

        is_black = (board.turn == chess_engine.Color.BLACK)
        orig_f, orig_r, dest_f, dest_r, promo = decode_move_index(board, chosen_idx, is_black)

        # Debug : vérifier que la pièce existe
        piece = board.get_square(orig_f, orig_r).get_piece()
        if piece.get_type() == chess_engine.PieceType.NONE:
            print(f"BUG: case vide à ({orig_f},{orig_r}), index={chosen_idx}, is_black={is_black}")
            print(f"  plane={chosen_idx // 64}, remainder={chosen_idx % 64}")
            print(f"  legal_indices={board.get_legal_move_indices()}")
            print(f"  chosen_idx in legal: {chosen_idx in board.get_legal_move_indices()}")
            break

        san = move_to_san(board, orig_f, orig_r, dest_f, dest_r, promo)
        success = board.move_piece(orig_f, orig_r, dest_f, dest_r, promo)
        if not success:
            print(f"SELF-PLAY ERROR: move failed ({orig_f},{orig_r})->({dest_f},{dest_r})")
            break

        if board.game_state == chess_engine.GameState.CHECKMATE:
            san += "#"
        elif board.is_in_check():
            san += "+"
        san_moves.append(san)
        move_num += 1

    print_pgn(board, san_moves)
    z = 0.0
    if board.game_state == chess_engine.GameState.CHECKMATE:
        z = 1.0  # history[-1] est la position du gagnant

    dataset = []
    for i, (tensor_np, pi) in enumerate(history):
        value = z if (len(history) - i) % 2 == 1 else -z
        dataset.append((tensor_np, pi, value))

    return dataset, move_num, board.game_state


def generate_games(model, device, num_games, num_simulations):
    all_data = []
    total_moves = 0
    results = {"checkmate": 0, "draw": 0, "ongoing": 0}

    for g in range(num_games):
        game_data, move_count, state = self_play_game(model, device, num_simulations)
        all_data.extend(game_data)
        total_moves += move_count

        if state == chess_engine.GameState.CHECKMATE:
            results["checkmate"] += 1
        elif state == chess_engine.GameState.ONGOING:
            results["ongoing"] += 1
        else:
            results["draw"] += 1

        print(f"  Partie {g + 1}/{num_games}: {move_count} coups, état={state}")

    avg_length = total_moves / max(num_games, 1)
    return all_data, results, avg_length


# ============================================================
#                     TRAINING
# ============================================================

def train_on_buffer(model, optimizer, scaler, device, replay_buffer,
                    epochs=10, batch_size=256, global_step=0):
    model.train()
    dataset = SelfPlayDataset(replay_buffer)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=0)

    for epoch in range(epochs):
        epoch_loss = 0.0
        num_batches = 0

        for x, target_pi, y_value in loader:
            x = x.to(device)
            target_pi = target_pi.to(device)
            y_value = y_value.to(device)

            optimizer.zero_grad()

            with torch.autocast(device_type="cuda", enabled=(device.type == "cuda")):
                p_logits, v_pred = model(x)
                log_probs = F.log_softmax(p_logits, dim=1)
                policy_loss = -torch.sum(target_pi * log_probs, dim=1).mean()
                value_loss = F.mse_loss(v_pred.view(-1), y_value)
                loss = policy_loss + value_loss

            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

            epoch_loss += loss.item()
            num_batches += 1
            global_step += 1

            if num_batches % 20 == 0:
                wandb.log({
                    "train/loss": loss.item(),
                    "train/policy_loss": policy_loss.item(),
                    "train/value_loss": value_loss.item(),
                    "train/global_step": global_step,
                })

        avg_loss = epoch_loss / max(num_batches, 1)
        print(f"    Epoch {epoch + 1}/{epochs} — loss: {avg_loss:.4f}")

    return global_step


# ============================================================
#                     PIPELINE
# ============================================================

def pipeline(
    num_iterations=10,
    games_per_iter=20,
    num_simulations=200,
    train_epochs=10,
    batch_size=256,
    learning_rate=1e-3,
    num_res_blocks=10,
    num_filters=128,
    max_buffer_size=200_000,
    checkpoint_path=None,
):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = ChessNet(num_res_blocks=num_res_blocks, num_filters=num_filters).to(device)

    # Chargement optionnel du checkpoint supervisé
    if checkpoint_path:
        from train_supervised import AlphaZeroLightning
        pretrained = AlphaZeroLightning.load_from_checkpoint(
            checkpoint_path,
            num_res_blocks=num_res_blocks,
            num_filters=num_filters,
        )
        model.load_state_dict(pretrained.model.state_dict())
        print(f"Checkpoint supervisé chargé: {checkpoint_path}")

    # Persistants entre les itérations — jamais recréés
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    scaler = GradScaler(enabled=(device.type == "cuda"))

    wandb.init(project="alphazero-chess", name="self_play")
    wandb.watch(model, log="gradients", log_freq=100)

    replay_buffer = []
    global_step = 0

    for iteration in range(num_iterations):
        print(f"\n{'=' * 50}")
        print(f"  ITERATION {iteration + 1}/{num_iterations}")
        print(f"{'=' * 50}")

        # ── 1. Self-play ──
        model.eval()
        new_data, results, avg_length = generate_games(
            model, device, games_per_iter, num_simulations
        )

        replay_buffer.extend(new_data)
        if len(replay_buffer) > max_buffer_size:
            replay_buffer = replay_buffer[-max_buffer_size:]

        wandb.log({
            "selfplay/buffer_size": len(replay_buffer),
            "selfplay/new_positions": len(new_data),
            "selfplay/avg_game_length": avg_length,
            "selfplay/checkmates": results["checkmate"],
            "selfplay/draws": results["draw"],
            "selfplay/truncated": results["ongoing"],
            "selfplay/iteration": iteration + 1,
        })

        print(f"  Buffer: {len(replay_buffer)} positions")
        print(f"  Parties: {results['checkmate']} mats, {results['draw']} nulles, "
              f"{results['ongoing']} tronquées")
        print(f"  Longueur moyenne: {avg_length:.0f} coups")

        # ── 2. Training ──
        global_step = train_on_buffer(
            model, optimizer, scaler, device, replay_buffer,
            epochs=train_epochs, batch_size=batch_size, global_step=global_step,
        )

        # ── 3. Sauvegarde ──
        save_path = f"checkpoints/selfplay_iter{iteration + 1}.pt"
        torch.save({
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scaler_state_dict": scaler.state_dict(),
            "iteration": iteration + 1,
            "global_step": global_step,
            "buffer_size": len(replay_buffer),
        }, save_path)
        print(f"  Checkpoint sauvegardé: {save_path}")

    wandb.finish()


if __name__ == "__main__":
    pipeline(
        num_iterations=15,  # Un peu plus d'itérations
        games_per_iter=10,  # BEAUCOUP plus de parties pour la diversité des données
        num_simulations=50,  # OK pour l'instant
        train_epochs=3,  # Moins d'epochs pour ne pas overfitter sur le nouveau buffer
        batch_size=512,
        checkpoint_path="checkpoints/supervised_best_03_07.ckpt",
    )
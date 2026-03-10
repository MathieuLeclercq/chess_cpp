import warnings

warnings.filterwarnings("ignore", module="requests")
import wandb
import torch
import numpy as np
import torch.nn.functional as F
import torch.multiprocessing as mp
from torch.utils.data import Dataset, DataLoader
from torch.amp import GradScaler
from datetime import datetime

import chess_engine
from lib import (decode_move_index, move_to_san, load_model, save_buffer, load_buffer,
                 export_model_to_onnx)

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
#                     WORKER & SELF-PLAY
# ============================================================
def self_play_game(mcts_engine, num_simulations=200, max_moves=200):
    board = chess_engine.Chessboard()
    board.set_startup_pieces()

    history = []
    san_moves = []
    move_num = 0

    while board.game_state == chess_engine.GameState.ONGOING and move_num < max_moves:
        tensor_np = board.get_alphazero_tensor()

        # Appel natif au C++ (retourne une liste, on convertit en ndarray)
        pi_raw = mcts_engine.mcts_search(board, num_simulations, 1.4, True)
        pi = np.array(pi_raw, dtype=np.float32)

        if move_num < 6:
            tau = 0.5
            log_pi = np.log(pi + 1e-10)
            logits = log_pi / tau
            logits -= np.max(logits)
            probs = np.exp(logits)
            probs /= np.sum(probs)

            chosen_idx = np.random.choice(4672, p=probs)

        else:
            chosen_idx = np.argmax(pi)

        history.append((tensor_np, pi))

        is_black = (board.turn == chess_engine.Color.BLACK)
        orig_f, orig_r, dest_f, dest_r, promo = decode_move_index(board, chosen_idx, is_black)

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

    z = 0.0
    if board.game_state == chess_engine.GameState.CHECKMATE:
        z = 1.0

    dataset = []
    for i, (tensor_np, pi) in enumerate(history):
        value = z if (len(history) - i) % 2 == 1 else -z
        dataset.append((tensor_np, pi, value))

    return dataset, move_num, board.game_state


def worker_self_play(args):
    """Fonction isolée exécutée par chaque processus (Cœur CPU)."""
    onnx_path, num_simulations, max_moves = args

    # Initialisation du moteur MCTS en C++ pour ce thread
    mcts_engine = chess_engine.MCTS(onnx_path)

    # Génération d'une seule partie
    game_data, move_count, state = self_play_game(mcts_engine, num_simulations, max_moves)

    return game_data, move_count, state


def generate_games(onnx_path, num_games, num_simulations, num_workers=4):
    all_data = []
    total_moves = 0
    results = {"checkmate": 0, "draw": 0, "ongoing": 0}

    args_list = [(onnx_path, num_simulations, 200) for _ in range(num_games)]

    print(f"Lancement de {num_games} parties sur {num_workers} processus (MCTS C++ / ONNX)...")

    with mp.Pool(processes=num_workers) as pool:
        for i, (game_data, move_count, state) in enumerate(
                pool.imap_unordered(worker_self_play, args_list)):
            all_data.extend(game_data)
            total_moves += move_count

            if state == chess_engine.GameState.CHECKMATE:
                results["checkmate"] += 1
            elif state == chess_engine.GameState.ONGOING:
                results["ongoing"] += 1
            else:
                results["draw"] += 1

            print(f"  Partie terminée ({i + 1}/{num_games}): {move_count} coups, état={state}")

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
        epoch_policy_loss = 0.0
        epoch_value_loss = 0.0
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
            epoch_policy_loss += policy_loss.item()
            epoch_value_loss += value_loss.item()
            num_batches += 1
            global_step += 1

        if num_batches > 0:
            avg_loss = epoch_loss / num_batches
            wandb.log({
                "train/epoch_loss": avg_loss,
                "train/epoch_policy_loss": epoch_policy_loss / num_batches,
                "train/epoch_value_loss": epoch_value_loss / num_batches,
                "train/epoch": epoch + 1,
                "train/global_step": global_step,
            })
            print(f"    Epoch {epoch + 1}/{epochs} — loss: {avg_loss:.4f}")

    return global_step


# ============================================================
#                     PIPELINE
# ============================================================
def pipeline(
        num_iterations=2,
        games_per_iter=4,
        num_simulations=100,
        train_epochs=3,
        batch_size=1024,
        learning_rate=1e-4,
        num_res_blocks=10,
        num_filters=128,
        max_buffer_size=100_000,
        num_workers=4,
        checkpoint_path=None,
):
    assert torch.cuda.is_available()
    gpu_device = torch.device("cuda")

    model = ChessNet(num_res_blocks=num_res_blocks, num_filters=num_filters).to(gpu_device)

    if checkpoint_path:
        model = load_model(checkpoint_path, num_res_blocks, num_filters, gpu_device)
        print(f"Checkpoint chargé : {checkpoint_path}")

    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    scaler = GradScaler("cuda", enabled=True)

    wandb.init(project="alphazero-chess", name="self_play_onnx_cpp")

    buffer_filepath = "checkpoints/replay_buffer.npz"
    replay_buffer = load_buffer(buffer_filepath)
    global_step = 0

    for iteration in range(num_iterations):
        print(f"\n{'=' * 50}")
        print(f"  ITERATION {iteration + 1}/{num_iterations}")
        print(f"{'=' * 50}")

        # ── 0. Exportation du modèle vers ONNX ──
        onnx_path = f"checkpoints/current_mcts_iter{iteration + 1}_int8.onnx"
        print("  Exportation et quantification du modèle vers ONNX...")
        export_model_to_onnx(model, onnx_path, gpu_device)

        # ── 1. Phase Self-Play (C++ / ONNX) ──
        new_data, results, avg_length = generate_games(
            onnx_path, games_per_iter, num_simulations, num_workers=num_workers
        )

        replay_buffer.extend(new_data)
        if len(replay_buffer) > max_buffer_size:
            replay_buffer = replay_buffer[-max_buffer_size:]

        wandb.log({
            "selfplay/buffer_size": len(replay_buffer),
            "selfplay/new_positions": len(new_data),
            "selfplay/avg_game_length": avg_length,
            "selfplay/iteration": iteration + 1,
        })

        print(f"  Buffer: {len(replay_buffer)} positions")

        # ── 2. Phase Training (GPU) ──
        current_batch_size = min(batch_size, len(replay_buffer))

        if current_batch_size > 0:
            global_step = train_on_buffer(
                model, optimizer, scaler, gpu_device, replay_buffer,
                epochs=train_epochs, batch_size=current_batch_size, global_step=global_step,
            )
        else:
            print("  Pas assez de données pour entraîner.")

        # ── 3. Sauvegarde ──
        timestamp = datetime.now().strftime("%Y_%m_%d_%Hh%M")
        save_path = f"checkpoints/{timestamp}_multi_iter{iteration + 1}.pt"
        torch.save({
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scaler_state_dict": scaler.state_dict(),
            "iteration": iteration + 1,
            "global_step": global_step,
        }, save_path)
        print(f"  Checkpoint sauvegardé: {save_path}")

        save_buffer(replay_buffer, buffer_filepath)

    wandb.finish()


if __name__ == "__main__":
    mp.set_start_method('spawn', force=True)

    pipeline(
        num_iterations=40,
        games_per_iter=64,
        num_workers=8,
        num_simulations=600,
        train_epochs=1,
        batch_size=1024,
        learning_rate=1e-5,
        max_buffer_size=50_000,
        checkpoint_path="checkpoints/supervised_best_03_09_lichess.ckpt"
    )

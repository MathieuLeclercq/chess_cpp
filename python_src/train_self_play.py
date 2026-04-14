import os.path
import warnings
import logging

warnings.filterwarnings("ignore", module="requests")
import wandb
import torch
from collections import deque
import torch.nn.functional as f
from torch.utils.data import Dataset, DataLoader, RandomSampler
from torch.amp import GradScaler
from datetime import datetime

import chess_engine
from lib import (save_buffer, load_buffer, export_model_to_onnx, calculate_performance_rating,
                 export_model_to_onnx_gpu, convert_game_results, run_with_interrupt)
from stockfish_player import evaluate_against_anchor
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
#                     SELF-PLAY (GPU Batched)
# ============================================================
def generate_games(onnx_path, games_per_iter, concurrent_games, slow_sims, fast_sims, slow_ratio):
    """
    Génère des parties via le SelfPlayManager C++ avec inférence batchée sur GPU.
    """
    evaluator = chess_engine.ONNXEvaluator(onnx_path, True)

    game_results = run_with_interrupt(
        chess_engine.generate_self_play_games,
        evaluator,
        concurrent_games,
        slow_sims,
        fast_sims,
        games_per_iter,
        slow_ratio
    )

    data, stats = convert_game_results(game_results)

    num_games = len(game_results)
    avg_length = stats["total_moves"] / max(num_games, 1)

    print(f"\n{'=' * 30}")
    print(f"      BILAN DE L'ITERATION")
    print(f"{'=' * 30}")
    print(f"  Parties jouées          : {num_games}")
    print(f"  Positions générées      : {len(data)}")
    print(f"  Pos sauvegardées/Partie : {avg_length:.1f}")
    print(f"  Victoires (mat)         : {stats['checkmates']}")
    print(f"  Nulles                  : {stats['draws']}")
    print(f"{'=' * 30}\n")

    # Libération explicite de l'évaluateur ONNX GPU
    del game_results
    del evaluator

    return data, avg_length


# ============================================================
#                     TRAINING
# ============================================================
def train_on_buffer(model, optimizer, scaler, device, replay_buffer, learning_rate,
                    epochs=10, batch_size=256, global_step=0, samples_per_epoch=15000):
    model.train()
    dataset = SelfPlayDataset(list(replay_buffer))

    num_samples = min(len(dataset), samples_per_epoch)
    sampler = RandomSampler(dataset, replacement=True, num_samples=num_samples)
    loader = DataLoader(dataset, batch_size=batch_size,
                        sampler=sampler, num_workers=0, pin_memory=True)

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
                log_probs = f.log_softmax(p_logits, dim=1)
                policy_loss = -torch.sum(target_pi * log_probs, dim=1).mean()
                value_loss = f.mse_loss(v_pred.view(-1), y_value)
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
                "train/learning_rate": learning_rate,
            }, step=global_step)
            print(f"    Epoch {epoch + 1}/{epochs} — loss: {avg_loss:.4f}")

    return global_step


# ============================================================
#                     PIPELINE
# ============================================================
def pipeline(
        num_iterations=2,
        games_per_iter=128,
        concurrent_games=128,
        slow_sims=700,
        fast_sims=100,
        slow_ratio=0.25,
        train_epochs=3,
        batch_size=1024,
        learning_rate=1e-4,
        num_res_blocks=10,
        num_filters=128,
        max_buffer_size=100_000,
        samples_per_epoch=15_000,
        eval_stockfish_every=4,
        checkpoint_path=None,
        stockfish_path=None,
        stockfish_elo=2500,
        stockfish_nodes=200_000,
        num_sim_eval_sf=700
):
    logging.getLogger("torch").setLevel(logging.ERROR)
    hyperparams = locals().copy()

    timestamp = datetime.now().strftime("%Y_%m_%d_%Hh%M")
    assert torch.cuda.is_available()
    gpu_device = torch.device("cuda")
    assert os.path.isfile(stockfish_path)

    model = ChessNet(num_res_blocks=num_res_blocks, num_filters=num_filters).to(gpu_device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    scaler = GradScaler("cuda", enabled=True)

    global_step = 0
    start_iteration = 0

    if checkpoint_path:
        checkpoint = torch.load(checkpoint_path, map_location=gpu_device, weights_only=True)
        model.load_state_dict(checkpoint["model_state_dict"])
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        for param_group in optimizer.param_groups:
            param_group['lr'] = learning_rate
        scaler.load_state_dict(checkpoint["scaler_state_dict"])
        start_iteration = checkpoint.get("iteration", 0)
        global_step = checkpoint.get("global_step", 0)
        print(f"Checkpoint chargé : {checkpoint_path} (Reprise à l'itération {start_iteration})")

    wandb.init(project="alphazero-chess", name=f"{timestamp}_self_play", config=hyperparams)

    buffer_filepath = "checkpoints/replay_buffer.npz"
    replay_buffer = deque(load_buffer(buffer_filepath), maxlen=max_buffer_size)

    for iteration in range(start_iteration, start_iteration + num_iterations):
        print(f"\n{'=' * 50}")
        print(f"  ITERATION {iteration + 1}/{start_iteration + num_iterations}")
        print(f"{'=' * 50}")

        # ── 1. Export ONNX pour le self-play GPU ──
        onnx_path = f"checkpoints/{timestamp}_selfplay_tmp.onnx"
        export_model_to_onnx_gpu(model, onnx_path, gpu_device)

        # ── 2. Self-Play (C++ / GPU batched) ──
        new_data, avg_length = generate_games(
            onnx_path, games_per_iter, concurrent_games, slow_sims, fast_sims, slow_ratio
        )

        replay_buffer.extend(new_data)
        print(f"  Buffer: {len(replay_buffer)} positions")

        # ── 3. Training (GPU / PyTorch) ──
        current_batch_size = min(batch_size, len(replay_buffer))

        if current_batch_size > 0:
            global_step = train_on_buffer(
                model, optimizer, scaler, gpu_device, replay_buffer, learning_rate,
                epochs=train_epochs, batch_size=current_batch_size, global_step=global_step,
                samples_per_epoch=samples_per_epoch
            )
        else:
            print("  Pas assez de données pour entraîner.")

        wandb.log({
            "selfplay/buffer_size": len(replay_buffer),
            "selfplay/new_positions": len(new_data),
            "selfplay/avg_game_length": avg_length,
            "selfplay/iteration": iteration + 1,
        }, step=global_step)

        # ── 4. Sauvegarde checkpoint ──
        ckpt_filename = f"{timestamp}_iter{iteration + 1}_unsupervised"
        save_path = f"checkpoints/{ckpt_filename}.pt"
        torch.save({
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scaler_state_dict": scaler.state_dict(),
            "iteration": iteration + 1,
            "global_step": global_step,
        }, save_path)
        print(f"  Checkpoint sauvegardé: {save_path}")
        save_buffer(list(replay_buffer), buffer_filepath)

        # Nettoyage du fichier ONNX temporaire
        if os.path.exists(onnx_path):
            os.remove(onnx_path)

        # ── 5. Évaluation Stockfish ──
        if (iteration + 1) % eval_stockfish_every == 0:
            # Export un ONNX dédié à l'évaluation (CPU, utilisé par l'ancien MCTS)
            eval_onnx_path = f"checkpoints/{ckpt_filename}.onnx"
            export_model_to_onnx(model, eval_onnx_path, gpu_device)

            eval_winrate, eval_wins, eval_draws, eval_losses = evaluate_against_anchor(
                onnx_path=eval_onnx_path,
                stockfish_path=stockfish_path,
                num_games=16,
                mcts_sims=num_sim_eval_sf,
                sf_elo=stockfish_elo,
                sf_nodes=stockfish_nodes,
                num_workers=8
            )

            estim_elo = calculate_performance_rating(
                stockfish_elo, eval_wins, eval_draws, eval_losses
            )

            wandb.log({
                "eval/winrate": eval_winrate,
                "eval/elo_estim": estim_elo,
                "eval/wins": eval_wins,
                "eval/draws": eval_draws,
                "eval/losses": eval_losses,
                "eval/iteration": iteration + 1,
            }, step=global_step)
        else:
            print(f"  Évaluation ignorée.")

    # Export final
    last_timestamp = datetime.now().strftime("%Y_%m_%d_%Hh%M")
    ckpt_onnx_final_path = f"checkpoints/{last_timestamp}_last_unsupervised.onnx"
    export_model_to_onnx(model, ckpt_onnx_final_path, gpu_device)

    wandb.finish()


if __name__ == "__main__":
    try:
        # import os
        # os.environ["WANDB_MODE"] = "disabled"
        pipeline(
            num_iterations=150,
            games_per_iter=512,
            concurrent_games=512,
            slow_sims=700,
            fast_sims=100,
            slow_ratio=0.25,
            train_epochs=1,
            batch_size=4096,
            learning_rate=4e-5,
            max_buffer_size=750_000,
            samples_per_epoch=170_000,
            eval_stockfish_every=6,
            checkpoint_path="checkpoints/2026_04_14_13h33_iter40_unsupervised.pt",
            stockfish_path=r"D:\logiciels\stockfish\stockfish.exe",
            stockfish_elo=2200,
            stockfish_nodes=200_000
        )
    except KeyboardInterrupt:
        print("\n[Interruption] Entraînement stoppé manuellement.")
        print("Synchronisation des dernières métriques avec WandB en cours...")
        wandb.finish()
        print("Arrêt propre terminé.")

import os.path
import warnings

warnings.filterwarnings("ignore", module="requests")
import wandb
import torch
import numpy as np
import torch.nn.functional as F
import torch.multiprocessing as mp
from torch.utils.data import Dataset, DataLoader, RandomSampler
from torch.amp import GradScaler
from datetime import datetime
from tqdm import tqdm

import chess_engine
from lib import (decode_move_index, move_to_san, load_model, save_buffer, load_buffer,
                 export_model_to_onnx, chose_move_idx)
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
#                     WORKER & SELF-PLAY
# ============================================================
def self_play_game(mcts_engine, num_simulations=600, fast_sims=100, slow_ratio=0.25, max_moves=200):
    board = chess_engine.Chessboard()
    board.set_startup_pieces()

    history = []
    san_moves = []
    move_num = 0

    while board.game_state == chess_engine.GameState.ONGOING and move_num < max_moves:
        is_slow_play = (np.random.rand() < slow_ratio)
        current_sims = num_simulations if is_slow_play else fast_sims

        tensor_np = board.get_alphazero_tensor()
        current_turn_color = board.turn

        pi_raw = mcts_engine.mcts_search(board, current_sims, 1.4, True)
        pi = np.array(pi_raw, dtype=np.float32)

        if move_num < 30:
            tau = 1.0
            chosen_idx = chose_move_idx(pi, tau)
        else:
            chosen_idx = np.argmax(pi)

        if is_slow_play:
            history.append((tensor_np, pi, current_turn_color))

        is_black = (board.turn == chess_engine.Color.BLACK)
        orig_f, orig_r, dest_f, dest_r, promo = decode_move_index(board, chosen_idx, is_black)

        san = move_to_san(board, orig_f, orig_r, dest_f, dest_r, promo)
        success = board.move_piece(orig_f, orig_r, dest_f, dest_r, promo)
        if not success:
            print(f"SELF-PLAY ERROR: move failed ({orig_f},{orig_r})->({dest_f},{dest_r})")
            raise Exception

        if board.game_state == chess_engine.GameState.CHECKMATE:
            san += "#"
        elif board.is_in_check():
            san += "+"
        san_moves.append(san)
        move_num += 1

    dataset = []
    if board.game_state == chess_engine.GameState.CHECKMATE:
        if board.turn == chess_engine.Color.WHITE:
            winner_color = chess_engine.Color.BLACK
        else:
            winner_color = chess_engine.Color.WHITE

        for tensor_np, pi, color in history:
            value = 1.0 if color == winner_color else -1.0
            dataset.append((tensor_np, pi, value))
    else:
        for tensor_np, pi, color in history:
            dataset.append((tensor_np, pi, 0.0))

    return dataset, move_num, board.game_state


def worker_self_play(args):
    onnx_path, num_simulations, fast_sims, max_moves = args

    mcts_engine = chess_engine.MCTS(onnx_path)
    game_data, move_count, state = self_play_game(mcts_engine, num_simulations, fast_sims=fast_sims,
                                                  max_moves=max_moves)

    return game_data, move_count, state


def generate_games(onnx_path, num_games, num_simulations, fast_sims, num_workers=4):
    all_data = []
    total_moves = 0

    results = {
        "CHECKMATE": 0, "STALEMATE": 0, "DRAW_REPETITION": 0,
        "DRAW_50_MOVES": 0, "DRAW_INSUFF_MATERIAL": 0, "ONGOING": 0
    }

    # Injection de fast_sims dans les arguments
    args_list = [(onnx_path, num_simulations, fast_sims, 200) for _ in range(num_games)]

    print(f"Lancement de {num_games} parties sur {num_workers} processus (MCTS C++ / ONNX)...")

    with mp.Pool(processes=num_workers) as pool:
        for game_data, move_count, state in tqdm(pool.imap_unordered(worker_self_play, args_list),
                                                 total=num_games,
                                                 desc="Génération du Self-Play"):
            all_data.extend(game_data)
            total_moves += move_count
            if state == chess_engine.GameState.CHECKMATE:
                results["CHECKMATE"] += 1
            elif state == chess_engine.GameState.STALEMATE:
                results["STALEMATE"] += 1
            elif state == chess_engine.GameState.DRAW_REPETITION:
                results["DRAW_REPETITION"] += 1
            elif state == chess_engine.GameState.DRAW_50_MOVES:
                results["DRAW_50_MOVES"] += 1
            elif state == chess_engine.GameState.DRAW_INSUFF_MATERIAL:
                results["DRAW_INSUFF_MATERIAL"] += 1
            elif state == chess_engine.GameState.ONGOING:
                results["ONGOING"] += 1

    avg_length = total_moves / max(num_games, 1)
    print("\n" + "=" * 30)
    print(f"      BILAN DE L'ITERATION")
    print("=" * 30)
    print(f"Nombre total de coups : {total_moves}")
    print(f"Moyenne de coups/partie : {avg_length:.1f}")
    print("-" * 30)
    print(f" Victoires (Checkmate) : {results['CHECKMATE']}")
    print(f" Pat (Stalemate)       : {results['STALEMATE']}")
    print(f" Répétition            : {results['DRAW_REPETITION']}")
    print(f" Règle des 50 coups    : {results['DRAW_50_MOVES']}")
    print(f" Matériel insuffisant  : {results['DRAW_INSUFF_MATERIAL']}")
    if results['ONGOING'] > 0:
        print(f" Non terminées (Max)   : {results['ONGOING']}")
    print("=" * 30 + "\n")

    return all_data, results, avg_length


# ============================================================
#                     TRAINING
# ============================================================
def train_on_buffer(model, optimizer, scaler, device, replay_buffer,
                    epochs=10, batch_size=256, global_step=0, samples_per_epoch=15000):
    model.train()
    dataset = SelfPlayDataset(replay_buffer)

    # Sécurité : on prend 15000, ou la taille du buffer s'il est plus petit au début
    num_samples = min(len(dataset), samples_per_epoch)
    sampler = RandomSampler(dataset, replacement=True, num_samples=num_samples)

    # On passe le sampler au DataLoader (shuffle doit être retiré quand on utilise un sampler)
    loader = DataLoader(dataset, batch_size=batch_size, sampler=sampler, num_workers=0)

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
            }, step=global_step)
            print(f"    Epoch {epoch + 1}/{epochs} — loss: {avg_loss:.4f}")

    return global_step


# ============================================================
#                     PIPELINE
# ============================================================
def pipeline(
        num_iterations=2,
        games_per_iter=4,
        num_simulations=600,
        fast_sims=100,
        train_epochs=3,
        batch_size=1024,
        learning_rate=1e-4,
        num_res_blocks=10,
        num_filters=128,
        max_buffer_size=100_000,
        samples_per_epoch=15_000,
        num_workers=4,
        eval_stockfish_every=4,
        checkpoint_path=None,
        stockfish_path=None,
        stockfish_elo=2500,
        stockfish_nodes=35_000
):
    hyperparams = locals().copy()

    timestamp = datetime.now().strftime("%Y_%m_%d_%Hh%M")
    assert torch.cuda.is_available()
    gpu_device = torch.device("cuda")
    assert os.path.isfile(stockfish_path)

    model = ChessNet(num_res_blocks=num_res_blocks, num_filters=num_filters).to(gpu_device)
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    scaler = GradScaler("cuda", enabled=True)

    global_step = 0
    start_iteration = 0

    if checkpoint_path:
        checkpoint = torch.load(checkpoint_path, map_location=gpu_device, weights_only=True)
        model.load_state_dict(checkpoint["model_state_dict"])
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        scaler.load_state_dict(checkpoint["scaler_state_dict"])
        start_iteration = checkpoint.get("iteration", 0)
        global_step = checkpoint.get("global_step", 0)
        print(f"Checkpoint chargé : {checkpoint_path} (Reprise à l'itération {start_iteration})")

    wandb.init(project="alphazero-chess", name=f"{timestamp}_self_play", config=hyperparams)

    buffer_filepath = "checkpoints/replay_buffer.npz"
    replay_buffer = load_buffer(buffer_filepath)

    init_onnx_filename = f"{timestamp}_iter0_unsupervised"
    print("  Exportation et quantification du modèle vers ONNX...")
    onnx_path = f"checkpoints/{init_onnx_filename}.onnx"
    export_model_to_onnx(model, onnx_path, gpu_device)

    for iteration in range(start_iteration, start_iteration + num_iterations):
        print(f"\n{'=' * 50}")
        print(f"  ITERATION {iteration + 1}/{start_iteration + num_iterations}")
        print(f"{'=' * 50}")

        # ── 1. Phase Self-Play (C++ / ONNX) ──
        new_data, results, avg_length = generate_games(
            onnx_path, games_per_iter, num_simulations, fast_sims, num_workers=num_workers
        )

        replay_buffer.extend(new_data)
        if len(replay_buffer) > max_buffer_size:
            replay_buffer = replay_buffer[-max_buffer_size:]

        wandb.log({
            "selfplay/buffer_size": len(replay_buffer),
            "selfplay/new_positions": len(new_data),
            "selfplay/avg_game_length": avg_length,
            "selfplay/iteration": iteration + 1,
        }, step=global_step)

        print(f"  Buffer: {len(replay_buffer)} positions")

        # ── 2. Phase Training (GPU) ──
        current_batch_size = min(batch_size, len(replay_buffer))

        if current_batch_size > 0:
            global_step = train_on_buffer(
                model, optimizer, scaler, gpu_device, replay_buffer,
                epochs=train_epochs, batch_size=current_batch_size, global_step=global_step,
                samples_per_epoch=samples_per_epoch
            )
        else:
            print("  Pas assez de données pour entraîner.")

        # ── 3. Sauvegarde ──
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
        print("  Exportation et quantification du modèle vers ONNX...")
        onnx_path = f"checkpoints/{ckpt_filename}.onnx"
        export_model_to_onnx(model, onnx_path, gpu_device)
        save_buffer(replay_buffer, buffer_filepath)

        # ── 4. Évaluation Rapide ──
        if (iteration + 1) % eval_stockfish_every == 0:
            eval_winrate, eval_wins, eval_draws, eval_losses = evaluate_against_anchor(
                onnx_path=onnx_path,
                stockfish_path=stockfish_path,
                num_games=8,
                mcts_sims=400,
                sf_elo=stockfish_elo,
                sf_nodes=stockfish_nodes
            )

            wandb.log({
                "eval/winrate": eval_winrate,
                "eval/wins": eval_wins,
                "eval/draws": eval_draws,
                "eval/losses": eval_losses,
                "eval/iteration": iteration + 1,
                "eval/global_step": global_step,
            })
        else:
            print(f"  Évaluation ignorée.")

    last_timestamp = datetime.now().strftime("%Y_%m_%d_%Hh%M")
    ckpt_onnx_final_path = f"checkpoints/{last_timestamp}_last_unsupervised.onnx"
    export_model_to_onnx(model, ckpt_onnx_final_path, gpu_device)

    wandb.finish()


if __name__ == "__main__":
    mp.set_start_method('spawn', force=True)

    try:
        pipeline(
            num_iterations=40,
            games_per_iter=128,
            num_workers=8,
            num_simulations=700,
            fast_sims=100,
            train_epochs=1,
            batch_size=1024,
            learning_rate=3e-5,
            max_buffer_size=100_000,
            samples_per_epoch=60_000,
            eval_stockfish_every=4,
            checkpoint_path="checkpoints/2026_03_17_15h08_iter34_unsupervised.pt",
            stockfish_path=r"D:\logiciels\stockfish\stockfish.exe",
            stockfish_elo=2200,
            stockfish_nodes=200_000
        )
    except KeyboardInterrupt:
        print("\n[Interruption] Entraînement stoppé manuellement.")
        print("Synchronisation des dernières métriques avec WandB en cours...")
        wandb.finish()
        print("Arrêt propre terminé.")

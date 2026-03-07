import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
import lightning as L
from lightning.pytorch.loggers import WandbLogger
from lightning.pytorch.callbacks import ModelCheckpoint

import chess_engine
from lib import decode_move_index
from mcts import MCTS
from model import ChessNet
from train import AlphaZeroLightning


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
            torch.tensor([value], dtype=torch.float32)
        )


# ============================================================
#                     MODULE LIGHTNING
# ============================================================

class AlphaZeroSelfPlay(L.LightningModule):
    def __init__(self, learning_rate=1e-3, num_res_blocks=10, num_filters=128):
        super().__init__()
        self.save_hyperparameters()
        self.model = ChessNet(num_res_blocks=num_res_blocks, num_filters=num_filters)

    def forward(self, x):
        return self.model(x)

    def training_step(self, batch, batch_idx):
        x, target_pi, y_value = batch
        p_logits, v_pred = self(x)

        # Policy : cross-entropie avec le vecteur de probabilités MCTS
        log_probs = F.log_softmax(p_logits, dim=1)
        policy_loss = -torch.sum(target_pi * log_probs, dim=1).mean()

        # Value : MSE
        value_loss = F.mse_loss(v_pred, y_value)

        loss = policy_loss + value_loss

        self.log("train/loss", loss, prog_bar=True)
        self.log("train/policy_loss", policy_loss)
        self.log("train/value_loss", value_loss)

        return loss

    def configure_optimizers(self):
        return torch.optim.Adam(self.parameters(), lr=self.hparams.learning_rate)


# ============================================================
#                     SELF-PLAY
# ============================================================

def self_play_game(model, device, num_simulations=200, max_moves=300):
    board = chess_engine.Chessboard()
    board.set_startup_pieces()

    history = []
    move_num = 0

    while board.game_state == chess_engine.GameState.ONGOING and move_num < max_moves:
        tensor_np = board.get_alphazero_tensor()
        pi, _ = MCTS.mcts_search(board, model, device, num_simulations)

        # Température : échantillonner les 30 premiers coups, greedy après
        if move_num < 30:
            probs = pi.copy()
            probs /= probs.sum()
            chosen_idx = np.random.choice(4672, p=probs)
        else:
            chosen_idx = np.argmax(pi)

        history.append((tensor_np, pi))

        is_black = (board.turn == chess_engine.Color.BLACK)
        orig_f, orig_r, dest_f, dest_r, promo = decode_move_index(board, chosen_idx, is_black)
        board.move_piece(orig_f, orig_r, dest_f, dest_r, promo)
        move_num += 1

    # Résultat
    z = 0.0
    if board.game_state == chess_engine.GameState.CHECKMATE:
        z = -1.0  # le joueur au trait est maté

    dataset = []
    for i, (tensor_np, pi) in enumerate(history):
        value = z if (len(history) - i) % 2 == 1 else -z
        dataset.append((tensor_np, pi, value))

    return dataset, move_num, board.game_state


def generate_games(model, device, num_games, num_simulations):
    """Génère plusieurs parties et retourne les données + métriques."""
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

    # Initialisation du module Lightning
    lit_model = AlphaZeroSelfPlay(
        learning_rate=learning_rate,
        num_res_blocks=num_res_blocks,
        num_filters=num_filters,
    )

    # Chargement optionnel du checkpoint supervisé
    if checkpoint_path:
        pretrained = AlphaZeroLightning.load_from_checkpoint(
            checkpoint_path,
            num_res_blocks=num_res_blocks,
            num_filters=num_filters,
        )
        lit_model.model.load_state_dict(pretrained.model.state_dict())
        print(f"Checkpoint supervisé chargé: {checkpoint_path}")

    raw_model = lit_model.model.to(device)

    # WandB
    wandb_logger = WandbLogger(project="alphazero-chess", name="self_play")

    replay_buffer = []

    for iteration in range(num_iterations):
        print(f"\n{'=' * 50}")
        print(f"  ITERATION {iteration + 1}/{num_iterations}")
        print(f"{'=' * 50}")

        # ── 1. Self-play ──
        raw_model.eval()
        new_data, results, avg_length = generate_games(
            raw_model, device, games_per_iter, num_simulations
        )

        replay_buffer.extend(new_data)
        if len(replay_buffer) > max_buffer_size:
            replay_buffer = replay_buffer[-max_buffer_size:]

        # Log des métriques de self-play
        wandb_logger.experiment.log({
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
        dataset = SelfPlayDataset(replay_buffer)
        dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=0)

        checkpoint_callback = ModelCheckpoint(
            dirpath="checkpoints/",
            filename=f"selfplay-iter{iteration + 1}-{{step}}",
            every_n_train_steps=500,
            save_top_k=-1,
        )

        trainer = L.Trainer(
            max_epochs=train_epochs,
            logger=wandb_logger,
            callbacks=[checkpoint_callback],
            precision="16-mixed",
            log_every_n_steps=20,
            enable_progress_bar=True,
        )

        trainer.fit(lit_model, train_dataloaders=dataloader)

        # Sauvegarde explicite de fin d'itération
        save_path = f"checkpoints/selfplay_iter{iteration + 1}.ckpt"
        trainer.save_checkpoint(save_path)
        print(f"  Checkpoint sauvegardé: {save_path}")


if __name__ == "__main__":
    pipeline(
        num_iterations=10,
        games_per_iter=20,
        num_simulations=200,
        train_epochs=10,
        batch_size=256,
        checkpoint_path="checkpoints/last.ckpt",
    )
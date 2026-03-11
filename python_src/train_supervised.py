import torch

from torch.utils.data import DataLoader
import lightning as L
from lightning.pytorch.loggers import WandbLogger
from lightning.pytorch.callbacks import ModelCheckpoint

from sharded_dataset import ShardedChessDataset
from lib import AlphaZeroLightning, load_model

torch.set_float32_matmul_precision('medium')


if __name__ == "__main__":
    # --- Configuration ---
    SHARD_DIR = r"D:\dataset_cpp_chess\dataset_shards"
    BATCH_SIZE = 4096

    # --- Initialisation de WandB ---
    wandb_logger = WandbLogger(project="alphazero-chess", name="supervised_phase_2_lichess")

    # --- Préparation des Données ---
    dataset = ShardedChessDataset(SHARD_DIR, shuffle=True)

    dataloader = DataLoader(
        dataset,
        batch_size=BATCH_SIZE,
        num_workers=8,
        pin_memory=True
    )

    # --- Callbacks ---
    checkpoint_callback = ModelCheckpoint(
        dirpath="checkpoints/",
        filename="alphazero-supervised-{step}",
        every_n_train_steps=3000,
        save_top_k=-1,
        save_last=True
    )

    # --- Instanciation ---
    # 1. On instancie le wrapper Lightning avec l'architecture vierge
    model = AlphaZeroLightning(
        learning_rate=1e-3,
        num_res_blocks=10,
        num_filters=128
    )

    # --- Entraînement ---
    trainer = L.Trainer(
        max_epochs=4,
        # limit_train_batches=100,
        logger=wandb_logger,
        callbacks=[checkpoint_callback],
        precision="16-mixed",
        log_every_n_steps=50
    )

    trainer.fit(
        model,
        train_dataloaders=dataloader,
        ckpt_path="checkpoints/alphazero-supervised-step=6000.ckpt"
    )

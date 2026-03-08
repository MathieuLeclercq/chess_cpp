import torch

from torch.utils.data import DataLoader
import lightning as L
from lightning.pytorch.loggers import WandbLogger
from lightning.pytorch.callbacks import ModelCheckpoint

from dataset import ChessDataset
from lib import AlphaZeroLightning

torch.set_float32_matmul_precision('medium')


if __name__ == "__main__":
    # --- Configuration ---
    PGN_DIR = "../training_data/clean_pgns"
    BATCH_SIZE = 4096

    # --- Initialisation de WandB ---
    wandb_logger = WandbLogger(project="alphazero-chess", name="supervised_phase_1")

    # --- Préparation des Données ---
    dataset = ChessDataset(PGN_DIR)

    dataloader = DataLoader(dataset, batch_size=BATCH_SIZE, num_workers=4)

    # --- Callbacks ---
    checkpoint_callback = ModelCheckpoint(
        dirpath="checkpoints/",
        filename="alphazero-supervised-{step}",
        every_n_train_steps=3000,
        save_top_k=-1,
        save_last=True
    )

    # --- Instanciation ---
    model = AlphaZeroLightning(learning_rate=1e-3, num_res_blocks=10, num_filters=128)

    # --- Entraînement ---
    trainer = L.Trainer(
        max_epochs=1,
        # limit_train_batches=100,
        logger=wandb_logger,
        callbacks=[checkpoint_callback],
        precision="16-mixed",
        log_every_n_steps=50
    )

    trainer.fit(
        model,
        train_dataloaders=dataloader,
        # ckpt_path=r"checkpoints\alphazero-supervised-step=5000.ckpt"
    )

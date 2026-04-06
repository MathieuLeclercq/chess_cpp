import torch
from torch.nn import functional as F

from torch.utils.data import DataLoader
import lightning as L
from lightning.pytorch.loggers import WandbLogger
from lightning.pytorch.callbacks import ModelCheckpoint

from model import ChessNet
# from sharded_dataset import ShardedChessDataset
from dataset import ChessSupervisedDataset

torch.set_float32_matmul_precision('medium')


class AlphaZeroLightning(L.LightningModule):
    def __init__(self, learning_rate=1e-3, num_res_blocks=10, num_filters=128):
        super().__init__()
        self.save_hyperparameters()
        self.model = ChessNet(num_res_blocks=num_res_blocks, num_filters=num_filters)

    def forward(self, x):
        return self.model(x)

    def training_step(self, batch, batch_idx):
        x, y_policy, y_value = batch

        # Forward pass
        p_logits, v_pred = self(x)

        # 1. Perte de la Policy (Stratégie)
        policy_loss = F.cross_entropy(p_logits, y_policy)

        # 2. Perte de la Value (Évaluation)
        value_loss = F.mse_loss(v_pred, y_value)

        # 3. Précision Top-1
        # On extrait l'index du coup ayant la plus forte probabilité (dim=1)
        preds = torch.argmax(p_logits, dim=1)
        # On calcule la moyenne des prédictions correctes
        acc = (preds == y_policy).float().mean()

        # Perte totale
        loss = policy_loss + value_loss

        # Logging dynamique vers WandB
        self.log("train/loss", loss, prog_bar=True)
        self.log("train/policy_loss", policy_loss)
        self.log("train/value_loss", value_loss)
        # Logging de la précision dans la barre de progression
        self.log("train/policy_acc", acc, prog_bar=True)

        return loss

    def configure_optimizers(self):
        # L'optimiseur Adam est très robuste pour ce type de phase supervisée
        optimizer = torch.optim.Adam(self.parameters(), lr=self.hparams.learning_rate)
        return optimizer


if __name__ == "__main__":
    # --- Configuration ---
    # SHARD_DIR = r"D:\dataset_cpp_chess\dataset_shards"
    PGN_DIR = r"C:\Users\M47h1\Documents\chess_cpp\training_data\clean_pgns"
    BATCH_SIZE = 2048

    # --- Initialisation de WandB ---
    wandb_logger = WandbLogger(
        project="alphazero-chess", name="supervised_phase_3_gm",
        log_model=False
    )

    # --- Préparation des Données ---
    # Instanciation de la nouvelle classe
    dataset = ChessSupervisedDataset(PGN_DIR)

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

    # On retire l'argument ckpt_path car le modèle est déjà chargé
    trainer.fit(
        model,
        train_dataloaders=dataloader,
        ckpt_path=r"C:\Users\M47h1\Documents\chess_cpp\python_src\checkpoints"
                  r"\2026_04_06_22h25_SUPERVISED_LICHESS_NEW_MODEL.ckpt"
    )

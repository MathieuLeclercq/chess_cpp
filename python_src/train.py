import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader
import lightning as L
from lightning.pytorch.loggers import WandbLogger
from lightning.pytorch.callbacks import ModelCheckpoint

from dataset import ChessDataset
from model import ChessNet

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
        # p_logits sort de ta couche Linear sans Softmax, on utilise donc cross_entropy
        policy_loss = F.cross_entropy(p_logits, y_policy)

        # 2. Perte de la Value (Évaluation)
        # v_pred sort d'une activation Tanh (entre -1 et 1), on utilise l'erreur quadratique moyenne
        value_loss = F.mse_loss(v_pred, y_value)

        # Perte totale
        loss = policy_loss + value_loss

        # Logging dynamique vers WandB
        self.log("train/loss", loss, prog_bar=True)
        self.log("train/policy_loss", policy_loss)
        self.log("train/value_loss", value_loss)

        return loss

    def configure_optimizers(self):
        # L'optimiseur Adam est très robuste pour ce type de phase supervisée
        optimizer = torch.optim.Adam(self.parameters(), lr=self.hparams.learning_rate)
        return optimizer


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
        # limit_train_batches=1000,
        logger=wandb_logger,
        callbacks=[checkpoint_callback],
        precision="16-mixed",
        log_every_n_steps=50
    )

    trainer.fit(
        model,
        train_dataloaders=dataloader,
        ckpt_path=r"checkpoints\alphazero-supervised-step=5000.ckpt"
    )

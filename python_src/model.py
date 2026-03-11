import torch
import torch.nn as nn
import torch.nn.functional as F


class ResBlock(nn.Module):
    """Bloc résiduel standard tel que décrit dans AlphaZero."""

    def __init__(self, num_filters):
        super(ResBlock, self).__init__()
        self.conv1 = nn.Conv2d(num_filters, num_filters, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm2d(num_filters)
        self.conv2 = nn.Conv2d(num_filters, num_filters, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm2d(num_filters)

    def forward(self, x):
        residual = x
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        out += residual  # Connexion résiduelle
        return F.relu(out)


class ChessNet(nn.Module):
    def __init__(self, num_res_blocks=10, num_filters=128):
        super(ChessNet, self).__init__()

        # 1. Couche d'entrée : 119 plans (input) -> num_filters
        self.conv_input = nn.Conv2d(119, num_filters, kernel_size=3, padding=1)
        self.bn_input = nn.BatchNorm2d(num_filters)

        # 2. Corps résiduel
        self.res_blocks = nn.ModuleList([ResBlock(num_filters) for _ in range(num_res_blocks)])

        # 3. Tête de Policy (façon AlphaZero Chess)
        self.policy_conv1 = nn.Conv2d(num_filters, num_filters, kernel_size=1)
        self.policy_bn1 = nn.BatchNorm2d(num_filters)
        self.policy_conv2 = nn.Conv2d(num_filters, 73, kernel_size=1)

        # 4. Tête de Value (Évaluation de la position)
        self.value_conv = nn.Conv2d(num_filters, 1, kernel_size=1)
        self.value_bn = nn.BatchNorm2d(1)
        self.value_fc1 = nn.Linear(1 * 8 * 8, 256)
        self.value_fc2 = nn.Linear(256, 1)

    def forward(self, x):
        # x shape: (N, 119, 8, 8)
        x = F.relu(self.bn_input(self.conv_input(x)))

        for block in self.res_blocks:
            x = block(x)

        # Policy Head
        p = F.relu(self.policy_bn1(self.policy_conv1(x)))
        p = self.policy_conv2(p)  # Shape: (N, 73, 8, 8)
        p = p.view(p.size(0), -1)  # Flatten final en (N, 4672) pour la CrossEntropyLoss

        # Value Head
        v = F.relu(self.value_bn(self.value_conv(x)))
        v = v.view(v.size(0), -1)
        v = F.relu(self.value_fc1(v))
        v = torch.tanh(self.value_fc2(v))  # Sortie entre -1 et 1

        return p, v

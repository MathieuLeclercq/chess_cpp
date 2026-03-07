import math
import torch
import numpy as np

import chess_engine

from lib import decode_move_index


class MCTSNode:
    def __init__(self, prior, move=None, parent=None):
        self.move = move  # (orig_f, orig_r, dest_f, dest_r, promo)
        self.parent = parent
        self.children = {}  # move_index -> MCTSNode
        self.prior = prior  # P(s,a) donné par le réseau
        self.visit_count = 0  # N(s,a)
        self.total_value = 0.0  # W(s,a)

    def q_value(self):
        if self.visit_count == 0:
            return 0.0
        return self.total_value / self.visit_count

    def ucb_score(self, parent_visits, c_puct=1.4):
        u = c_puct * self.prior * math.sqrt(parent_visits) / (1 + self.visit_count)
        return self.q_value() + u


class MCTS:

    @staticmethod
    def is_terminal(board):
        return board.game_state != chess_engine.GameState.ONGOING

    @staticmethod
    def terminal_value(board):
        """Retourne la value du point de vue du joueur qui VIENT de jouer (le parent)."""
        state = board.game_state
        if state == chess_engine.GameState.CHECKMATE:
            return -1.0  # le joueur au trait a perdu → celui qui a joué a gagné
        return 0.0  # pat, répétition, 50 coups

    def terminal_value(board):
        """Retourne la value du point de vue du joueur qui VIENT de jouer (le parent)."""
        state = board.game_state
        if state == chess_engine.GameState.CHECKMATE:
            return -1.0  # le joueur au trait a perdu → celui qui a joué a gagné
        return 0.0  # pat, répétition, 50 coups

    @staticmethod
    def mcts_search(board, model, device, num_simulations=800, c_puct=1.4):
        """
        Retourne le vecteur de probabilités pi (basé sur les visites)
        et la value de la position racine.
        """
        root = MCTSNode(prior=0.0)

        # Expansion initiale de la racine
        MCTS.expand_node(root, board, model, device)

        for _ in range(num_simulations):
            node = root
            moves_played = 0

            # 1. SELECT — descendre dans l'arbre
            while node.children and not is_terminal(board):
                best_idx = max(node.children,
                               key=lambda idx: node.children[idx].ucb_score(node.visit_count,
                                                                            c_puct))
                node = node.children[best_idx]
                orig_f, orig_r, dest_f, dest_r, promo = node.move
                board.move_piece(orig_f, orig_r, dest_f, dest_r, promo, False)
                moves_played += 1

            # 2. EVALUATE
            if is_terminal(board):
                value = terminal_value(board)  # +1/-1/0
            elif not node.children:
                # 3. EXPAND + évaluer la feuille
                value = MCTS.expand_node(node, board, model, device)

            # 4. BACKUP — remonter en alternant le signe
            while node is not None:
                node.visit_count += 1
                node.total_value += value
                value = -value  # le parent voit la valeur inversée
                node = node.parent

            # Rembobiner le board
            for _ in range(moves_played):
                board.undo_move()

        # Construire le vecteur de policy (basé sur les visites)
        pi = np.zeros(4672, dtype=np.float32)
        for idx, child in root.children.items():
            pi[idx] = child.visit_count
        pi /= pi.sum()

        return pi, root

    @staticmethod
    def expand_node(node, board, model, device):
        tensor = torch.from_numpy(board.get_alphazero_tensor()).float().unsqueeze(0).to(device)

        with torch.no_grad():
            p_logits, v = model(tensor)

        policy = torch.softmax(p_logits, dim=1).squeeze(0).cpu().numpy()
        value = v.item()

        legal_indices = board.get_legal_move_indices()
        is_black = (board.turn == chess_engine.Color.BLACK)

        for idx in legal_indices:
            orig_f, orig_r, dest_f, dest_r, promo = decode_move_index(board, idx, is_black)
            node.children[idx] = MCTSNode(
                prior=policy[idx],
                move=(orig_f, orig_r, dest_f, dest_r, promo),
                parent=node
            )

        return value

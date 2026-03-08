import math
import torch
import numpy as np

import chess_engine

from lib import decode_move_index

_first_failure_logged = False  # en haut du fichier ou dans la classe

class MCTSNode:
    _first_failure_logged = False
    def __init__(self, prior, move=None, parent=None):
        self.move = move  # (orig_f, orig_r, dest_f, dest_r, promo)
        self.parent = parent
        self.children = {}  # move_index -> MCTSNode
        self.prior = prior  # P(s,a) donné par le réseau
        self.visit_count = 0  # N(s,a)
        self.total_value = 0.0  # W(s,a)
        self.is_terminal = False

    def q_value(self):
        if self.visit_count == 0:
            return 0.0
        return self.total_value / self.visit_count

    def ucb_score(self, parent_visits, c_puct=1.4):
        u = c_puct * self.prior * math.sqrt(parent_visits) / (1 + self.visit_count)
        return -self.q_value() + u  # négatif : le parent est l'adversaire


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

    @staticmethod
    def mcts_search(board, model, device, num_simulations=800, c_puct=1.4, add_dirichlet=False):
        """
        Retourne le vecteur de probabilités pi (basé sur les visites)
        et la value de la position racine.
        """
        root = MCTSNode(prior=0.0)

        MCTS.expand_node(root, board, model, device)

        if add_dirichlet and root.children:
            epsilon = 0.25  # Fraction du bruit (25%)
            alpha = 0.3  # Paramètre de la distribution pour les échecs

            # Génération d'un vecteur de bruit de la taille du nombre de coups légaux
            noise = np.random.dirichlet([alpha] * len(root.children))

            # Mélange des priors du réseau avec le bruit
            for i, (idx, child) in enumerate(root.children.items()):
                child.prior = (1 - epsilon) * child.prior + epsilon * noise[i]

        MCTS._first_failure_logged = False
        # Lancement des simulations
        for _ in range(num_simulations):
            node = root
            moves_played = 0

            # 1. SELECT
            while node.children and not node.is_terminal:
                best_idx = max(node.children,
                               key=lambda idx: node.children[idx].ucb_score(node.visit_count,
                                                                            c_puct))
                child = node.children[best_idx]
                orig_f, orig_r, dest_f, dest_r, promo = child.move
                success = board.move_piece(orig_f, orig_r, dest_f, dest_r, promo, False)
                if not success:
                    if not MCTS._first_failure_logged:
                        MCTS._first_failure_logged = True
                        piece = board.get_square(orig_f, orig_r).get_piece()
                        print(f"=== FIRST MCTS FAILURE ===")
                        print(
                            f"  Move: ({orig_f},{orig_r})->({dest_f},{dest_r}), promo={promo}")
                        print(
                            f"  Piece at origin: type={piece.get_type()}, color={piece.get_color()}")
                        print(f"  Board turn: {board.turn}")
                        print(f"  Move index: {best_idx}")
                        print(f"  Depth in tree: {moves_played}")
                        print(f"  Node was expanded with is_black={child.move}")
                        # Vérifier le round-trip encode/decode
                        legal = board.get_legal_move_indices()
                        print(f"  Current legal indices: {legal}")
                        print(f"  best_idx in legal: {best_idx in legal}")
                        # Re-décoder pour comparer
                        is_black = (board.turn == chess_engine.Color.BLACK)
                        re_decoded = decode_move_index(board, best_idx, is_black)
                        print(f"  Re-decoded now: {re_decoded}")
                        print(f"  Stored in node: {child.move}")
                    break  # CRUCIAL : ne pas incrémenter moves_played
                node = child
                moves_played += 1

            # 2. EVALUATE / EXPAND
            if node.is_terminal:
                # Noeud terminal déjà connu : relire la valeur directement
                if board.is_in_check():
                    value = -1.0
                else:
                    value = 0.0
            elif not node.children:
                value = MCTS.expand_node(node, board, model, device)
            else:
                value = node.q_value()  # fallback, ne devrait pas arriver

            # 3. BACKUP
            while node is not None:
                node.visit_count += 1
                node.total_value += value
                value = -value
                node = node.parent

            for _ in range(moves_played):
                board.undo_move()

        # Construire le vecteur de policy (basé sur les visites)
        pi = np.zeros(4672, dtype=np.float32)
        for idx, child in root.children.items():
            pi[idx] = child.visit_count

        sum_visits = pi.sum()
        if sum_visits > 0:
            pi /= sum_visits

        return pi, root

    @staticmethod
    def expand_node(node, board, model, device):
        legal_indices = board.get_legal_move_indices()

        # Position terminale : pas de coups légaux
        if not legal_indices:
            node.is_terminal = True
            if board.is_in_check():
                return -1.0  # mat : le joueur au trait a perdu
            else:
                return 0.0  # pat

        tensor = torch.from_numpy(board.get_alphazero_tensor()).float().unsqueeze(0).to(device)

        with torch.no_grad():
            p_logits, v = model(tensor)

        policy = torch.softmax(p_logits, dim=1).squeeze(0).cpu().numpy()
        value = v.item()

        is_black = (board.turn == chess_engine.Color.BLACK)

        if 74 in legal_indices:
            _, test_r, _, _, _ = decode_move_index(board, 74, is_black)
            # Si le board est censé être Blanc, mais qu'on génère une coordonnée Noire (rang 6)
            if board.turn == chess_engine.Color.WHITE and test_r == 6:
                print("\n" + "!" * 50)
                print("!!! PARADOXE DÉTECTÉ DANS EXPAND_NODE !!!")
                print(f"  board.turn de l'objet : {board.turn}")
                print(f"  is_black évalué à     : {is_black}")
                print(f"  decode_move_index a retourné le rang : {test_r}")
                print("!" * 50 + "\n")
        # ====================================================

        legal_probs = np.zeros(len(legal_indices), dtype=np.float32)
        for i, idx in enumerate(legal_indices):
            legal_probs[i] = policy[idx]

        sum_probs = np.sum(legal_probs)
        if sum_probs > 0:
            legal_probs /= sum_probs
        else:
            legal_probs = np.ones(len(legal_indices), dtype=np.float32) / len(legal_indices)

        for i, idx in enumerate(legal_indices):
            orig_f, orig_r, dest_f, dest_r, promo = decode_move_index(board, idx, is_black)
            node.children[idx] = MCTSNode(
                prior=legal_probs[i],
                move=(orig_f, orig_r, dest_f, dest_r, promo),
                parent=node
            )

        return value

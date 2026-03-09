import math
import torch
import numpy as np

import chess_engine

from lib import decode_move_index, move_to_san


class MCTSNode:
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
        return -self.q_value() + u


def backup(node, value):
    """Remonte la valeur dans l'arbre en alternant le signe."""
    while node is not None:
        node.visit_count += 1
        node.total_value += value
        value = -value
        node = node.parent


class MCTS:

    @staticmethod
    def select_leaf(root, board, c_puct):
        """
        Descend dans l'arbre en suivant UCB jusqu'à une feuille.
        Retourne (node, moves_played, aborted).
        """
        node = root
        moves_played = 0

        while node.children and not node.is_terminal:
            best_idx = max(
                node.children,
                key=lambda idx: node.children[idx].ucb_score(node.visit_count, c_puct)
            )
            child = node.children[best_idx]
            orig_f, orig_r, dest_f, dest_r, promo = child.move
            success = board.move_piece(orig_f, orig_r, dest_f, dest_r, promo, False)
            if not success:
                # Coup invalide — ne devrait plus arriver
                raise Exception("problème lors de la génération du coup")

            node = child
            moves_played += 1

        return node, moves_played, False

    @staticmethod
    def expand_node_from_results(node, legal_indices, decoded_moves, policy, value):
        """
        Expanse un nœud avec les résultats d'un forward pass déjà effectué.
        """
        legal_probs = np.array([policy[idx] for idx in legal_indices], dtype=np.float32)
        s = legal_probs.sum()
        if s > 0:
            legal_probs /= s
        else:
            legal_probs = np.ones(len(legal_indices), dtype=np.float32) / len(legal_indices)

        for i, idx in enumerate(legal_indices):
            node.children[idx] = MCTSNode(
                prior=legal_probs[i],
                move=decoded_moves[i],
                parent=node
            )

        return value

    @staticmethod
    def expand_node_single(node, board, model, device):
        """
        Expansion classique (un seul nœud). Utilisé pour la racine.
        """
        legal_indices = board.get_legal_move_indices()

        if not legal_indices:
            node.is_terminal = True
            if board.is_in_check():
                return -1.0
            else:
                return 0.0

        tensor = torch.from_numpy(board.get_alphazero_tensor()).float().unsqueeze(0).to(device)

        with torch.no_grad():
            p_logits, v = model(tensor)

        policy = torch.softmax(p_logits, dim=1).squeeze(0).cpu().numpy()
        value = v.item()

        is_black = (board.turn == chess_engine.Color.BLACK)

        decoded_moves = []
        for idx in legal_indices:
            decoded_moves.append(decode_move_index(board, idx, is_black))

        return MCTS.expand_node_from_results(node, legal_indices, decoded_moves, policy, value)

    @staticmethod
    def mcts_search(board, model, device, num_simulations=200, c_puct=1.4,
                    add_dirichlet=False, batch_size=1):
        """
        MCTS avec évaluation par batch.
        Collecte plusieurs feuilles, fait UN forward pass, puis expand + backup.
        """
        root = MCTSNode(prior=0.0)

        # Expansion initiale de la racine (toujours en single)
        MCTS.expand_node_single(root, board, model, device)

        # Bruit de Dirichlet sur la racine
        if add_dirichlet and root.children:
            epsilon, alpha = 0.25, 0.3
            noise = np.random.dirichlet([alpha] * len(root.children))
            for i, (idx, child) in enumerate(root.children.items()):
                child.prior = (1 - epsilon) * child.prior + epsilon * noise[i]

        sim = 0
        while sim < num_simulations:
            # ── Phase 1 : Collecter un batch de feuilles ──
            pending = []  # (node, moves_played, tensor_np, legal_indices, decoded_moves)

            for _ in range(min(batch_size, num_simulations - sim)):
                node, moves_played, aborted = MCTS.select_leaf(root, board, c_puct)

                if aborted:
                    for _ in range(moves_played):
                        board.undo_move()
                    sim += 1
                    continue

                # Cas terminal : backup immédiat, pas besoin du réseau
                if node.is_terminal:
                    value = -1.0 if board.is_in_check() else 0.0
                    backup(node, value)
                    for _ in range(moves_played):
                        board.undo_move()
                    sim += 1
                    continue

                # Feuille non-expansée : collecter les données
                if not node.children:
                    legal_indices = board.get_legal_move_indices()

                    # Vérifier si c'est en fait une position terminale
                    if not legal_indices:
                        node.is_terminal = True
                        value = -1.0 if board.is_in_check() else 0.0
                        backup(node, value)
                        for _ in range(moves_played):
                            board.undo_move()
                        sim += 1
                        continue

                    # Capturer tensor + moves AVANT de rembobiner
                    tensor_np = board.get_alphazero_tensor()
                    is_black = (board.turn == chess_engine.Color.BLACK)

                    decoded_moves = []
                    for idx in legal_indices:
                        decoded_moves.append(decode_move_index(board, idx, is_black))

                    pending.append((node, moves_played, tensor_np, legal_indices, decoded_moves))

                # Rembobiner le board pour la prochaine sélection
                for _ in range(moves_played):
                    board.undo_move()

            # ── Phase 2 : Forward pass batché ──
            if not pending:
                continue

            tensors = np.stack([p[2] for p in pending])
            batch_tensor = torch.from_numpy(tensors).float().to(device)

            with torch.no_grad():
                p_logits, v_preds = model(batch_tensor)

            policies = torch.softmax(p_logits, dim=1).cpu().numpy()
            values = v_preds.squeeze(1).cpu().numpy()

            # ── Phase 3 : Expansion + Backup ──
            for i, (node, moves_played, tensor_np, legal_indices, decoded_moves) in enumerate(
                    pending):
                policy = policies[i]
                value = float(values[i])

                MCTS.expand_node_from_results(node, legal_indices, decoded_moves, policy, value)
                backup(node, value)
                sim += 1

        # Construire le vecteur pi
        pi = np.zeros(4672, dtype=np.float32)
        for idx, child in root.children.items():
            pi[idx] = child.visit_count

        s = pi.sum()
        if s > 0:
            pi /= s

        return pi, root

    @staticmethod
    def ai_pick_move_mcts(board, model, device, num_simulations):
        """
        Utilise le MCTS pour choisir un coup et affiche l'analyse détaillée des meilleurs coups.
        """
        legal_indices = board.get_legal_move_indices()
        if not legal_indices:
            return None

        is_black = (board.turn == chess_engine.Color.BLACK)

        # --- 1. PRÉDICTION BRUTE (Avant MCTS) ---
        # On convertit le plateau en tenseur et on fait une passe dans le réseau
        tensor = torch.from_numpy(board.get_alphazero_tensor()).float().unsqueeze(0).to(device)
        model.eval()
        with torch.no_grad():
            p_logits, _ = model(tensor)

        # On masque les coups illégaux pour ne garder que la meilleure idée légale
        p_logits = p_logits[0].cpu().numpy()
        masked_logits = np.full_like(p_logits, -np.inf)
        masked_logits[legal_indices] = p_logits[legal_indices]

        best_raw_idx = int(np.argmax(masked_logits))
        orig_f, orig_r, dest_f, dest_r, promo = decode_move_index(board, best_raw_idx, is_black)
        raw_san = move_to_san(board, orig_f, orig_r, dest_f, dest_r, promo)

        print(f"\n[Réseau Brut] Coup préféré avant réflexion : {raw_san}")
        # ----------------------------------------

        # 2. Lancement de la recherche MCTS
        pi, root = MCTS.mcts_search(
            board, model, device, num_simulations=num_simulations, add_dirichlet=False,
            batch_size=16)

        # 3. Trier les indices par nombre de visites (décroissant)
        top_indices = np.argsort(pi)[::-1][:3]

        print(f"--- Analyse MCTS ({num_simulations} sims) ---")

        for i, idx in enumerate(top_indices):
            if pi[idx] == 0:
                continue  # On n'affiche pas les coups non visités

            child = root.children[idx]
            f_o, r_o, f_d, r_d, promo = child.move
            san = move_to_san(board, f_o, r_o, f_d, r_d, promo)

            # --- NOUVEAU : Valeur absolue (Blancs = Positif) ---
            # Si c'est au tour des Blancs, l'enfant (trait aux Noirs) évalue pour les Noirs -> on inverse
            # Si c'est au tour des Noirs, l'enfant (trait aux Blancs) évalue pour les Blancs -> on conserve
            val_white = -child.q_value() if not is_black else child.q_value()
            # ---------------------------------------------------

            prob = pi[idx] * 100
            visites = child.visit_count

            rank_str = f"#{i + 1}"
            print(
                f"{rank_str:3} | {san:6} | Prob: {prob:5.1f}% | Value: {val_white:+.3f} | N: {visites}")

        # 4. Le meilleur coup reste celui avec l'index 0 du tri
        best_idx = top_indices[0]
        best_move = root.children[best_idx].move

        print(f"Coup sélectionné : {move_to_san(board, *best_move)}\n")

        return best_move

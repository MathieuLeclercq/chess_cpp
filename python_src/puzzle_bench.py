"""Banc de puzzles Lichess : orchestration.

Mesure un modele sur data/puzzles_bench.txt et ecrit un CSV par puzzle plus un
rapport agrege. Le scoring vit dans bench_metrics, testable sans modele.

Voir docs/superpowers/specs/2026-08-14-puzzle-bench-design.md
"""

import os
import sys
from pathlib import Path

RACINE_PYTHON = Path(__file__).resolve().parent
if str(RACINE_PYTHON) not in sys.path:
    sys.path.insert(0, str(RACINE_PYTHON))
os.add_dll_directory(str(RACINE_PYTHON))

import chess_engine

# Un MCTS neuf est cree a chaque recherche. Au defaut de 2 097 143 entrees a
# 1040 octets, chaque instance reserverait 2,03 Gio, soit 32,5 Gio a 16
# travailleurs pour 31,4 Gio de RAM. 800 simulations ne stockent au plus que
# 800 positions distinctes, donc 8192 entrees suffisent largement.
TAILLE_TT = 8192


def exporter_onnx(chemin_pt: Path, sortie: Path) -> dict:
    """Exporte un checkpoint .pt en ONNX a axes dynamiques.

    torch n'est importe qu'ici, donc jamais dans un processus travailleur ou il
    couterait 475 Mio. L'architecture est deduite du checkpoint plutot que
    codee en dur, sans quoi un modele de taille differente casserait en
    silence.
    """
    import torch

    from model import ChessNet

    checkpoint = torch.load(chemin_pt, map_location="cpu", weights_only=True)
    etat = checkpoint["model_state_dict"]

    num_filters = etat["conv_input.weight"].shape[0]
    num_res_blocks = 1 + max(
        int(cle.split(".")[1]) for cle in etat if cle.startswith("res_blocks."))

    modele = ChessNet(num_res_blocks=num_res_blocks, num_filters=num_filters)
    modele.load_state_dict(etat)
    modele.eval()

    sortie.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        modele,
        torch.randn(1, 119, 8, 8),
        str(sortie),
        input_names=["input"],
        output_names=["policy", "value"],
        dynamic_axes={"input": {0: "batch_size"},
                      "policy": {0: "batch_size"},
                      "value": {0: "batch_size"}},
        # Sous torch 2.13 l'exporteur par defaut reclame onnxscript, absent.
        dynamo=False,
    )
    return {
        "iteration": checkpoint.get("iteration"),
        "global_step": checkpoint.get("global_step"),
        "num_res_blocks": num_res_blocks,
        "num_filters": num_filters,
    }


def resoudre_modele(chemin: Path, dossier_onnx: Path) -> tuple[Path, dict]:
    """Accepte un .onnx tel quel, ou exporte un .pt s'il le faut."""
    chemin = Path(chemin)
    if chemin.suffix == ".onnx":
        return chemin, {"iteration": None, "global_step": None,
                        "num_res_blocks": None, "num_filters": None}

    sortie = Path(dossier_onnx) / f"{chemin.stem}.onnx"
    if not sortie.exists():
        return sortie, exporter_onnx(chemin, sortie)

    # Un export deja present est reutilise, mais l'architecture est relue pour
    # le contexte du rapport.
    import torch

    checkpoint = torch.load(chemin, map_location="cpu", weights_only=True)
    etat = checkpoint["model_state_dict"]
    return sortie, {
        "iteration": checkpoint.get("iteration"),
        "global_step": checkpoint.get("global_step"),
        "num_res_blocks": 1 + max(int(c.split(".")[1]) for c in etat
                                  if c.startswith("res_blocks.")),
        "num_filters": etat["conv_input.weight"].shape[0],
    }


def faire_policy_fn(session):
    """Renvoie policy_fn(board) -> (probabilites sur les index legaux, value).

    Softmax masque sur les coups legaux. Le C++ fait un softmax sur les 4672
    sorties (onnx_evaluator.cpp:74-89) puis renormalise sur les coups legaux
    (mcts.cpp:184-198) : renormaliser un softmax global sur un sous-ensemble
    est identique a un softmax sur ce seul sous-ensemble, et un test verrouille
    l'accord.
    """
    import math

    import numpy as np

    def policy_fn(board):
        tenseur = np.asarray(board.get_alphazero_tensor(),
                             dtype=np.float32).reshape(1, 119, 8, 8)
        logits, value = session.run(None, {"input": tenseur})
        logits = logits[0]

        indices = board.get_legal_move_indices()
        maxi = max(float(logits[i]) for i in indices)
        exps = {i: math.exp(float(logits[i]) - maxi) for i in indices}
        somme = sum(exps.values())
        return ({i: e / somme for i, e in exps.items()},
                float(np.asarray(value).reshape(-1)[0]))

    return policy_fn


def faire_search_fn(evaluateur, simulations: int, c_puct: float):
    """Renvoie search_fn(board) -> distribution de visites sur 4672.

    Un MCTS neuf a chaque recherche : la table de transposition est indexee sur
    le seul Zobrist, or les positions successives d'une meme ligne ont des
    historiques differents, donc un hit renverrait une value calculee sous un
    autre historique.
    """
    def search_fn(board):
        mcts = chess_engine.MCTS(evaluateur, TAILLE_TT)
        return mcts.mcts_search(board, simulations, c_puct, False)

    return search_fn

"""Tests couples au moteur : ils ont besoin du module compile et d'un modele.

Le test d'accord du softmax est le seul garde-fou du choix d'implementation
retenu, a savoir recalculer le prior en Python plutot que d'ajouter un binding
C++. Il compare la meme grandeur des deux cotes, pas un substitut.
"""
import os
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "python_src"))
os.add_dll_directory(str(RACINE / "python_src"))

import chess_engine
from bench_metrics import charger_position, parse_bench_line

BANC = RACINE / "data" / "puzzles_bench.txt"
CHECKPOINT = (RACINE / "python_src" / "checkpoints"
              / "2026_04_23_23h25_iter316_unsupervised.pt")

pytestmark = pytest.mark.skipif(
    not CHECKPOINT.exists() or not BANC.exists(),
    reason="checkpoint ou fichier de banc absent")


@pytest.fixture(scope="module")
def modele(tmp_path_factory):
    import puzzle_bench

    dossier = tmp_path_factory.mktemp("onnx")
    return puzzle_bench.resoudre_modele(CHECKPOINT, dossier)


@pytest.fixture(scope="module")
def session(modele):
    import onnxruntime as ort

    chemin, _ = modele
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    return ort.InferenceSession(str(chemin), options,
                                providers=["CPUExecutionProvider"])


def _premier_puzzle():
    with open(BANC, encoding="utf-8") as f:
        return parse_bench_line(0, next(f))


def test_export_recupere_les_metadonnees_du_checkpoint(modele):
    _, meta = modele

    assert meta["iteration"] == 316
    assert meta["global_step"] == 19415


def test_export_deduit_l_architecture_du_checkpoint(modele):
    """La coder en dur casserait silencieusement sur un modele de taille
    differente."""
    _, meta = modele

    assert meta["num_res_blocks"] == 10
    assert meta["num_filters"] == 128


def test_la_somme_des_probabilites_vaut_un(session):
    import puzzle_bench

    board = charger_position(_premier_puzzle())
    probs, value = puzzle_bench.faire_policy_fn(session)(board)

    assert set(probs) == set(board.get_legal_move_indices())
    assert sum(probs.values()) == pytest.approx(1.0)
    assert -1.0 <= value <= 1.0


def test_le_softmax_python_egale_le_prior_du_cpp(modele, session):
    """Le C++ applique un softmax sur les 4672 sorties (onnx_evaluator.cpp)
    puis renormalise sur les coups legaux (mcts.cpp), ce qui est identique a un
    softmax sur les seuls coups legaux. L'egalite est mathematique, on la
    verifie quand meme : c'est le seul risque de l'approche retenue.
    """
    import puzzle_bench

    chemin, _ = modele
    board = charger_position(_premier_puzzle())
    probs, _ = puzzle_bench.faire_policy_fn(session)(board)

    # Cote C++ : step_analysis renseigne m_analysis_root, et
    # get_analysis_results expose le prior des enfants visites.
    evaluateur = chess_engine.ONNXEvaluator(str(chemin), False)
    mcts = chess_engine.MCTS(evaluateur, puzzle_bench.TAILLE_TT)
    mcts.step_analysis(board, 400, 1.4)
    stats = mcts.get_analysis_results()

    assert stats, "aucun coup visite, le test ne verifierait rien"

    for s in stats:
        assert s.move_idx in probs, f"index {s.move_idx} absent du softmax Python"
        assert s.prior == pytest.approx(probs[s.move_idx], rel=1e-4, abs=1e-6)

    assert len(stats) >= 5, f"seulement {len(stats)} priors compares"


def test_la_recherche_renvoie_une_distribution_de_visites(modele):
    import puzzle_bench

    chemin, _ = modele
    evaluateur = chess_engine.ONNXEvaluator(str(chemin), False)
    search_fn = puzzle_bench.faire_search_fn(evaluateur, 64, 1.4)

    board = charger_position(_premier_puzzle())
    pi = search_fn(board)

    assert len(pi) == 4672
    assert sum(pi) == pytest.approx(1.0)
    legaux = set(board.get_legal_move_indices())
    assert all(pi[i] == 0.0 for i in range(4672) if i not in legaux)


def test_la_taille_de_tt_reste_petite():
    """Au defaut de 2 097 143 entrees a 1040 octets, chaque MCTS reserverait
    2,03 Gio, soit 32,5 Gio a 16 travailleurs pour 31,4 Gio de RAM. Un MCTS
    neuf est cree a chaque recherche."""
    import puzzle_bench

    assert puzzle_bench.TAILLE_TT <= 65536

# Banc de puzzles Lichess : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mesurer la force tactique d'un modèle sur les 5 000 puzzles de `data/puzzles_bench.txt`, en produisant un CSV par puzzle et un rapport agrégé.

**Architecture:** Deux modules Python. `bench_metrics.py` porte la logique pure, dont les deux accès au réseau sont injectés (`policy_fn`, `search_fn`), ce qui rend tout le scoring testable sans modèle. `puzzle_bench.py` porte l'orchestration : CLI, export ONNX, pool de 16 processus, écriture du CSV et du rapport. Aucun changement C++.

**Tech Stack:** Python 3.13, `chess_engine` (module pybind11 compilé), onnxruntime 1.24.3 CPU, torch (export ONNX uniquement, dans le processus parent), pytest.

Spec de référence : `docs/superpowers/specs/2026-08-14-puzzle-bench-design.md`.

## Global Constraints

- **`tt_size` doit valoir 8192, jamais le défaut.** Une `TTEntry` pèse 1040 octets et le défaut de `MCTS.__init__` est 2 097 143 entrées, soit 2,03 Gio par instance. Le design crée un `MCTS` neuf à chaque recherche et tourne à 16 processus : au défaut cela demanderait 32,5 Gio pour 31,4 Gio de RAM disponibles.
- **Ne jamais importer `torch` dans un processus travailleur.** torch et onnx coûtent 475 Mio à l'import, contre 20 Mio pour onnxruntime et 2 Mio pour `chess_engine`. C'est la raison d'être de la tâche 1.
- **`add_dirichlet=False` explicite** à chaque appel de `mcts_search`.
- **`OMP_NUM_THREADS=1`** posé dans le processus parent avant la création du pool, pour être hérité. Le poser dans l'initialiseur du travailleur serait trop tard sous Windows, qui utilise `spawn` et réimporte le module avant d'exécuter l'initialiseur.
- **`intra_op_num_threads = 1`** sur la `SessionOptions` onnxruntime, indépendamment de la variable d'environnement.
- **`use_gpu=False`.** Mesuré : le GPU n'apporte rien à batch 1 (376 sims/s contre 373 sur CPU) et ne monte pas à l'échelle (352 sims/s à 8 processus).
- **Comparer des index de policy, jamais des chaînes UCI**, pour décider si un coup est le bon. L'encodage est injectif sur les coups légaux, alors que deux mises en forme UCI peuvent différer (promotion dame implicite, roque).
- Le module compilé et ses DLL vivent dans `python_src/`. Tout script doit faire `os.add_dll_directory` sur ce répertoire avant `import chess_engine`.
- Pas de tiret cadratin dans le code, les commentaires ou les messages de commit. Pas de ligne `Co-Authored-By`.
- Commandes : `cmake` hors PATH, voir la mémoire projet. Tests : `.venv/Scripts/python.exe -m pytest python_src/tests -q`.

---

### Task 1: Extraire l'encodage des coups dans un module sans torch

**Files:**
- Create: `python_src/move_coding.py`
- Modify: `python_src/lib.py:17-53` (`encode_move`), `:55-102` (`decode_move_index`), `:200-207` (`gestion_promo_dame`), `:423-446` (`parse_uci_to_coords`), `:448-470` (`coords_to_uci`)
- Test: `python_src/tests/test_move_coding.py`

**Interfaces:**
- Consomme : rien.
- Produit : `move_coding.encode_move(orig_f, orig_r, dest_f, dest_r, promotion_type, is_black_turn) -> int`, `move_coding.decode_move_index(board, index, is_black) -> tuple[int, int, int, int, PieceType]`, `move_coding.parse_uci_to_coords(uci_str) -> tuple[int, int, int, int, PieceType]`, `move_coding.coords_to_uci(orig_f, orig_r, dest_f, dest_r, promotion) -> str`, `move_coding.gestion_promo_dame(board, orig_f, orig_r, dest_r, promo) -> PieceType`. `lib` les réexporte, tous les appelants existants continuent de faire `from lib import ...`.

Les cinq fonctions sont **déplacées sans changer une ligne de leur corps**. Le seul import de `move_coding.py` est `import chess_engine`.

Appelants existants à ne pas casser, tous en `from lib import` : `convert_pgn_to_binary.py:4`, `dataset.py:7`, `play_against_bot.py:17`, `stockfish_player.py:9`, `uci.py:7`.

- [ ] **Step 1: Écrire le test d'aller-retour, qui échoue faute de module**

```python
"""Verrouille l'encodage index de policy contre coup, la brique dont depend
tout le scoring du banc. Un aller-retour faux ferait mesurer n'importe quoi."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.add_dll_directory(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chess_engine
from move_coding import coords_to_uci, decode_move_index, encode_move, parse_uci_to_coords

# Positions choisies pour couvrir les noirs au trait, les promotions et le roque.
POSITIONS = [
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R b KQkq - 0 1",
    "8/PPPPPPPP/8/8/8/8/1ppppppp/k6K w - - 0 1",
    "8/PPPPPPPP/8/8/8/8/1ppppppp/k6K b - - 0 1",
]


def _board(fen):
    board = chess_engine.Chessboard()
    board.load_fen(fen)
    return board


@pytest.mark.parametrize("fen", POSITIONS)
def test_encode_decode_round_trip_on_every_legal_move(fen):
    board = _board(fen)
    is_black = board.turn == chess_engine.Color.BLACK
    indices = board.get_legal_move_indices()

    assert indices, f"aucun coup legal dans {fen}"

    for index in indices:
        o_f, o_r, d_f, d_r, promo = decode_move_index(board, index, is_black)
        assert encode_move(o_f, o_r, d_f, d_r, promo, is_black) == index


@pytest.mark.parametrize("fen", POSITIONS)
def test_uci_round_trip_on_every_legal_move(fen):
    """Le banc lit des coups en UCI et doit les retrouver comme index."""
    board = _board(fen)
    is_black = board.turn == chess_engine.Color.BLACK

    for index in board.get_legal_move_indices():
        uci = coords_to_uci(*decode_move_index(board, index, is_black))
        o_f, o_r, d_f, d_r, promo = parse_uci_to_coords(uci)
        promo = chess_engine.PieceType.QUEEN if (
            promo == chess_engine.PieceType.NONE
            and board.get_square(o_f, o_r).get_piece().get_type() == chess_engine.PieceType.PAWN
            and d_r in (0, 7)
        ) else promo
        assert encode_move(o_f, o_r, d_f, d_r, promo, is_black) == index


def test_move_coding_does_not_import_torch():
    """La raison d'etre du module : 16 travailleurs qui importent torch
    coutent environ 8 Gio de RAM, contre moins de 1 Gio sans lui."""
    import subprocess

    racine = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    code = (
        "import os, sys; sys.path.insert(0, r'%s'); "
        "os.add_dll_directory(r'%s'); "
        "import move_coding; "
        "assert 'torch' not in sys.modules, sorted(k for k in sys.modules if 'torch' in k)"
    ) % (racine, racine)
    subprocess.run([sys.executable, "-c", code], check=True)
```

- [ ] **Step 2: Lancer le test et vérifier l'échec**

Run: `.venv/Scripts/python.exe -m pytest python_src/tests/test_move_coding.py -q`
Attendu : ÉCHEC, `ModuleNotFoundError: No module named 'move_coding'`.

- [ ] **Step 3: Créer `move_coding.py` en déplaçant les cinq fonctions**

Couper depuis `lib.py` les corps de `encode_move` (17-53), `decode_move_index` (55-102), `gestion_promo_dame` (200-207), `parse_uci_to_coords` (423-446) et `coords_to_uci` (448-470), les coller tels quels dans `move_coding.py` sous cet en-tête :

```python
"""Encodage et decodage des coups pour la policy AlphaZero, 4672 index.

Extrait de lib.py pour etre importable sans torch : le banc de puzzles fait
tourner 16 processus travailleurs, et torch coute 475 Mio a l'import contre
2 Mio pour chess_engine. Les corps de ces fonctions n'ont pas change, lib les
reexporte pour ne casser aucun appelant.
"""

import chess_engine
```

- [ ] **Step 4: Faire réexporter par `lib.py`**

Remplacer dans `lib.py` les cinq définitions supprimées par, juste après les imports existants :

```python
# Reexport : ces fonctions vivent desormais dans move_coding, importable sans
# torch. Les appelants historiques font `from lib import encode_move`, etc.
from move_coding import (  # noqa: F401
    coords_to_uci,
    decode_move_index,
    encode_move,
    gestion_promo_dame,
    parse_uci_to_coords,
)
```

- [ ] **Step 5: Lancer les tests, vérifier qu'ils passent et que rien n'est cassé**

Run: `.venv/Scripts/python.exe -m pytest python_src/tests -q`
Attendu : tous les tests passent, y compris les 35 déjà présents.

Run: `.venv/Scripts/python.exe -c "import sys, os; sys.path.insert(0,'python_src'); os.add_dll_directory(os.path.abspath('python_src')); import uci, dataset, stockfish_player; print('imports ok')"`
Attendu : `imports ok`. Ce contrôle vaut la peine parce qu'aucun test ne couvre `uci.py`.

- [ ] **Step 6: Commit**

```bash
git add python_src/move_coding.py python_src/lib.py python_src/tests/test_move_coding.py
git commit -m "Extrait l'encodage des coups dans un module sans torch"
```

---

### Task 2: Lecture d'une ligne du banc

**Files:**
- Create: `python_src/bench_metrics.py`
- Test: `python_src/tests/test_bench_metrics.py`

**Interfaces:**
- Consomme : rien.
- Produit : `BenchPuzzle` (dataclass gelée, champs `ligne: int`, `fen_initiale: str`, `coups_uci: list[str]`, `solution_uci: list[str]`, `rating: int`, `themes: str`) et `parse_bench_line(index: int, ligne: str) -> BenchPuzzle`.

- [ ] **Step 1: Écrire les tests**

```python
"""Tests du noyau de mesure du banc. Aucun modele, aucun processus : les deux
acces au reseau sont injectes."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.add_dll_directory(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bench_metrics import BenchPuzzle, parse_bench_line

LIGNE = (
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    "|e2e4 e7e5 g1f3 b8c6 f1b5"
    "|a7a6 b5c6"
    "|1615"
    "|crushing discoveredAttack middlegame short"
)


def test_parse_bench_line_splits_the_five_fields():
    puzzle = parse_bench_line(7, LIGNE + "\n")

    assert puzzle.ligne == 7
    assert puzzle.fen_initiale.startswith("rnbqkbnr/")
    assert puzzle.coups_uci == ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"]
    assert puzzle.solution_uci == ["a7a6", "b5c6"]
    assert puzzle.rating == 1615
    assert puzzle.themes == "crushing discoveredAttack middlegame short"


def test_parse_bench_line_is_the_inverse_of_format_line():
    """Verrouille les deux modules ensemble : si build_puzzle_dataset change
    l'ordre des champs, ce test tombe au lieu de laisser le banc lire de
    travers."""
    import chess
    from build_puzzle_dataset import MatchResult, PuzzleRow, format_line

    row = PuzzleRow(
        puzzle_id="abc12",
        fen="8/8/8/8/8/8/8/K6k w - - 0 1",
        moves=["f1b5", "a7a6", "b5c6"],
        rating=1500,
        themes="mateIn2 short",
        game_url="https://lichess.org/testtest#4",
    )
    match = MatchResult(start_fen=chess.STARTING_FEN,
                        moves_uci=["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"])

    puzzle = parse_bench_line(0, format_line(row, match))

    assert puzzle.fen_initiale == chess.STARTING_FEN
    assert puzzle.coups_uci == ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"]
    assert puzzle.solution_uci == ["a7a6", "b5c6"]
    assert puzzle.rating == 1500
    assert puzzle.themes == "mateIn2 short"


def test_parse_bench_line_rejects_a_wrong_field_count():
    with pytest.raises(ValueError):
        parse_bench_line(0, "un|deux|trois\n")
```

- [ ] **Step 2: Lancer et vérifier l'échec**

Run: `.venv/Scripts/python.exe -m pytest python_src/tests/test_bench_metrics.py -q`
Attendu : ÉCHEC, `ModuleNotFoundError: No module named 'bench_metrics'`.

- [ ] **Step 3: Implémenter**

```python
"""Noyau de mesure du banc de puzzles.

Toute la logique de scoring vit ici et recoit ses deux acces au reseau par
injection, policy_fn et search_fn, sur le modele du fetcher de
lichess_games.fetch_games. Ce module n'importe donc ni torch ni onnxruntime, et
se teste entierement avec des faux.

Voir docs/superpowers/specs/2026-08-14-puzzle-bench-design.md
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BenchPuzzle:
    ligne: int
    fen_initiale: str
    coups_uci: list[str]
    solution_uci: list[str]
    rating: int
    themes: str


def parse_bench_line(index: int, ligne: str) -> BenchPuzzle:
    """Inverse de build_puzzle_dataset.format_line.

    Le fichier du banc ne contient pas le PuzzleId : l'index de ligne est donc
    l'identifiant, ce qui impose de ne jamais reordonner le fichier.
    """
    champs = ligne.rstrip("\n").split("|")
    if len(champs) != 5:
        raise ValueError(
            f"ligne {index} : {len(champs)} champs au lieu de 5")
    fen, coups, solution, rating, themes = champs
    return BenchPuzzle(
        ligne=index,
        fen_initiale=fen,
        coups_uci=coups.split(),
        solution_uci=solution.split(),
        rating=int(rating),
        themes=themes,
    )
```

- [ ] **Step 4: Lancer et vérifier le succès**

Run: `.venv/Scripts/python.exe -m pytest python_src/tests/test_bench_metrics.py -q`
Attendu : 3 tests passent.

- [ ] **Step 5: Commit**

```bash
git add python_src/bench_metrics.py python_src/tests/test_bench_metrics.py
git commit -m "Lit une ligne du banc de puzzles"
```

---

### Task 3: Chargement de la position et mesure d'un puzzle

**Files:**
- Modify: `python_src/bench_metrics.py`
- Modify: `python_src/tests/test_bench_metrics.py`

**Interfaces:**
- Consomme : `BenchPuzzle` et `parse_bench_line` de la tâche 2, `move_coding.encode_move`, `move_coding.parse_uci_to_coords`, `move_coding.decode_move_index`, `move_coding.coords_to_uci`, `move_coding.gestion_promo_dame` de la tâche 1.
- Produit :
  - `uci_to_index(board, uci: str) -> int`
  - `index_to_uci(board, index: int) -> str`
  - `charger_position(puzzle: BenchPuzzle, sans_historique: bool = False)` renvoyant un `chess_engine.Chessboard`, lève `DonneesInvalides`
  - `class DonneesInvalides(Exception)`
  - `PuzzleMeasure` (dataclass gelée, champs listés dans le code ci-dessous)
  - `measure_puzzle(puzzle, policy_fn, search_fn, sans_historique=False, horloge=time.perf_counter) -> PuzzleMeasure`

`policy_fn(board)` doit renvoyer `(probs: dict[int, float], value: float)`, les probabilités portant sur les index légaux uniquement. `search_fn(board)` doit renvoyer une séquence de 4672 flottants, la distribution de visites normalisée.

- [ ] **Step 1: Écrire les tests**

À ajouter à `python_src/tests/test_bench_metrics.py` :

```python
import chess_engine
from bench_metrics import (
    DonneesInvalides,
    charger_position,
    measure_puzzle,
    uci_to_index,
)


def _puzzle(coups, solution, fen=None):
    return BenchPuzzle(
        ligne=0,
        fen_initiale=fen or "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        coups_uci=coups,
        solution_uci=solution,
        rating=1500,
        themes="fork short",
    )


def _faux_reseau(board, coup_prefere, p=0.7):
    """policy_fn factice : met p sur coup_prefere, repartit le reste."""
    indices = board.get_legal_move_indices()
    cible = uci_to_index(board, coup_prefere)
    reste = (1.0 - p) / max(1, len(indices) - 1)
    probs = {i: (p if i == cible else reste) for i in indices}
    return probs, 0.25


def _fausse_recherche(board, coup_choisi):
    """search_fn factice : toutes les visites sur coup_choisi."""
    pi = [0.0] * 4672
    pi[uci_to_index(board, coup_choisi)] = 1.0
    return pi


def test_charger_position_rejoue_l_historique():
    puzzle = _puzzle(["e2e4", "e7e5", "g1f3"], ["b8c6"])
    board = charger_position(puzzle)

    assert board.turn == chess_engine.Color.BLACK
    assert chess_engine.PieceType.KNIGHT == board.get_square(5, 2).get_piece().get_type()


def test_charger_position_refuse_un_historique_illegal():
    puzzle = _puzzle(["e2e4", "e2e4"], ["b8c6"])

    with pytest.raises(DonneesInvalides):
        charger_position(puzzle)


def test_charger_position_sans_historique_donne_la_meme_position():
    """Le bras sans historique repart de la FEN atteinte, ce qui vide les plans
    d'historique du tenseur sans changer la position."""
    puzzle = _puzzle(["e2e4", "e7e5", "g1f3"], ["b8c6"])

    avec = charger_position(puzzle)
    sans = charger_position(puzzle, sans_historique=True)

    assert avec.to_fen() == sans.to_fen()
    assert avec.get_alphazero_tensor().shape == sans.get_alphazero_tensor().shape
    # Les plans d'historique differencient les deux tenseurs.
    assert not (avec.get_alphazero_tensor() == sans.get_alphazero_tensor()).all()


def test_measure_puzzle_compte_une_reussite_au_premier_coup():
    puzzle = _puzzle(["e2e4", "e7e5", "g1f3"], ["b8c6"])

    mesure = measure_puzzle(
        puzzle,
        policy_fn=lambda b: _faux_reseau(b, "b8c6"),
        search_fn=lambda b: _fausse_recherche(b, "b8c6"),
    )

    assert mesure.erreur == ""
    assert mesure.reussi_reseau is True
    assert mesure.reussi_recherche is True
    assert mesure.reussi_ligne is True
    assert mesure.premier_ecart == -1
    assert mesure.coup_reseau == "b8c6"
    assert mesure.coup_recherche == "b8c6"
    assert mesure.p_correct_reseau == pytest.approx(0.7)
    assert mesure.rang_correct_reseau == 1
    assert mesure.part_visites_correct == pytest.approx(1.0)
    assert mesure.nb_recherches == 1


def test_measure_puzzle_compte_un_echec_et_le_rang_du_bon_coup():
    puzzle = _puzzle(["e2e4", "e7e5", "g1f3"], ["b8c6"])

    mesure = measure_puzzle(
        puzzle,
        policy_fn=lambda b: _faux_reseau(b, "g8f6"),
        search_fn=lambda b: _fausse_recherche(b, "g8f6"),
    )

    assert mesure.reussi_reseau is False
    assert mesure.reussi_recherche is False
    assert mesure.reussi_ligne is False
    assert mesure.premier_ecart == 0
    assert mesure.coup_recherche == "g8f6"
    assert mesure.rang_correct_reseau > 1
    assert mesure.part_visites_correct == pytest.approx(0.0)
    assert mesure.nb_recherches == 1


def test_measure_puzzle_suit_une_ligne_de_trois_coups():
    """Les coups du solveur sont aux index pairs. Ici deux recherches."""
    puzzle = _puzzle(["e2e4", "e7e5", "g1f3", "b8c6"], ["f1b5", "a7a6", "b5c6"])

    mesure = measure_puzzle(
        puzzle,
        policy_fn=lambda b: _faux_reseau(b, "f1b5"),
        search_fn=lambda b: _fausse_recherche(
            b, "f1b5" if b.get_square(5, 0).get_piece().get_type()
            == chess_engine.PieceType.BISHOP else "b5c6"),
    )

    assert mesure.reussi_recherche is True
    assert mesure.reussi_ligne is True
    assert mesure.premier_ecart == -1
    assert mesure.nb_recherches == 2


def test_measure_puzzle_s_arrete_au_premier_ecart_de_la_ligne():
    puzzle = _puzzle(["e2e4", "e7e5", "g1f3", "b8c6"], ["f1b5", "a7a6", "b5c6"])

    # Le premier coup est bon, le second coup solveur (index 2) est faux.
    def recherche(board):
        if board.get_square(5, 0).get_piece().get_type() == chess_engine.PieceType.BISHOP:
            return _fausse_recherche(board, "f1b5")
        return _fausse_recherche(board, "b5a4")

    mesure = measure_puzzle(
        puzzle,
        policy_fn=lambda b: _faux_reseau(b, "f1b5"),
        search_fn=recherche,
    )

    assert mesure.reussi_recherche is True     # le premier coup reste bon
    assert mesure.reussi_ligne is False
    assert mesure.premier_ecart == 2
    assert mesure.nb_recherches == 2


def test_measure_puzzle_signale_une_solution_illegale():
    """Second controle independant de la correction du pipeline : si
    solution[0] n'est pas legal, on compte au lieu de planter."""
    puzzle = _puzzle(["e2e4", "e7e5", "g1f3"], ["e2e4"])

    mesure = measure_puzzle(
        puzzle,
        policy_fn=lambda b: _faux_reseau(b, "b8c6"),
        search_fn=lambda b: _fausse_recherche(b, "b8c6"),
    )

    assert mesure.erreur == "solution_illegale"
    assert mesure.nb_recherches == 0
```

- [ ] **Step 2: Lancer et vérifier l'échec**

Run: `.venv/Scripts/python.exe -m pytest python_src/tests/test_bench_metrics.py -q`
Attendu : ÉCHEC à l'import, `cannot import name 'measure_puzzle'`.

- [ ] **Step 3: Implémenter**

À ajouter à `python_src/bench_metrics.py`, après `parse_bench_line` :

```python
import time

import chess_engine
from move_coding import (
    coords_to_uci,
    decode_move_index,
    encode_move,
    gestion_promo_dame,
    parse_uci_to_coords,
)

TAILLE_POLICY = 4672


class DonneesInvalides(Exception):
    """La ligne du banc ne decrit pas une position jouable."""

    def __init__(self, cause: str):
        super().__init__(cause)
        self.cause = cause


def uci_to_index(board, uci: str) -> int:
    """Index de policy d'un coup UCI dans la position courante.

    La promotion dame est implicite dans la convention AlphaZero : Lichess
    ecrit bien le suffixe, mais gestion_promo_dame couvre le cas ou il manque.
    """
    o_f, o_r, d_f, d_r, promo = parse_uci_to_coords(uci)
    promo = gestion_promo_dame(board, o_f, o_r, d_r, promo)
    is_black = board.turn == chess_engine.Color.BLACK
    return encode_move(o_f, o_r, d_f, d_r, promo, is_black)


def index_to_uci(board, index: int) -> str:
    is_black = board.turn == chess_engine.Color.BLACK
    return coords_to_uci(*decode_move_index(board, index, is_black))


def charger_position(puzzle: BenchPuzzle, sans_historique: bool = False):
    """Rejoue l'historique cote C++, ce qui construit les plans d'historique.

    On ne reconstruit jamais le tenseur en Python : le banc reste ainsi
    insensible a un changement de representation.
    """
    board = chess_engine.Chessboard()
    board.load_fen(puzzle.fen_initiale)
    for coup in puzzle.coups_uci:
        if not board.move_piece_uci(coup):
            raise DonneesInvalides("historique_illegal")

    if sans_historique:
        # Recharger la FEN atteinte donne la meme position sans passe.
        atteinte = board.to_fen()
        board = chess_engine.Chessboard()
        board.load_fen(atteinte)
    return board


@dataclass(frozen=True)
class PuzzleMeasure:
    ligne: int
    rating: int
    themes: str
    plies_historique: int
    nb_coups_legaux: int
    coup_reseau: str
    reussi_reseau: bool
    p_correct_reseau: float
    rang_correct_reseau: int
    value_reseau: float
    coup_recherche: str
    reussi_recherche: bool
    part_visites_correct: float
    reussi_ligne: bool
    premier_ecart: int
    nb_recherches: int
    duree_s: float
    erreur: str


def _mesure_en_erreur(puzzle: BenchPuzzle, cause: str,
                      duree: float) -> PuzzleMeasure:
    return PuzzleMeasure(
        ligne=puzzle.ligne, rating=puzzle.rating, themes=puzzle.themes,
        plies_historique=len(puzzle.coups_uci), nb_coups_legaux=0,
        coup_reseau="", reussi_reseau=False, p_correct_reseau=0.0,
        rang_correct_reseau=0, value_reseau=0.0,
        coup_recherche="", reussi_recherche=False, part_visites_correct=0.0,
        reussi_ligne=False, premier_ecart=-1, nb_recherches=0,
        duree_s=duree, erreur=cause,
    )


def measure_puzzle(puzzle: BenchPuzzle, policy_fn, search_fn,
                   sans_historique: bool = False,
                   horloge=time.perf_counter) -> PuzzleMeasure:
    """Mesure un puzzle : colonne reseau seul, puis colonne recherche.

    policy_fn(board) -> (probs sur les index legaux, value)
    search_fn(board) -> sequence de 4672 flottants, visites normalisees

    Les comparaisons portent sur des index de policy et jamais sur des chaines
    UCI : l'encodage est injectif sur les coups legaux, alors que deux mises en
    forme UCI peuvent differer.
    """
    debut = horloge()

    if not puzzle.solution_uci:
        return _mesure_en_erreur(puzzle, "solution_vide", horloge() - debut)

    try:
        board = charger_position(puzzle, sans_historique)
    except DonneesInvalides as exc:
        return _mesure_en_erreur(puzzle, exc.cause, horloge() - debut)

    legaux = set(board.get_legal_move_indices())
    nb_coups_legaux = len(legaux)
    idx_attendu = uci_to_index(board, puzzle.solution_uci[0])
    if idx_attendu not in legaux:
        return _mesure_en_erreur(puzzle, "solution_illegale", horloge() - debut)

    # --- Colonne reseau seul ---
    probs, value = policy_fn(board)
    p_correct = probs.get(idx_attendu, 0.0)
    rang = 1 + sum(1 for p in probs.values() if p > p_correct)
    idx_reseau = max(probs, key=probs.get)
    coup_reseau = index_to_uci(board, idx_reseau)
    reussi_reseau = idx_reseau == idx_attendu

    # --- Colonne recherche, premier coup puis ligne complete ---
    coup_recherche = ""
    reussi_recherche = False
    part_visites = 0.0
    premier_ecart = -1
    nb_recherches = 0

    for rang_ply, coup_attendu in enumerate(puzzle.solution_uci):
        if rang_ply % 2 == 0:
            idx_ply = uci_to_index(board, coup_attendu)
            if idx_ply not in set(board.get_legal_move_indices()):
                premier_ecart = rang_ply
                return _remplir(puzzle, board, nb_coups_legaux, coup_reseau,
                                reussi_reseau, p_correct, rang, value,
                                coup_recherche, reussi_recherche, part_visites,
                                premier_ecart, nb_recherches,
                                horloge() - debut, "ligne_illegale")

            pi = search_fn(board)
            nb_recherches += 1
            idx_choisi = max(range(TAILLE_POLICY), key=lambda i: pi[i])

            if rang_ply == 0:
                coup_recherche = index_to_uci(board, idx_choisi)
                part_visites = float(pi[idx_ply])
                reussi_recherche = idx_choisi == idx_ply

            if idx_choisi != idx_ply:
                premier_ecart = rang_ply
                break

        if not board.move_piece_uci(coup_attendu):
            premier_ecart = rang_ply
            return _remplir(puzzle, board, nb_coups_legaux, coup_reseau,
                            reussi_reseau, p_correct, rang, value,
                            coup_recherche, reussi_recherche, part_visites,
                            premier_ecart, nb_recherches,
                            horloge() - debut, "ligne_illegale")

    return _remplir(puzzle, board, nb_coups_legaux, coup_reseau, reussi_reseau,
                    p_correct, rang, value, coup_recherche, reussi_recherche,
                    part_visites, premier_ecart, nb_recherches,
                    horloge() - debut, "")


def _remplir(puzzle, board, nb_coups_legaux, coup_reseau, reussi_reseau,
             p_correct, rang, value, coup_recherche, reussi_recherche,
             part_visites, premier_ecart, nb_recherches, duree,
             erreur) -> PuzzleMeasure:
    return PuzzleMeasure(
        ligne=puzzle.ligne, rating=puzzle.rating, themes=puzzle.themes,
        plies_historique=len(puzzle.coups_uci),
        nb_coups_legaux=nb_coups_legaux,
        coup_reseau=coup_reseau, reussi_reseau=reussi_reseau,
        p_correct_reseau=float(p_correct), rang_correct_reseau=rang,
        value_reseau=float(value),
        coup_recherche=coup_recherche, reussi_recherche=reussi_recherche,
        part_visites_correct=part_visites,
        reussi_ligne=(premier_ecart == -1 and erreur == ""),
        premier_ecart=premier_ecart, nb_recherches=nb_recherches,
        duree_s=duree, erreur=erreur,
    )
```

- [ ] **Step 4: Lancer et vérifier le succès**

Run: `.venv/Scripts/python.exe -m pytest python_src/tests/test_bench_metrics.py -q`
Attendu : tous les tests de la tâche passent.

- [ ] **Step 5: Prouver que le test de ligne mord**

Remplacer temporairement, dans `measure_puzzle`, `if idx_choisi != idx_ply:` par `if False:`.
Run: `.venv/Scripts/python.exe -m pytest python_src/tests/test_bench_metrics.py -q`
Attendu : `test_measure_puzzle_s_arrete_au_premier_ecart_de_la_ligne` échoue. Rétablir ensuite.

- [ ] **Step 6: Commit**

```bash
git add python_src/bench_metrics.py python_src/tests/test_bench_metrics.py
git commit -m "Mesure un puzzle : colonne reseau seul et colonne recherche"
```

---

### Task 4: Agrégation, Wilson et McNemar

**Files:**
- Modify: `python_src/bench_metrics.py`
- Modify: `python_src/tests/test_bench_metrics.py`

**Interfaces:**
- Consomme : `PuzzleMeasure` de la tâche 3.
- Produit :
  - `wilson(succes: int, total: int, z: float = 1.96) -> tuple[float, float]`
  - `mcnemar(b: int, c: int) -> tuple[float, float]` renvoyant `(chi2, p_value)`
  - `Taux` (dataclass gelée : `total`, `reseau`, `recherche`, `ligne`, `p_correct_median`, `part_visites_median`)
  - `BenchStats` (dataclass gelée : `global_: Taux`, `par_tranche: dict[str, Taux]`, `par_theme: dict[str, Taux]`, `mcnemar_b: int`, `mcnemar_c: int`, `mcnemar_chi2: float`, `mcnemar_p: float`, `erreurs: dict[str, int]`, `au_dela_128: int`)
  - `aggregate(mesures: list[PuzzleMeasure]) -> BenchStats`
  - `TRANCHES = (("1000-1449", 1000, 1449), ("1450-1899", 1450, 1899), ("1900-2349", 1900, 2349), ("2350-2800", 2350, 2800))`

- [ ] **Step 1: Écrire les tests**

```python
from bench_metrics import BenchStats, Taux, aggregate, mcnemar, wilson


def test_wilson_encadre_la_proportion():
    bas, haut = wilson(50, 100)

    assert bas < 0.5 < haut
    assert 0.39 < bas < 0.41       # valeur connue pour 50/100 a 95 pour cent
    assert 0.59 < haut < 0.61


def test_wilson_ne_sort_jamais_de_zero_un():
    assert wilson(0, 10)[0] == 0.0
    assert wilson(10, 10)[1] == 1.0
    assert wilson(0, 0) == (0.0, 0.0)


def test_mcnemar_sur_une_table_connue():
    """b = 10, c = 40 : chi2 avec correction de continuite = 29 sur 50."""
    chi2, p = mcnemar(10, 40)

    assert chi2 == pytest.approx((abs(10 - 40) - 1) ** 2 / 50)
    assert p < 0.001


def test_mcnemar_sans_discordance_ne_signale_rien():
    assert mcnemar(0, 0) == (0.0, 1.0)
    chi2, p = mcnemar(20, 20)
    assert chi2 == 0.0
    assert p == pytest.approx(1.0)


def _mesure(ligne, rating, reseau, recherche, complete, p=0.5, part=0.5,
            themes="fork short", erreur="", nb_legaux=30):
    from bench_metrics import PuzzleMeasure
    return PuzzleMeasure(
        ligne=ligne, rating=rating, themes=themes,
        plies_historique=20, nb_coups_legaux=nb_legaux,
        coup_reseau="e2e4", reussi_reseau=reseau, p_correct_reseau=p,
        rang_correct_reseau=1, value_reseau=0.1,
        coup_recherche="e2e4", reussi_recherche=recherche,
        part_visites_correct=part, reussi_ligne=complete,
        premier_ecart=-1 if complete else 0, nb_recherches=1,
        duree_s=0.5, erreur=erreur,
    )


def test_aggregate_compte_les_taux_globaux():
    mesures = [
        _mesure(0, 1100, True, True, True),
        _mesure(1, 1500, False, True, False),
        _mesure(2, 2000, True, False, False),
        _mesure(3, 2400, False, False, False),
    ]

    stats = aggregate(mesures)

    assert stats.global_.total == 4
    assert stats.global_.reseau == 2
    assert stats.global_.recherche == 2
    assert stats.global_.ligne == 1


def test_aggregate_ventile_par_tranche_de_rating():
    mesures = [
        _mesure(0, 1100, True, True, True),
        _mesure(1, 1500, True, True, True),
        _mesure(2, 1500, False, False, False),
    ]

    stats = aggregate(mesures)

    assert stats.par_tranche["1000-1449"].total == 1
    assert stats.par_tranche["1450-1899"].total == 2
    assert stats.par_tranche["1450-1899"].reseau == 1
    assert stats.par_tranche["1900-2349"].total == 0


def test_aggregate_compte_un_puzzle_dans_chacun_de_ses_themes():
    mesures = [_mesure(0, 1500, True, True, True, themes="fork pin short")]

    stats = aggregate(mesures)

    assert stats.par_theme["fork"].total == 1
    assert stats.par_theme["pin"].total == 1
    # 'short' n'est pas un motif tactique et ne doit pas apparaitre.
    assert "short" not in stats.par_theme


def test_aggregate_remplit_les_cases_discordantes_de_mcnemar():
    mesures = [
        _mesure(0, 1500, True, False, False),   # reseau bon, recherche mauvaise
        _mesure(1, 1500, True, False, False),
        _mesure(2, 1500, False, True, False),   # inverse
        _mesure(3, 1500, True, True, True),     # concordant
    ]

    stats = aggregate(mesures)

    assert stats.mcnemar_b == 2
    assert stats.mcnemar_c == 1


def test_aggregate_exclut_les_erreurs_des_taux_et_les_compte_a_part():
    mesures = [
        _mesure(0, 1500, True, True, True),
        _mesure(1, 1500, False, False, False, erreur="solution_illegale"),
    ]

    stats = aggregate(mesures)

    assert stats.global_.total == 1
    assert stats.erreurs == {"solution_illegale": 1}


def test_aggregate_signale_les_positions_au_dela_de_la_limite_de_tt():
    mesures = [
        _mesure(0, 1500, True, True, True, nb_legaux=52),
        _mesure(1, 1500, True, True, True, nb_legaux=140),
    ]

    assert aggregate(mesures).au_dela_128 == 1
```

- [ ] **Step 2: Lancer et vérifier l'échec**

Run: `.venv/Scripts/python.exe -m pytest python_src/tests/test_bench_metrics.py -q`
Attendu : ÉCHEC à l'import, `cannot import name 'aggregate'`.

- [ ] **Step 3: Implémenter**

À ajouter à `python_src/bench_metrics.py` :

```python
import collections
import math
import statistics

# Reprises de build_puzzle_dataset.BENCH_BUCKETS, sous forme d'etiquettes.
TRANCHES = (
    ("1000-1449", 1000, 1449),
    ("1450-1899", 1450, 1899),
    ("1900-2349", 1900, 2349),
    ("2350-2800", 2350, 2800),
)


def wilson(succes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalle de Wilson, preferable a l'intervalle normal sur des taux
    proches de 0 ou de 1, ou sur de petites tranches."""
    if total == 0:
        return (0.0, 0.0)
    p = succes / total
    d = 1.0 + z * z / total
    centre = (p + z * z / (2 * total)) / d
    demi = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / d
    return (max(0.0, centre - demi), min(1.0, centre + demi))


def mcnemar(b: int, c: int) -> tuple[float, float]:
    """Test de McNemar avec correction de continuite, sur les deux cases
    discordantes d'une comparaison appariee.

    b : le reseau seul avait trouve, la recherche a perdu.
    c : le reseau seul avait manque, la recherche a trouve.

    La p-valeur bilaterale d'un chi2 a un degre de liberte vaut
    erfc(sqrt(chi2 / 2)), ce qui evite une dependance a scipy.
    """
    n = b + c
    if n == 0:
        return (0.0, 1.0)
    chi2 = max(0.0, abs(b - c) - 1.0) ** 2 / n
    return (chi2, math.erfc(math.sqrt(chi2 / 2.0)))


@dataclass(frozen=True)
class Taux:
    total: int
    reseau: int
    recherche: int
    ligne: int
    p_correct_median: float
    part_visites_median: float


@dataclass(frozen=True)
class BenchStats:
    global_: Taux
    par_tranche: dict
    par_theme: dict
    mcnemar_b: int
    mcnemar_c: int
    mcnemar_chi2: float
    mcnemar_p: float
    erreurs: dict
    au_dela_128: int


def _taux(mesures: list) -> Taux:
    if not mesures:
        return Taux(0, 0, 0, 0, 0.0, 0.0)
    return Taux(
        total=len(mesures),
        reseau=sum(1 for m in mesures if m.reussi_reseau),
        recherche=sum(1 for m in mesures if m.reussi_recherche),
        ligne=sum(1 for m in mesures if m.reussi_ligne),
        p_correct_median=statistics.median(m.p_correct_reseau for m in mesures),
        part_visites_median=statistics.median(
            m.part_visites_correct for m in mesures),
    )


def aggregate(mesures: list) -> BenchStats:
    """Les puzzles en erreur sont exclus des taux et comptes a part : les
    inclure ferait passer un defaut de donnees pour une faiblesse du modele."""
    from build_puzzle_dataset import TACTICAL_THEMES

    erreurs: collections.Counter = collections.Counter(
        m.erreur for m in mesures if m.erreur)
    valides = [m for m in mesures if not m.erreur]

    par_tranche = {}
    for etiquette, bas, haut in TRANCHES:
        par_tranche[etiquette] = _taux(
            [m for m in valides if bas <= m.rating <= haut])

    par_theme = {}
    for theme in sorted(TACTICAL_THEMES):
        lot = [m for m in valides if theme in m.themes.split()]
        if lot:
            par_theme[theme] = _taux(lot)

    b = sum(1 for m in valides if m.reussi_reseau and not m.reussi_recherche)
    c = sum(1 for m in valides if not m.reussi_reseau and m.reussi_recherche)
    chi2, p = mcnemar(b, c)

    return BenchStats(
        global_=_taux(valides),
        par_tranche=par_tranche,
        par_theme=par_theme,
        mcnemar_b=b, mcnemar_c=c, mcnemar_chi2=chi2, mcnemar_p=p,
        erreurs=dict(erreurs),
        au_dela_128=sum(1 for m in valides if m.nb_coups_legaux > 128),
    )
```

- [ ] **Step 4: Lancer et vérifier le succès**

Run: `.venv/Scripts/python.exe -m pytest python_src/tests/test_bench_metrics.py -q`
Attendu : tous les tests passent.

- [ ] **Step 5: Commit**

```bash
git add python_src/bench_metrics.py python_src/tests/test_bench_metrics.py
git commit -m "Agrege les mesures du banc, Wilson et McNemar"
```

---

### Task 5: Mise en forme du rapport

**Files:**
- Modify: `python_src/bench_metrics.py`
- Modify: `python_src/tests/test_bench_metrics.py`

**Interfaces:**
- Consomme : `BenchStats` et `wilson` de la tâche 4.
- Produit : `format_report(stats: BenchStats, contexte: dict) -> str`. Les clés attendues de `contexte` sont `modele`, `iteration`, `global_step`, `simulations`, `c_puct`, `fichier_banc`, `sans_historique`, `duree_totale_s`, `travailleurs`.

- [ ] **Step 1: Écrire les tests**

```python
from bench_metrics import format_report


def _stats_minimales():
    mesures = [
        _mesure(0, 1100, True, True, True, p=0.8, part=0.9),
        _mesure(1, 1500, False, True, False, p=0.1, part=0.6),
        _mesure(2, 2000, True, False, False, p=0.7, part=0.2),
    ]
    return aggregate(mesures)


CONTEXTE = {
    "modele": "iter316_dynamic.onnx",
    "iteration": 316,
    "global_step": 19415,
    "simulations": 800,
    "c_puct": 1.4,
    "fichier_banc": "data/puzzles_bench.txt",
    "sans_historique": False,
    "duree_totale_s": 3600.0,
    "travailleurs": 16,
}


def test_format_report_contient_le_contexte_et_les_taux():
    texte = format_report(_stats_minimales(), CONTEXTE)

    assert "iter316_dynamic.onnx" in texte
    assert "19415" in texte
    assert "800" in texte
    assert "McNemar" in texte
    assert "1000-1449" in texte


def test_format_report_ne_contient_pas_de_tiret_cadratin():
    """Regle de redaction du projet."""
    assert "—" not in format_report(_stats_minimales(), CONTEXTE)


def test_format_report_signale_les_erreurs_quand_il_y_en_a():
    mesures = [
        _mesure(0, 1500, True, True, True),
        _mesure(1, 1500, False, False, False, erreur="solution_illegale"),
    ]

    texte = format_report(aggregate(mesures), CONTEXTE)

    assert "solution_illegale" in texte


def test_format_report_reste_muet_sur_les_erreurs_quand_il_n_y_en_a_pas():
    texte = format_report(_stats_minimales(), CONTEXTE)

    assert "solution_illegale" not in texte
```

- [ ] **Step 2: Lancer et vérifier l'échec**

Run: `.venv/Scripts/python.exe -m pytest python_src/tests/test_bench_metrics.py -q`
Attendu : ÉCHEC, `cannot import name 'format_report'`.

- [ ] **Step 3: Implémenter**

```python
def _ligne_taux(etiquette: str, t: Taux) -> str:
    if t.total == 0:
        return f"| {etiquette} | 0 | | | | | |"
    br, hr = wilson(t.reseau, t.total)
    bs, hs = wilson(t.recherche, t.total)
    bl, hl = wilson(t.ligne, t.total)
    return (
        f"| {etiquette} | {t.total} "
        f"| {100.0 * t.reseau / t.total:.1f} ({100 * br:.1f} a {100 * hr:.1f}) "
        f"| {100.0 * t.recherche / t.total:.1f} ({100 * bs:.1f} a {100 * hs:.1f}) "
        f"| {100.0 * t.ligne / t.total:.1f} ({100 * bl:.1f} a {100 * hl:.1f}) "
        f"| {t.p_correct_median:.3f} | {t.part_visites_median:.3f} |"
    )


_EN_TETE_TABLE = (
    "| | n | Reseau seul % | Recherche % | Ligne complete % "
    "| p med. du bon coup | part de visites med. |\n"
    "|---|---|---|---|---|---|---|"
)


def format_report(stats: BenchStats, contexte: dict) -> str:
    """Rapport markdown. Les taux sont suivis de leur intervalle de Wilson a
    95 pour cent, sans quoi deux points d'ecart se liraient comme un ecart."""
    bras = "sans historique" if contexte["sans_historique"] else "avec historique"
    lignes = [
        "# Banc de puzzles : resultats",
        "",
        f"Modele : `{contexte['modele']}`, iteration {contexte['iteration']}, "
        f"global_step {contexte['global_step']}",
        f"Banc : `{contexte['fichier_banc']}`, bras {bras}",
        f"Recherche : {contexte['simulations']} simulations, "
        f"c_puct {contexte['c_puct']}, {contexte['travailleurs']} travailleurs",
        f"Duree : {contexte['duree_totale_s'] / 60.0:.1f} min",
        "",
        "## Global",
        "",
        _EN_TETE_TABLE,
        _ligne_taux("global", stats.global_),
        "",
        "## Par tranche de rating",
        "",
        _EN_TETE_TABLE,
    ]
    for etiquette, _, _ in TRANCHES:
        lignes.append(_ligne_taux(etiquette, stats.par_tranche[etiquette]))

    lignes += [
        "",
        "## Par theme tactique",
        "",
        "Un puzzle portant plusieurs themes compte dans chacun : la ventilation",
        "est multi-etiquettes et ne somme pas au total.",
        "",
        _EN_TETE_TABLE,
    ]
    for theme, t in sorted(stats.par_theme.items(),
                           key=lambda kv: -kv[1].total):
        lignes.append(_ligne_taux(theme, t))

    lignes += [
        "",
        "## Reseau seul contre recherche, comparaison appariee",
        "",
        "Les deux colonnes portent sur les memes puzzles, donc McNemar",
        "s'applique. La case qui compte est la premiere : si elle est grosse, la",
        "recherche detruit des tactiques que la policy voyait deja.",
        "",
        f"- Reseau bon, recherche mauvaise : **{stats.mcnemar_b}**",
        f"- Reseau mauvais, recherche bonne : **{stats.mcnemar_c}**",
        f"- McNemar : chi2 = {stats.mcnemar_chi2:.2f}, p = {stats.mcnemar_p:.2e}",
    ]

    if stats.erreurs:
        lignes += ["", "## Erreurs de donnees", ""]
        lignes += [f"- `{cause}` : {n}"
                   for cause, n in sorted(stats.erreurs.items())]
        lignes.append("")
        lignes.append(
            "Ces puzzles sont exclus des taux ci-dessus. Les compter dedans "
            "ferait passer un defaut de donnees pour une faiblesse du modele.")

    if stats.au_dela_128:
        lignes += [
            "",
            f"Attention : {stats.au_dela_128} positions depassent 128 coups "
            "legaux, or TT_MAX_MOVES tronque a 128 et les coups au dela ne "
            "peuvent jamais etre joues.",
        ]

    return "\n".join(lignes) + "\n"
```

- [ ] **Step 4: Lancer et vérifier le succès**

Run: `.venv/Scripts/python.exe -m pytest python_src/tests/test_bench_metrics.py -q`
Attendu : tous les tests passent.

- [ ] **Step 5: Commit**

```bash
git add python_src/bench_metrics.py python_src/tests/test_bench_metrics.py
git commit -m "Met en forme le rapport du banc"
```

---

### Task 6: Accès au modèle, et l'accord du softmax avec le C++

**Files:**
- Create: `python_src/puzzle_bench.py`
- Create: `python_src/tests/test_bench_engine.py`

**Interfaces:**
- Consomme : `bench_metrics.uci_to_index`, `bench_metrics.charger_position`, `bench_metrics.parse_bench_line`.
- Produit :
  - `resoudre_modele(chemin: Path, dossier_onnx: Path) -> tuple[Path, dict]` renvoyant le chemin ONNX et `{"iteration", "global_step"}`
  - `exporter_onnx(chemin_pt: Path, sortie: Path) -> dict`
  - `faire_policy_fn(session)` renvoyant un `policy_fn(board) -> (dict[int, float], float)`
  - `faire_search_fn(evaluateur, simulations: int, c_puct: float)` renvoyant un `search_fn(board) -> list[float]`
  - `TAILLE_TT = 8192`

`exporter_onnx` déduit l'architecture du checkpoint au lieu de la coder en dur, et passe `dynamo=False` : sous torch 2.13 l'exporteur par défaut réclame `onnxscript`, absent de l'environnement.

- [ ] **Step 1: Écrire le test d'accord du softmax**

```python
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
from bench_metrics import charger_position, parse_bench_line, uci_to_index

BANC = RACINE / "data" / "puzzles_bench.txt"
CHECKPOINT = RACINE / "python_src" / "checkpoints" / "2026_04_23_23h25_iter316_unsupervised.pt"

pytestmark = pytest.mark.skipif(
    not CHECKPOINT.exists() or not BANC.exists(),
    reason="checkpoint ou fichier de banc absent")


@pytest.fixture(scope="module")
def modele(tmp_path_factory):
    import puzzle_bench

    dossier = tmp_path_factory.mktemp("onnx")
    chemin, meta = puzzle_bench.resoudre_modele(CHECKPOINT, dossier)
    return chemin, meta


def test_export_recupere_les_metadonnees_du_checkpoint(modele):
    _, meta = modele

    assert meta["iteration"] == 316
    assert meta["global_step"] == 19415


def test_le_softmax_python_egale_le_prior_du_cpp(modele):
    """Le C++ applique un softmax sur les 4672 sorties puis renormalise sur les
    coups legaux, ce qui est identique a un softmax sur les seuls coups legaux.
    L'egalite est mathematique, on la verifie quand meme.
    """
    import onnxruntime as ort
    import puzzle_bench

    chemin, _ = modele
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    session = ort.InferenceSession(str(chemin), options,
                                   providers=["CPUExecutionProvider"])
    policy_fn = puzzle_bench.faire_policy_fn(session)

    with open(BANC, encoding="utf-8") as f:
        puzzle = parse_bench_line(0, next(f))
    board = charger_position(puzzle)

    probs, _ = policy_fn(board)

    # Cote C++ : step_analysis renseigne m_analysis_root, et
    # get_analysis_results expose le prior des enfants visites.
    evaluateur = chess_engine.ONNXEvaluator(str(chemin), False)
    mcts = chess_engine.MCTS(evaluateur, puzzle_bench.TAILLE_TT)
    mcts.step_analysis(board, 400, 1.4)
    stats = mcts.get_analysis_results()

    assert stats, "aucun coup visite, le test ne verifie rien"

    compares = 0
    for s in stats:
        assert s.move_idx in probs, f"index {s.move_idx} absent du softmax Python"
        assert s.prior == pytest.approx(probs[s.move_idx], rel=1e-4, abs=1e-6)
        compares += 1

    assert compares >= 5, f"seulement {compares} priors compares"


def test_la_somme_des_probabilites_vaut_un(modele):
    import onnxruntime as ort
    import puzzle_bench

    chemin, _ = modele
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    session = ort.InferenceSession(str(chemin), options,
                                   providers=["CPUExecutionProvider"])
    policy_fn = puzzle_bench.faire_policy_fn(session)

    with open(BANC, encoding="utf-8") as f:
        puzzle = parse_bench_line(0, next(f))
    board = charger_position(puzzle)

    probs, value = policy_fn(board)

    assert set(probs) == set(board.get_legal_move_indices())
    assert sum(probs.values()) == pytest.approx(1.0)
    assert -1.0 <= value <= 1.0


def test_la_recherche_renvoie_une_distribution_de_visites(modele):
    import puzzle_bench

    chemin, _ = modele
    evaluateur = chess_engine.ONNXEvaluator(str(chemin), False)
    search_fn = puzzle_bench.faire_search_fn(evaluateur, 64, 1.4)

    with open(BANC, encoding="utf-8") as f:
        puzzle = parse_bench_line(0, next(f))
    board = charger_position(puzzle)

    pi = search_fn(board)

    assert len(pi) == 4672
    assert sum(pi) == pytest.approx(1.0)
    legaux = set(board.get_legal_move_indices())
    assert all(pi[i] == 0.0 for i in range(4672) if i not in legaux)
```

- [ ] **Step 2: Lancer et vérifier l'échec**

Run: `.venv/Scripts/python.exe -m pytest python_src/tests/test_bench_engine.py -q`
Attendu : ÉCHEC, `ModuleNotFoundError: No module named 'puzzle_bench'`.

- [ ] **Step 3: Implémenter la partie modèle de `puzzle_bench.py`**

```python
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
# 800 positions distinctes.
TAILLE_TT = 8192


def exporter_onnx(chemin_pt: Path, sortie: Path) -> dict:
    """Exporte un checkpoint .pt en ONNX a axes dynamiques.

    torch n'est importe qu'ici, donc jamais dans un processus travailleur ou il
    couterait 475 Mio. L'architecture est deduite du checkpoint plutot que
    codee en dur.
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
    return {"iteration": checkpoint.get("iteration"),
            "global_step": checkpoint.get("global_step"),
            "num_res_blocks": num_res_blocks,
            "num_filters": num_filters}


def resoudre_modele(chemin: Path, dossier_onnx: Path) -> tuple[Path, dict]:
    """Accepte un .onnx tel quel, ou exporte un .pt s'il le faut."""
    chemin = Path(chemin)
    if chemin.suffix == ".onnx":
        return chemin, {"iteration": None, "global_step": None}

    sortie = Path(dossier_onnx) / f"{chemin.stem}.onnx"
    if sortie.exists():
        # Un export deja present est reutilise, mais on relit le checkpoint
        # pour le contexte du rapport.
        import torch
        checkpoint = torch.load(chemin, map_location="cpu", weights_only=True)
        return sortie, {"iteration": checkpoint.get("iteration"),
                        "global_step": checkpoint.get("global_step")}

    return sortie, exporter_onnx(chemin, sortie)


def faire_policy_fn(session):
    """Renvoie policy_fn(board) -> (probs sur les index legaux, value).

    Softmax masque sur les coups legaux. Le C++ fait un softmax sur les 4672
    sorties (onnx_evaluator.cpp:74-89) puis renormalise sur les coups legaux
    (mcts.cpp:184-198) : renormaliser un softmax global sur un sous-ensemble
    est identique a un softmax sur ce seul sous-ensemble.
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
        return {i: e / somme for i, e in exps.items()}, float(value.reshape(-1)[0])

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
```

- [ ] **Step 4: Lancer et vérifier le succès**

Run: `.venv/Scripts/python.exe -m pytest python_src/tests/test_bench_engine.py -q`
Attendu : 5 tests passent. Si le checkpoint est absent, ils se sautent.

- [ ] **Step 5: Prouver que le test d'accord mord**

Dans `faire_policy_fn`, remplacer temporairement `maxi = max(...)` par `maxi = 0.0` et diviser par `somme * 2` au lieu de `somme`.
Run: `.venv/Scripts/python.exe -m pytest python_src/tests/test_bench_engine.py -q`
Attendu : `test_le_softmax_python_egale_le_prior_du_cpp` et `test_la_somme_des_probabilites_vaut_un` échouent. Rétablir ensuite.

- [ ] **Step 6: Commit**

```bash
git add python_src/puzzle_bench.py python_src/tests/test_bench_engine.py
git commit -m "Accede au modele et verifie l'accord du softmax avec le C++"
```

---

### Task 7: Orchestration, pool de processus, CSV et CLI

**Files:**
- Modify: `python_src/puzzle_bench.py`
- Modify: `python_src/tests/test_bench_engine.py`

**Interfaces:**
- Consomme : tout ce que produisent les tâches 2 à 6.
- Produit : `CHAMPS_CSV: tuple[str, ...]`, `ecrire_csv(mesures, chemin)`, `initialiser_travailleur(onnx, simulations, c_puct, sans_historique)`, `traiter_lot(lignes) -> list[PuzzleMeasure]`, `main() -> int`.

Le pool utilise un état par processus rempli par l'initialiseur : une session onnxruntime et un `ONNXEvaluator`, tous deux créés une seule fois par travailleur.

- [ ] **Step 1: Écrire le test de bout en bout sur un petit échantillon**

À ajouter à `python_src/tests/test_bench_engine.py` :

```python
def test_main_de_bout_en_bout_sur_un_petit_echantillon(tmp_path, monkeypatch):
    """Execute main() sur 6 puzzles et 8 simulations : verifie l'assemblage,
    pas la qualite du modele."""
    import csv as csv_mod

    import puzzle_bench

    sortie_csv = tmp_path / "res.csv"
    sortie_rapport = tmp_path / "rapport.md"

    monkeypatch.setattr(sys, "argv", [
        "puzzle_bench.py",
        "--model", str(CHECKPOINT),
        "--banc", str(BANC),
        "--limite", "6",
        "--simulations", "8",
        "--travailleurs", "2",
        "--dossier-onnx", str(tmp_path / "onnx"),
        "--out-csv", str(sortie_csv),
        "--out-rapport", str(sortie_rapport),
    ])

    assert puzzle_bench.main() == 0

    with open(sortie_csv, encoding="utf-8", newline="") as f:
        lignes = list(csv_mod.DictReader(f))

    assert len(lignes) == 6
    assert list(lignes[0]) == list(puzzle_bench.CHAMPS_CSV)
    # Aucune erreur de donnees : c'est un second controle de la correction du
    # pipeline, independant des tests de build_puzzle_dataset.
    assert all(l["erreur"] == "" for l in lignes), [
        l["erreur"] for l in lignes if l["erreur"]]

    rapport = sortie_rapport.read_text(encoding="utf-8")
    assert "Banc de puzzles" in rapport
    assert "McNemar" in rapport


def test_main_refuse_un_fichier_de_banc_absent(tmp_path, monkeypatch):
    import puzzle_bench

    monkeypatch.setattr(sys, "argv", [
        "puzzle_bench.py",
        "--model", str(CHECKPOINT),
        "--banc", str(tmp_path / "absent.txt"),
        "--out-csv", str(tmp_path / "res.csv"),
        "--out-rapport", str(tmp_path / "rapport.md"),
    ])

    assert puzzle_bench.main() == 2
```

- [ ] **Step 2: Lancer et vérifier l'échec**

Run: `.venv/Scripts/python.exe -m pytest python_src/tests/test_bench_engine.py -q`
Attendu : ÉCHEC, `module 'puzzle_bench' has no attribute 'main'`.

- [ ] **Step 3: Implémenter**

À ajouter à `python_src/puzzle_bench.py` :

```python
import argparse
import csv
import dataclasses
import multiprocessing as mp
import time

from bench_metrics import (
    aggregate,
    format_report,
    measure_puzzle,
    parse_bench_line,
)

CHAMPS_CSV = (
    "ligne", "rating", "themes", "plies_historique", "nb_coups_legaux",
    "coup_reseau", "reussi_reseau", "p_correct_reseau", "rang_correct_reseau",
    "value_reseau", "coup_recherche", "reussi_recherche",
    "part_visites_correct", "reussi_ligne", "premier_ecart", "nb_recherches",
    "duree_s", "erreur",
)

# Etat par processus travailleur : la session et l'evaluateur ne sont crees
# qu'une fois, pas a chaque puzzle.
_ETAT: dict = {}


def initialiser_travailleur(onnx: str, simulations: int, c_puct: float,
                            sans_historique: bool) -> None:
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(onnx, options,
                                   providers=["CPUExecutionProvider"])

    _ETAT["policy_fn"] = faire_policy_fn(session)
    _ETAT["search_fn"] = faire_search_fn(
        chess_engine.ONNXEvaluator(onnx, False), simulations, c_puct)
    _ETAT["sans_historique"] = sans_historique


def traiter_lot(lot: list) -> list:
    """lot : liste de (index, ligne brute). Renvoie des PuzzleMeasure."""
    return [
        measure_puzzle(
            parse_bench_line(index, ligne),
            _ETAT["policy_fn"],
            _ETAT["search_fn"],
            sans_historique=_ETAT["sans_historique"],
        )
        for index, ligne in lot
    ]


def ecrire_csv(mesures: list, chemin: Path) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(CHAMPS_CSV))
        writer.writeheader()
        for mesure in sorted(mesures, key=lambda m: m.ligne):
            writer.writerow(dataclasses.asdict(mesure))


def _lots(lignes: list, taille: int) -> list:
    return [lignes[i:i + taille] for i in range(0, len(lignes), taille)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True,
                        help="checkpoint .pt ou modele .onnx")
    parser.add_argument("--banc", type=Path,
                        default=Path("../data/puzzles_bench.txt"))
    parser.add_argument("--dossier-onnx", type=Path,
                        default=Path("checkpoints_onnx"))
    parser.add_argument("--out-csv", type=Path, default=None)
    parser.add_argument("--out-rapport", type=Path, default=None)
    parser.add_argument("--simulations", type=int, default=800)
    parser.add_argument("--c-puct", type=float, default=1.4)
    parser.add_argument("--travailleurs", type=int, default=16)
    parser.add_argument("--limite", type=int, default=0,
                        help="ne traiter que les N premiers puzzles")
    parser.add_argument("--sans-historique", action="store_true",
                        help="presente les puzzles avec l'historique vide")
    args = parser.parse_args()

    if not args.banc.exists():
        print(f"fichier de banc introuvable : {args.banc}", file=sys.stderr)
        return 2

    onnx, meta = resoudre_modele(args.model, args.dossier_onnx)
    if not Path(onnx).exists():
        print(f"modele ONNX introuvable : {onnx}", file=sys.stderr)
        return 2

    with open(args.banc, encoding="utf-8") as f:
        lignes = [(i, ligne) for i, ligne in enumerate(f)]
    if args.limite:
        lignes = lignes[:args.limite]

    # Posee dans le parent pour etre heritee : sous Windows le pool utilise
    # spawn et reimporte le module avant d'executer l'initialiseur, donc la
    # poser dans l'initialiseur serait trop tard.
    os.environ["OMP_NUM_THREADS"] = "1"

    suffixe = " (sans historique)" if args.sans_historique else ""
    print(f"{len(lignes)} puzzles, {args.simulations} simulations, "
          f"{args.travailleurs} travailleurs{suffixe}")

    debut = time.perf_counter()
    lots = _lots(lignes, 16)
    mesures: list = []
    with mp.Pool(args.travailleurs, initializer=initialiser_travailleur,
                 initargs=(str(onnx), args.simulations, args.c_puct,
                           args.sans_historique)) as pool:
        for i, resultat in enumerate(pool.imap_unordered(traiter_lot, lots), 1):
            mesures.extend(resultat)
            if i % 10 == 0 or i == len(lots):
                fait = len(mesures)
                ecoule = time.perf_counter() - debut
                print(f"  {fait}/{len(lignes)} puzzles, {ecoule / 60.0:.1f} min, "
                      f"{fait / max(1e-9, ecoule):.1f} puzzles/s")
    duree = time.perf_counter() - debut

    stats = aggregate(mesures)
    contexte = {
        "modele": Path(onnx).name,
        "iteration": meta.get("iteration"),
        "global_step": meta.get("global_step"),
        "simulations": args.simulations,
        "c_puct": args.c_puct,
        "fichier_banc": str(args.banc),
        "sans_historique": args.sans_historique,
        "duree_totale_s": duree,
        "travailleurs": args.travailleurs,
    }

    out_csv = args.out_csv or Path(
        f"../data/bench_results/{Path(onnx).stem}.csv")
    out_rapport = args.out_rapport or Path(
        f"../docs/superpowers/specs/{time.strftime('%Y-%m-%d')}"
        f"-puzzle-bench-resultats.md")

    ecrire_csv(mesures, out_csv)
    out_rapport.parent.mkdir(parents=True, exist_ok=True)
    out_rapport.write_text(format_report(stats, contexte), encoding="utf-8")

    print(f"\nCSV     : {out_csv}")
    print(f"Rapport : {out_rapport}")
    print(f"Duree   : {duree / 60.0:.1f} min")
    if stats.erreurs:
        print(f"Erreurs de donnees : {stats.erreurs}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())
```

- [ ] **Step 4: Lancer et vérifier le succès**

Run: `.venv/Scripts/python.exe -m pytest python_src/tests -q`
Attendu : toute la suite passe, y compris les 35 tests préexistants.

- [ ] **Step 5: Commit**

```bash
git add python_src/puzzle_bench.py python_src/tests/test_bench_engine.py
git commit -m "Orchestre le banc : pool de processus, CSV et rapport"
```

---

### Task 8: Exécution réelle et rapport

**Files:**
- Create: `data/bench_results/2026_04_23_23h25_iter316_unsupervised.csv`
- Create: `docs/superpowers/specs/2026-08-14-puzzle-bench-resultats.md`

**Interfaces:**
- Consomme : `puzzle_bench.main` de la tâche 7.
- Produit : le CSV par puzzle et le rapport, tous deux commités.

- [ ] **Step 1: Contrôler le débit sur 200 puzzles**

```bash
cd python_src && ../.venv/Scripts/python.exe puzzle_bench.py \
  --model checkpoints/2026_04_23_23h25_iter316_unsupervised.pt \
  --limite 200 --simulations 800 --travailleurs 16 \
  --out-csv ../data/bench_results/_essai.csv \
  --out-rapport ../docs/superpowers/specs/_essai.md
```

Attendu : 200 puzzles, zéro erreur de données, un débit affiché. Extrapoler à 5 000 avant de lancer la campagne complète, et ne pas se contenter d'une estimation.

- [ ] **Step 2: Supprimer les fichiers d'essai**

```bash
rm data/bench_results/_essai.csv docs/superpowers/specs/_essai.md
```

- [ ] **Step 3: Lancer la campagne complète**

```bash
cd python_src && ../.venv/Scripts/python.exe puzzle_bench.py \
  --model checkpoints/2026_04_23_23h25_iter316_unsupervised.pt \
  --simulations 800 --travailleurs 16
```

Attendu : environ une heure, un CSV de 5 000 lignes et un rapport.

- [ ] **Step 4: Contrôler la cohérence du résultat**

Vérifier dans le rapport, avant de conclure quoi que ce soit :
- zéro erreur de données, sans quoi la correction du pipeline est incomplète ;
- le taux ligne complète est inférieur ou égal au taux premier coup, sur chaque ligne de chaque table, sinon il y a un bug de comptage ;
- le taux décroît quand le rating croît, sinon la ventilation par tranche est suspecte ;
- `au_dela_128` vaut zéro.

- [ ] **Step 5: Commit**

```bash
git add data/bench_results docs/superpowers/specs/2026-08-14-puzzle-bench-resultats.md
git commit -m "Ajoute les resultats du banc de puzzles pour iter316"
```

---

## Auto-revue

**Couverture de la spec.** Section 4 du design (deux modules) : tâches 1 à 7. Section 5 (procédure de mesure) : tâche 3, plus tâche 6 pour les deux accès réseau. Section 6 (schéma de données) : `CHAMPS_CSV` en tâche 7 et `PuzzleMeasure` en tâche 3, mêmes noms de champs. Section 7 (agrégation, Wilson, McNemar) : tâche 4. Section 8 (pièges) : `tt_size` et `add_dirichlet` en tâche 6, `OMP_NUM_THREADS` et `intra_op_num_threads` en tâche 7, `TT_MAX_MOVES` en tâche 4 et contrôlé en tâche 8, robustesse des données en tâche 3. Section 9 (tests) : tâches 2 à 6. Le drapeau `--sans-historique` est implémenté en tâche 7 et testé en tâche 3.

**Scan des placeholders.** Un fragment d'import invalide s'était glissé en tâche 3, étape 1, avec une consigne de remplacement : supprimé, seul le bloc correct subsiste. Aucun « TBD », aucun « gérer les cas limites », aucun renvoi du type « comme la tâche N » : le code est répété là où il est nécessaire.

**Cohérence des types.** `policy_fn` renvoie partout `(dict[int, float], float)` et `search_fn` une séquence de 4672 flottants, en tâches 3, 6 et 7. `Taux` porte les mêmes noms de champs en tâches 4 et 5. `CHAMPS_CSV` en tâche 7 reprend exactement les champs de `PuzzleMeasure` de la tâche 3, dans le même ordre, ce que le test de bout en bout vérifie.

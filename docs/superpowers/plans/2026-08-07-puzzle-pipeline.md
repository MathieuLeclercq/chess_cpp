# Pipeline de puzzles avec historique réel : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fournir aux positions de puzzles injectées dans le self-play l'historique réel de la partie Lichess dont elles sont issues, afin qu'elles deviennent structurellement indiscernables des positions de partie.

**Architecture:** Un module Python isolé pour la couche réseau et le cache disque, un second pour le filtrage, l'appariement de position et l'écriture des deux fichiers de sortie. Côté C++, le chargement lit le nouveau format délimité et rejoue les coups UCI pour peupler `m_boardHistory`.

**Tech Stack:** Python 3.13, `python-chess` pour le rejeu et la comparaison de positions, `requests` pour l'API Lichess, pytest pour les tests unitaires. C++17 côté moteur.

**Spec de référence:** `docs/superpowers/specs/2026-08-07-puzzle-pipeline-design.md`

## Global Constraints

- Les **119 plans** du tenseur restent inchangés. Aucune modification de `getAlphaZeroTensor` ni de `model.py`.
- Le mode amnésie est **conservé**, taux ramené de 5 % à **1 %**, et sa raison d'être doit être redocumentée dans le code (l'ancien commentaire devient faux).
- Format de fichier : `<fen_initiale>|<coups_uci>|<solution_uci>|<rating>|<themes>`, une ligne par puzzle, séparateur `|`. Pas de JSON, le C++ doit lire sans dépendance supplémentaire.
- Appariement de position : comparaison sur les **trois premiers champs** de la FEN (placement, trait, droits de roque). Les compteurs **et le champ prise en passant** sont exclus.
- **Ne jamais comparer les hash Zobrist** entre rejeu et `loadFEN` : `checkEnPassant()` positionne le drapeau sur toute poussée double alors que Lichess ne renseigne la case que si une capture est possible. Comparer les ensembles de coups légaux.
- Répartition train / banc par **hachage du `PuzzleId`**, jamais par tirage aléatoire.
- Plage entraînement : rating **1300 à 2600**, 100 000 puzzles. Plage banc : **1000 à 2800**, 5 000 puzzles en 4 tranches de 1250 (**1000-1449, 1450-1899, 1900-2349, 2350-2800**).
- Thèmes retenus, correspondance par **jeton exact** après découpage sur les espaces : `mateIn1 mateIn2 mateIn3 fork pin skewer discoveredAttack doubleCheck hangingPiece sacrifice deflection trappedPiece attraction interference xRayAttack capturingDefender`.
- API : `POST https://lichess.org/api/games/export/_ids`, corps texte brut, IDs séparés par des virgules, **300 IDs maximum par requête**, une requête à la fois, recul exponentiel sur 429.
- Messages de commit sans ligne `Co-Authored-By`.
- Aucun tiret cadratin dans le code, les commentaires ou la documentation.
- Commentaires et messages en français, comme le reste du projet.

## Commandes

```bash
uv sync                                  # installe aussi le groupe dev (pytest)
uv run pytest python_src/tests -v        # tests unitaires
uv run python python_src/build_puzzle_dataset.py --help
```

Build C++ (cmake non présent dans le PATH, celui de Visual Studio fonctionne) :

```bash
cmake --build build --config Release --target chess_engine
```

## Structure des fichiers

| Fichier | Responsabilité |
|---|---|
| `pyproject.toml` (modifié) | ajout du groupe de dépendances `dev` avec pytest |
| `python_src/lichess_games.py` (créé) | couche réseau : extraction d'IDs, lots de 300, cache disque, jeton, recul sur 429 |
| `python_src/build_puzzle_dataset.py` (créé) | filtrage CSV, appariement de position, répartition, écriture, rapport |
| `python_src/tests/test_lichess_games.py` (créé) | tests de la couche réseau, avec récupérateur injecté |
| `python_src/tests/test_build_puzzle_dataset.py` (créé) | tests du filtrage, du hachage et de l'appariement |
| `src/chessboard.hpp` / `.cpp` (modifiés) | ajout de `movePieceUCI` |
| `src/selfplay_manager.hpp` / `.cpp` (modifiés) | chargement du nouveau format, rejeu des coups, amnésie à 1 % |
| `data/puzzles_bench.txt` (créé par exécution) | jeu du banc, committé |

`extract_lichess_puzzle.py` n'est pas modifié : le nouveau pipeline le remplace. Il reste en place le temps de vérifier que le nouveau produit bien mieux, et sera supprimé dans un cycle ultérieur.

---

### Task 1 : Filtrage du CSV et répartition par hachage

**Files:**
- Create: `python_src/build_puzzle_dataset.py`
- Create: `python_src/tests/test_build_puzzle_dataset.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: rien des tâches précédentes
- Produces: `TACTICAL_THEMES: frozenset[str]`, `matches_themes(themes_field: str) -> bool`, `bucket_of(rating: int) -> int | None`, `split_of(puzzle_id: str) -> str` renvoyant `"bench"` ou `"train"`, `PuzzleRow` (dataclass : `puzzle_id, fen, moves, rating, themes, game_url`), `read_puzzle_csv(path) -> Iterator[PuzzleRow]`

- [ ] **Step 1 : Ajouter pytest à pyproject.toml**

Ajouter à la fin de `pyproject.toml` :

```toml
[dependency-groups]
dev = ["pytest>=8.0"]
```

- [ ] **Step 2 : Synchroniser et vérifier que pytest répond**

```bash
uv sync && uv run pytest --version
```

Attendu : une version de pytest affichée, 8.0 ou supérieure.

- [ ] **Step 3 : Écrire les tests avant le code**

Créer `python_src/tests/test_build_puzzle_dataset.py` :

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_puzzle_dataset import (
    BENCH_BUCKETS,
    bucket_of,
    matches_themes,
    split_of,
)


def test_theme_exact_token_not_substring():
    """Le bug de l'ancienne extraction : 'mate' matchait 'smotheredMate'."""
    assert matches_themes("mateIn1 short crushing")
    assert matches_themes("middlegame fork advantage")
    # smotheredMate n'est pas dans la liste retenue, et ne doit pas matcher
    # via une correspondance de sous-chaine avec un theme de la liste.
    assert not matches_themes("smotheredMate short crushing")
    assert not matches_themes("endgame advantage long")


def test_theme_requires_at_least_one_match():
    assert not matches_themes("")
    assert matches_themes("pin")


def test_bucket_boundaries_are_contiguous_and_inclusive():
    assert bucket_of(1000) == 0
    assert bucket_of(1449) == 0
    assert bucket_of(1450) == 1
    assert bucket_of(1899) == 1
    assert bucket_of(1900) == 2
    assert bucket_of(2349) == 2
    assert bucket_of(2350) == 3
    assert bucket_of(2800) == 3


def test_bucket_rejects_out_of_range():
    assert bucket_of(999) is None
    assert bucket_of(2801) is None


def test_buckets_cover_the_declared_range_without_overlap():
    seen = set()
    for rating in range(1000, 2801):
        b = bucket_of(rating)
        assert b is not None, rating
        seen.add(b)
    assert seen == set(range(len(BENCH_BUCKETS)))


def test_split_is_deterministic():
    assert split_of("abc12") == split_of("abc12")


def test_split_produces_both_sides_in_roughly_the_declared_ratio():
    ids = [f"p{i:05d}" for i in range(20000)]
    bench = sum(1 for i in ids if split_of(i) == "bench")
    # Cible 5 pour cent, tolerance large : on teste la mecanique, pas la
    # qualite statistique de sha256.
    assert 0.03 < bench / len(ids) < 0.07
```

- [ ] **Step 4 : Lancer les tests et vérifier qu'ils échouent**

```bash
uv run pytest python_src/tests/test_build_puzzle_dataset.py -v
```

Attendu : ÉCHEC à l'import, `ModuleNotFoundError: No module named 'build_puzzle_dataset'`.

- [ ] **Step 5 : Écrire le module**

Créer `python_src/build_puzzle_dataset.py` :

```python
"""
Construit les jeux de puzzles avec historique reel, depuis le CSV Lichess et
l'API d'export des parties.

Deux sorties disjointes :
  training_data/puzzles_train.txt  (gitignore)  rating 1300-2600
  data/puzzles_bench.txt           (committe)   rating 1000-2800, 4 tranches

Voir docs/superpowers/specs/2026-08-07-puzzle-pipeline-design.md
"""

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# Motifs tactiques uniquement. Sont exclus les libelles de phase, de longueur,
# d'issue et de provenance, qui ne decrivent pas un motif.
TACTICAL_THEMES = frozenset({
    "mateIn1", "mateIn2", "mateIn3",
    "fork", "pin", "skewer", "discoveredAttack", "doubleCheck",
    "hangingPiece", "sacrifice", "deflection", "trappedPiece",
    "attraction", "interference", "xRayAttack", "capturingDefender",
})

TRAIN_RATING_MIN = 1300
TRAIN_RATING_MAX = 2600

# Bornes incluses de chaque tranche du banc.
BENCH_BUCKETS = ((1000, 1449), (1450, 1899), (1900, 2349), (2350, 2800))

# Part des puzzles envoyes au banc. La repartition se fait par hachage du
# PuzzleId et non par tirage, pour rester identique si un CSV plus recent est
# telecharge : aucune contamination possible dans le temps.
BENCH_SHARE = 0.05


@dataclass(frozen=True)
class PuzzleRow:
    puzzle_id: str
    fen: str
    moves: list[str]
    rating: int
    themes: str
    game_url: str


def matches_themes(themes_field: str) -> bool:
    """Correspondance par jeton exact, pas par sous-chaine.

    L'ancienne extraction faisait `theme in themes_field`, ce qui aurait fait
    matcher 'mate' avec 'smotheredMate' des lors qu'on elargit la liste.
    """
    return bool(TACTICAL_THEMES.intersection(themes_field.split()))


def bucket_of(rating: int) -> int | None:
    """Indice de tranche du banc, ou None si hors plage."""
    for index, (low, high) in enumerate(BENCH_BUCKETS):
        if low <= rating <= high:
            return index
    return None


def split_of(puzzle_id: str) -> str:
    """'bench' ou 'train', deterministe et stable dans le temps."""
    digest = hashlib.sha256(puzzle_id.encode("utf-8")).digest()
    # 16 bits suffisent largement pour un seuil a 5 pour cent.
    value = (digest[0] << 8 | digest[1]) / 65536.0
    return "bench" if value < BENCH_SHARE else "train"


def read_puzzle_csv(path: Path) -> Iterator[PuzzleRow]:
    """Lit le CSV Lichess et ne renvoie que les lignes passant le filtre de themes.

    Le filtre de rating n'est pas applique ici : les deux sorties ont des plages
    differentes, donc c'est l'appelant qui tranche.
    """
    with open(path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            themes = row.get("Themes", "")
            if not matches_themes(themes):
                continue
            try:
                rating = int(row["Rating"])
            except (KeyError, ValueError):
                continue
            yield PuzzleRow(
                puzzle_id=row["PuzzleId"],
                fen=row["FEN"],
                moves=row["Moves"].split(),
                rating=rating,
                themes=themes,
                game_url=row.get("GameUrl", ""),
            )
```

- [ ] **Step 6 : Lancer les tests et vérifier qu'ils passent**

```bash
uv run pytest python_src/tests/test_build_puzzle_dataset.py -v
```

Attendu : 7 tests PASSED.

- [ ] **Step 7 : Commit**

```bash
git add pyproject.toml uv.lock python_src/build_puzzle_dataset.py python_src/tests/test_build_puzzle_dataset.py
git commit -F - <<'EOF'
Ajoute le filtrage CSV et la repartition par hachage des puzzles

Filtrage par jeton exact sur les themes. L'ancienne extraction faisait
`theme in themes_field`, une correspondance de sous-chaine. Ce n'est pas
un bug actif : aucun jeton retenu n'est sous-chaine d'un autre theme
Lichess, donc les deux methodes concordent sur les donnees reelles. La
fragilite est latente et un test synthetique la verrouille.

Repartition train / banc par hachage du PuzzleId, jamais par tirage :
la repartition reste identique si un CSV plus recent est telecharge,
donc aucune contamination possible dans le temps.

Ajoute pytest comme dependance de developpement.
EOF
```

---

### Task 2 : Couche de téléchargement avec cache et reprise

**Files:**
- Create: `python_src/lichess_games.py`
- Create: `python_src/tests/test_lichess_games.py`

**Interfaces:**
- Consumes: rien
- Produces: `MAX_IDS_PER_REQUEST = 300`, `game_id_from_url(url: str) -> str | None`, `ply_hint_from_url(url: str) -> int | None`, `batched(items: list, size: int) -> Iterator[list]`, `fetch_games(game_ids: list[str], cache_dir: Path, token: str | None = None, fetcher=None) -> None`, `cached_pgn(game_id: str, cache_dir: Path) -> str | None`

`fetcher` est injectable pour les tests : signature `fetcher(ids: list[str], token: str | None) -> str`, renvoyant les PGN concaténés. Par défaut, un appel réel à l'API.

- [ ] **Step 1 : Écrire les tests avant le code**

Créer `python_src/tests/test_lichess_games.py` :

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lichess_games as lg


def test_game_id_extraction():
    assert lg.game_id_from_url("https://lichess.org/787zsVup") == "787zsVup"
    assert lg.game_id_from_url("https://lichess.org/787zsVup/black#48") == "787zsVup"
    assert lg.game_id_from_url("https://lichess.org/787zsVup#48") == "787zsVup"
    assert lg.game_id_from_url("") is None


def test_ply_hint_extraction():
    assert lg.ply_hint_from_url("https://lichess.org/787zsVup/black#48") == 48
    assert lg.ply_hint_from_url("https://lichess.org/787zsVup") is None
    assert lg.ply_hint_from_url("https://lichess.org/787zsVup#notanumber") is None


def test_batched_respects_size_and_loses_nothing():
    items = list(range(701))
    batches = list(lg.batched(items, lg.MAX_IDS_PER_REQUEST))
    assert [len(b) for b in batches] == [300, 300, 101]
    assert [x for b in batches for x in b] == items


def _fake_pgn(game_id: str) -> str:
    return (
        f'[Event "Test"]\n'
        f'[Site "https://lichess.org/{game_id}"]\n'
        f'[Result "1-0"]\n'
        f"\n"
        f"1. e4 e5 2. Nf3 1-0\n\n"
    )


def test_fetch_writes_one_file_per_game(tmp_path):
    calls = []

    def fetcher(ids, token):
        calls.append(list(ids))
        return "".join(_fake_pgn(i) for i in ids)

    lg.fetch_games(["aaa", "bbb"], tmp_path, fetcher=fetcher)

    assert calls == [["aaa", "bbb"]]
    assert lg.cached_pgn("aaa", tmp_path) is not None
    assert "https://lichess.org/bbb" in lg.cached_pgn("bbb", tmp_path)


def test_fetch_skips_what_is_already_cached(tmp_path):
    calls = []

    def fetcher(ids, token):
        calls.append(list(ids))
        return "".join(_fake_pgn(i) for i in ids)

    lg.fetch_games(["aaa"], tmp_path, fetcher=fetcher)
    lg.fetch_games(["aaa", "bbb"], tmp_path, fetcher=fetcher)

    # Le second appel ne redemande que ce qui manque.
    assert calls == [["aaa"], ["bbb"]]


def test_fetch_with_everything_cached_makes_no_call(tmp_path):
    def fetcher(ids, token):
        return "".join(_fake_pgn(i) for i in ids)

    lg.fetch_games(["aaa"], tmp_path, fetcher=fetcher)

    def exploding_fetcher(ids, token):
        raise AssertionError("aucun appel ne devait etre fait")

    lg.fetch_games(["aaa"], tmp_path, fetcher=exploding_fetcher)


def test_missing_game_in_response_is_not_cached(tmp_path):
    """Une partie supprimee ou privee n'apparait pas dans la reponse."""
    def fetcher(ids, token):
        return _fake_pgn("aaa")  # 'bbb' manque

    lg.fetch_games(["aaa", "bbb"], tmp_path, fetcher=fetcher)

    assert lg.cached_pgn("aaa", tmp_path) is not None
    assert lg.cached_pgn("bbb", tmp_path) is None
```

- [ ] **Step 2 : Lancer les tests et vérifier qu'ils échouent**

```bash
uv run pytest python_src/tests/test_lichess_games.py -v
```

Attendu : ÉCHEC à l'import, `ModuleNotFoundError: No module named 'lichess_games'`.

- [ ] **Step 3 : Écrire le module**

Créer `python_src/lichess_games.py` :

```python
"""
Couche de recuperation des parties Lichess par lots, avec cache disque.

Isolee du reste du pipeline pour deux raisons : les preoccupations reseau
(limites de debit, reprise, jeton) ne concernent personne d'autre, et le
recuperateur est injectable, ce qui rend le module testable sans reseau.
"""

import io
import re
import time
from pathlib import Path
from typing import Callable, Iterator

import chess.pgn
import requests

EXPORT_URL = "https://lichess.org/api/games/export/_ids"

# Verifie le 2026-08-07 contre la specification OpenAPI de Lichess :
# "300 IDs can be submitted."
MAX_IDS_PER_REQUEST = 300

# Lichess demande de ne faire qu'une requete a la fois.
PAUSE_BETWEEN_REQUESTS_S = 1.0
MAX_RETRIES = 5

_ID_RE = re.compile(r"lichess\.org/([A-Za-z0-9]{8})")
_PLY_RE = re.compile(r"#(\d+)\s*$")


def game_id_from_url(url: str) -> str | None:
    """Extrait l'identifiant de partie a 8 caracteres d'une GameUrl."""
    match = _ID_RE.search(url or "")
    return match.group(1) if match else None


def ply_hint_from_url(url: str) -> int | None:
    """Numero de ply de l'ancre, s'il y en a une. Sert uniquement a lever une
    ambiguite d'appariement, jamais a determiner la position directement."""
    match = _PLY_RE.search(url or "")
    return int(match.group(1)) if match else None


def batched(items: list, size: int) -> Iterator[list]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _cache_path(game_id: str, cache_dir: Path) -> Path:
    return cache_dir / f"{game_id}.pgn"


def cached_pgn(game_id: str, cache_dir: Path) -> str | None:
    path = _cache_path(game_id, cache_dir)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _http_fetcher(ids: list[str], token: str | None) -> str:
    headers = {"Accept": "application/x-chess-pgn"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for attempt in range(MAX_RETRIES):
        response = requests.post(
            EXPORT_URL, data=",".join(ids), headers=headers, timeout=120)
        if response.status_code == 429:
            wait = 60 * (attempt + 1)
            print(f"  429 recu, attente de {wait} s", flush=True)
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response.text
    raise RuntimeError("limite de debit non levee apres plusieurs tentatives")


def _split_pgn_by_game_id(all_pgn: str) -> dict[str, str]:
    """Decoupe une reponse multi-parties et indexe par identifiant.

    L'en-tete Site porte l'URL de la partie, donc son identifiant. On ne se fie
    pas a l'ordre de la reponse.
    """
    result: dict[str, str] = {}
    stream = io.StringIO(all_pgn)
    while True:
        game = chess.pgn.read_game(stream)
        if game is None:
            break
        game_id = game_id_from_url(game.headers.get("Site", ""))
        if game_id:
            result[game_id] = str(game)
    return result


def fetch_games(game_ids: list[str],
                cache_dir: Path,
                token: str | None = None,
                fetcher: Callable[[list[str], str | None], str] | None = None) -> None:
    """Remplit le cache disque pour les identifiants demandes.

    Ne retelecharge jamais ce qui est deja en cache, donc une relance apres
    interruption ne coute que ce qui manque. Les parties absentes de la reponse
    (supprimees, privees) ne sont pas mises en cache et seront simplement
    manquantes a l'etape d'appariement.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    fetcher = fetcher or _http_fetcher

    missing = [gid for gid in game_ids if not _cache_path(gid, cache_dir).exists()]
    if not missing:
        return

    total_batches = (len(missing) + MAX_IDS_PER_REQUEST - 1) // MAX_IDS_PER_REQUEST
    for index, batch in enumerate(batched(missing, MAX_IDS_PER_REQUEST), start=1):
        print(f"  lot {index}/{total_batches} ({len(batch)} parties)", flush=True)
        for game_id, pgn in _split_pgn_by_game_id(fetcher(batch, token)).items():
            _cache_path(game_id, cache_dir).write_text(pgn, encoding="utf-8")
        if index < total_batches:
            time.sleep(PAUSE_BETWEEN_REQUESTS_S)
```

- [ ] **Step 4 : Lancer les tests et vérifier qu'ils passent**

```bash
uv run pytest python_src/tests/test_lichess_games.py -v
```

Attendu : 7 tests PASSED.

- [ ] **Step 5 : Commit**

```bash
git add python_src/lichess_games.py python_src/tests/test_lichess_games.py
git commit -F - <<'EOF'
Ajoute la couche de recuperation des parties Lichess

Lots de 300 identifiants, cache disque par GameId, jeton optionnel,
recul sur 429. Une relance apres interruption ne retelecharge que ce
qui manque.

Le decoupage des reponses multi-parties se fait par l'en-tete Site et
non par l'ordre de la reponse. Les parties absentes (supprimees,
privees) ne sont pas mises en cache et seront simplement manquantes a
l'appariement.

Le recuperateur est injectable, donc le module est testable sans
reseau.
EOF
```

---

### Task 3 : Appariement de position par rejeu

**Files:**
- Modify: `python_src/build_puzzle_dataset.py`
- Modify: `python_src/tests/test_build_puzzle_dataset.py`

**Interfaces:**
- Consumes: `PuzzleRow` de la Task 1, `ply_hint_from_url` de la Task 2
- Produces: `position_key(board) -> str` (trois premiers champs de la FEN), `MatchResult` (dataclass : `start_fen: str`, `moves_uci: list[str]`), `MatchError` (classe de constantes : `NO_MATCH = "no_match"`, `AMBIGUOUS = "ambiguous"`, `GAME_MISSING = "game_missing"`, `UNREADABLE = "unreadable"`), `match_puzzle_in_game(pgn_text: str, puzzle_fen: str, ply_hint: int | None) -> MatchResult | str`

La fonction renvoie un `MatchResult` en cas de succès, ou l'une des chaînes de `MatchError` en cas d'échec.

- [ ] **Step 1 : Écrire les tests avant le code**

Ajouter à la fin de `python_src/tests/test_build_puzzle_dataset.py` :

```python
import chess
import chess.pgn

from build_puzzle_dataset import (
    MatchError,
    MatchResult,
    match_puzzle_in_game,
    position_key,
)


def _pgn_from_uci(uci_moves: list[str]) -> str:
    """Fabrique un PGN a partir d'une liste de coups UCI."""
    game = chess.pgn.Game()
    node = game
    board = chess.Board()
    for uci in uci_moves:
        move = chess.Move.from_uci(uci)
        node = node.add_variation(move)
        board.push(move)
    game.headers["Site"] = "https://lichess.org/testtest"
    return str(game)


def _fen_after(uci_moves: list[str]) -> str:
    board = chess.Board()
    for uci in uci_moves:
        board.push(chess.Move.from_uci(uci))
    return board.fen()


def test_position_key_keeps_three_fields_only():
    board = chess.Board()
    assert position_key(board) == (
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq")


def test_match_finds_the_right_ply_and_returns_the_moves():
    line = ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"]
    result = match_puzzle_in_game(
        _pgn_from_uci(line), _fen_after(line), ply_hint=None)

    assert isinstance(result, MatchResult)
    assert result.moves_uci == line
    assert result.start_fen == chess.STARTING_FEN


def test_match_finds_a_position_in_the_middle_of_the_game():
    line = ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6"]
    target = _fen_after(line[:3])

    result = match_puzzle_in_game(_pgn_from_uci(line), target, ply_hint=None)

    assert result.moves_uci == line[:3]


def test_match_ignores_en_passant_and_counter_fields():
    """Une divergence de convention sur la case en passant ne doit pas rejeter."""
    line = ["e2e4"]
    target = _fen_after(line)
    fields = target.split()
    # Lichess ne renseigne la case que si une capture est possible ; on simule
    # la convention inverse, plus les compteurs differents.
    forged = f"{fields[0]} {fields[1]} {fields[2]} - 7 42"

    result = match_puzzle_in_game(_pgn_from_uci(line), forged, ply_hint=None)

    assert result.moves_uci == line


def test_no_match_is_reported():
    line = ["e2e4", "e7e5"]
    unreachable = _fen_after(["d2d4", "d7d5", "c2c4"])

    result = match_puzzle_in_game(
        _pgn_from_uci(line), unreachable, ply_hint=None)

    assert result == MatchError.NO_MATCH


def test_repetition_without_hint_is_rejected_as_ambiguous():
    # Nf3 Nf6 Ng1 Ng8 ramene a la position de depart : deux plies partagent
    # placement, trait et droits de roque.
    line = ["g1f3", "g8f6", "f3g1", "f6g8"]
    target = chess.STARTING_FEN

    result = match_puzzle_in_game(_pgn_from_uci(line), target, ply_hint=None)

    assert result == MatchError.AMBIGUOUS


def test_repetition_with_hint_picks_the_closest_ply():
    line = ["g1f3", "g8f6", "f3g1", "f6g8"]
    target = chess.STARTING_FEN

    result = match_puzzle_in_game(_pgn_from_uci(line), target, ply_hint=4)

    assert result.moves_uci == line
```

- [ ] **Step 2 : Lancer les tests et vérifier qu'ils échouent**

```bash
uv run pytest python_src/tests/test_build_puzzle_dataset.py -v
```

Attendu : ÉCHEC à l'import, `ImportError: cannot import name 'MatchError'`.

- [ ] **Step 3 : Écrire le code d'appariement**

Ajouter à `python_src/build_puzzle_dataset.py`, après `read_puzzle_csv`, et compléter les imports en tête du fichier avec `import io`, `import chess`, `import chess.pgn` :

```python
class MatchError:
    """Causes d'echec d'appariement, comptabilisees dans le rapport."""
    NO_MATCH = "no_match"
    AMBIGUOUS = "ambiguous"
    GAME_MISSING = "game_missing"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class MatchResult:
    start_fen: str
    moves_uci: list[str]


def position_key(board: "chess.Board") -> str:
    """Trois premiers champs de la FEN : placement, trait, droits de roque.

    Sont exclus les compteurs, dont les conventions peuvent differer entre le
    CSV et le PGN reconstitue, ET la case en passant, pour la meme raison :
    Lichess ne la renseigne que si une capture est possible, python-chess a sa
    propre regle, et une divergence provoquerait un rejet a tort sur exactement
    les positions les plus interessantes.
    """
    return " ".join(board.fen().split()[:3])


def match_puzzle_in_game(pgn_text: str,
                         puzzle_fen: str,
                         ply_hint: int | None):
    """Rejoue la partie et localise le ply atteignant la position du puzzle.

    On ne se fie pas au numero de ply de la GameUrl : il ne sert qu'a lever une
    ambiguite. Le rejeu transforme une hypothese sur le format des donnees en
    verification effective.

    Renvoie un MatchResult, ou une constante de MatchError.
    """
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return MatchError.UNREADABLE

    try:
        board = game.board()
    except ValueError:
        return MatchError.UNREADABLE

    start_fen = board.fen()
    target = " ".join(puzzle_fen.split()[:3])

    moves: list[str] = []
    candidates: list[list[str]] = []

    if position_key(board) == target:
        candidates.append([])

    for move in game.mainline_moves():
        board.push(move)
        moves.append(move.uci())
        if position_key(board) == target:
            candidates.append(list(moves))

    if not candidates:
        return MatchError.NO_MATCH

    if len(candidates) == 1:
        return MatchResult(start_fen=start_fen, moves_uci=candidates[0])

    if ply_hint is None:
        return MatchError.AMBIGUOUS

    best = min(candidates, key=lambda c: abs(len(c) - ply_hint))
    return MatchResult(start_fen=start_fen, moves_uci=best)
```

- [ ] **Step 4 : Lancer les tests et vérifier qu'ils passent**

```bash
uv run pytest python_src/tests/test_build_puzzle_dataset.py -v
```

Attendu : 14 tests PASSED.

- [ ] **Step 5 : Commit**

```bash
git add python_src/build_puzzle_dataset.py python_src/tests/test_build_puzzle_dataset.py
git commit -F - <<'EOF'
Ajoute l'appariement de position par rejeu de la partie

On rejoue les coups et on compare a la FEN du puzzle a chaque ply,
plutot que de se fier au numero de ply de la GameUrl, qui ne sert plus
qu'a lever une ambiguite. Le procede transforme une hypothese sur le
format des donnees en verification effective.

Comparaison sur les trois premiers champs de la FEN uniquement. Les
compteurs sont exclus, et la case en passant aussi : Lichess ne la
renseigne que si une capture est possible, python-chess a sa propre
regle, et une divergence de convention provoquerait un rejet a tort sur
exactement les positions les plus interessantes.

Les repetitions produisent plusieurs plies candidats. Sans ancre de ply
dans l'URL, le puzzle est ecarte comme ambigu plutot que devine.
EOF
```

---

### Task 4 : Assemblage, écriture des fichiers et rapport

**Files:**
- Modify: `python_src/build_puzzle_dataset.py`
- Modify: `python_src/tests/test_build_puzzle_dataset.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: tout ce qui précède
- Produces: `format_line(row: PuzzleRow, match: MatchResult) -> str`, `main()` avec les options `--csv`, `--cache`, `--out-train`, `--out-bench`, `--train-target`, `--bench-per-bucket`, `--token`, `--dry-run`

- [ ] **Step 1 : Écrire le test du formatage de ligne**

Ajouter à `python_src/tests/test_build_puzzle_dataset.py` :

```python
from build_puzzle_dataset import PuzzleRow, format_line


def test_format_line_has_five_fields_and_no_separator_inside():
    row = PuzzleRow(
        puzzle_id="abc12",
        fen="8/8/8/8/8/8/8/K6k w - - 0 1",
        moves=["e2e4", "e7e5", "g1f3"],
        rating=1500,
        themes="mateIn2 short",
        game_url="https://lichess.org/testtest#4",
    )
    match = MatchResult(start_fen=chess.STARTING_FEN, moves_uci=["e2e4", "e7e5"])

    line = format_line(row, match)
    fields = line.split("|")

    assert len(fields) == 5
    assert fields[0] == chess.STARTING_FEN
    assert fields[1] == "e2e4 e7e5"
    # Le premier coup de Moves est la gaffe adverse, deja incluse dans les
    # coups rejoues. La solution commence donc au deuxieme.
    assert fields[2] == "e7e5 g1f3"
    assert fields[3] == "1500"
    assert fields[4] == "mateIn2 short"
    assert "\n" not in line
```

- [ ] **Step 2 : Lancer le test et vérifier qu'il échoue**

```bash
uv run pytest python_src/tests/test_build_puzzle_dataset.py::test_format_line_has_five_fields_and_no_separator_inside -v
```

Attendu : ÉCHEC, `ImportError: cannot import name 'format_line'`.

- [ ] **Step 3 : Écrire le formatage et le programme principal**

Ajouter à `python_src/build_puzzle_dataset.py`, et compléter les imports avec `import argparse`, `import collections`, `import sys`, et `from lichess_games import fetch_games, game_id_from_url, ply_hint_from_url, cached_pgn` :

```python
def format_line(row: PuzzleRow, match: MatchResult) -> str:
    """Une ligne du fichier de sortie.

    Le premier coup du champ Moves du CSV est la gaffe de l'adversaire, deja
    incluse dans les coups rejoues. La solution commence donc au deuxieme.
    """
    return "|".join((
        match.start_fen,
        " ".join(match.moves_uci),
        " ".join(row.moves[1:]),
        str(row.rating),
        row.themes,
    ))


def _read_token(path: Path) -> str | None:
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        return token or None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path,
                        default=Path("../training_data/lichess_db_puzzle.csv"))
    parser.add_argument("--cache", type=Path,
                        default=Path("../training_data/lichess_games_cache"))
    parser.add_argument("--out-train", type=Path,
                        default=Path("../training_data/puzzles_train.txt"))
    parser.add_argument("--out-bench", type=Path,
                        default=Path("../data/puzzles_bench.txt"))
    parser.add_argument("--train-target", type=int, default=100_000)
    parser.add_argument("--bench-per-bucket", type=int, default=1250)
    parser.add_argument("--token", type=Path,
                        default=Path("../lichess_token.txt"))
    parser.add_argument("--dry-run", action="store_true",
                        help="filtre et rapporte sans rien telecharger")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"CSV introuvable : {args.csv}", file=sys.stderr)
        print("Telecharger depuis https://database.lichess.org/#puzzles",
              file=sys.stderr)
        return 2

    # --- 1. Selection ---
    train: list[PuzzleRow] = []
    bench: dict[int, list[PuzzleRow]] = collections.defaultdict(list)

    def bench_is_full() -> bool:
        return all(len(bench[i]) >= args.bench_per_bucket
                   for i in range(len(BENCH_BUCKETS)))

    print("Lecture et filtrage du CSV...")
    for row in read_puzzle_csv(args.csv):
        if not game_id_from_url(row.game_url):
            continue
        if split_of(row.puzzle_id) == "bench":
            index = bucket_of(row.rating)
            if index is not None and len(bench[index]) < args.bench_per_bucket:
                bench[index].append(row)
        elif len(train) < args.train_target:
            if TRAIN_RATING_MIN <= row.rating <= TRAIN_RATING_MAX:
                train.append(row)

        # Le CSV compte plusieurs millions de lignes : inutile de le lire en
        # entier quand les deux quotas sont atteints.
        if len(train) >= args.train_target and bench_is_full():
            break

    selected = train + [r for rows in bench.values() for r in rows]
    print(f"  {len(train)} pour l'entrainement, "
          f"{sum(len(v) for v in bench.values())} pour le banc")
    for index, (low, high) in enumerate(BENCH_BUCKETS):
        print(f"  tranche {low}-{high} : {len(bench[index])}")

    if args.dry_run:
        print("--dry-run : arret avant telechargement.")
        return 0

    # --- 2. Telechargement ---
    game_ids = list(dict.fromkeys(
        game_id_from_url(r.game_url) for r in selected))
    print(f"Recuperation de {len(game_ids)} parties distinctes "
          f"pour {len(selected)} puzzles...")
    fetch_games(game_ids, args.cache, token=_read_token(args.token))

    # --- 3. Appariement et ecriture ---
    counters: collections.Counter = collections.Counter()
    history_lengths: list[int] = []

    def emit(rows: list[PuzzleRow], out_path: Path) -> int:
        written = 0
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as handle:
            for row in rows:
                pgn = cached_pgn(game_id_from_url(row.game_url), args.cache)
                if pgn is None:
                    counters[MatchError.GAME_MISSING] += 1
                    continue
                result = match_puzzle_in_game(
                    pgn, row.fen, ply_hint_from_url(row.game_url))
                if isinstance(result, str):
                    counters[result] += 1
                    continue
                handle.write(format_line(row, result) + "\n")
                history_lengths.append(len(result.moves_uci))
                written += 1
        return written

    written_train = emit(train, args.out_train)
    written_bench = emit(
        [r for rows in bench.values() for r in rows], args.out_bench)

    # --- 4. Rapport ---
    total = len(selected)
    rejected = sum(counters.values())
    short = sum(1 for n in history_lengths if n < 8)

    print(f"\n{'=' * 34}\n      RAPPORT DU PIPELINE\n{'=' * 34}")
    print(f"  Puzzles selectionnes   : {total}")
    print(f"  Ecrits (entrainement)  : {written_train}")
    print(f"  Ecrits (banc)          : {written_bench}")
    print(f"  Ecartes                : {rejected} "
          f"({100.0 * rejected / max(1, total):.2f} %)")
    for cause, count in sorted(counters.items()):
        print(f"    {cause:<14} : {count}")
    if history_lengths:
        print(f"  Historique < 8 plies   : {short} "
              f"({100.0 * short / len(history_lengths):.2f} %)")
    print("=" * 34)

    if rejected > 0.05 * max(1, total):
        print("\nPLUS DE 5 POUR CENT D'ECARTES. L'hypothese sur le format des "
              "donnees est a revoir avant d'aller plus loin.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4 : Lancer toute la suite**

```bash
uv run pytest python_src/tests -v
```

Attendu : 15 tests PASSED.

- [ ] **Step 5 : Vérifier la disjonction train / banc sur les fichiers produits**

Ajouter à `python_src/tests/test_build_puzzle_dataset.py` :

```python
def test_train_and_bench_never_share_a_puzzle_id():
    """La disjonction est une exigence : un banc partageant des puzzles avec
    l'entrainement mesurerait la memorisation, pas la capacite tactique."""
    ids = [f"p{i:06d}" for i in range(50000)]
    train = {i for i in ids if split_of(i) == "train"}
    bench = {i for i in ids if split_of(i) == "bench"}

    assert train and bench
    assert train.isdisjoint(bench)
    assert len(train) + len(bench) == len(ids)
```

```bash
uv run pytest python_src/tests -v
```

Attendu : 16 tests PASSED.

- [ ] **Step 6 : Ignorer le cache de parties**

Ajouter à `.gitignore`, après la ligne `training_data/` :

```
python_src/tests/__pycache__
.pytest_cache/
```

Le cache de parties vit sous `training_data/`, déjà ignoré. Le fichier du banc va dans `data/`, qui n'est pas ignoré et doit être versionné.

- [ ] **Step 7 : Vérifier la CLI sans réseau**

```bash
cd python_src && uv run python build_puzzle_dataset.py --help
```

Attendu : l'aide s'affiche avec les options `--csv`, `--cache`, `--out-train`, `--out-bench`, `--train-target`, `--bench-per-bucket`, `--token`, `--dry-run`.

```bash
cd python_src && uv run python build_puzzle_dataset.py --csv /inexistant.csv
```

Attendu : message `CSV introuvable`, code de sortie 2.

- [ ] **Step 8 : Commit**

```bash
git add python_src/build_puzzle_dataset.py python_src/tests/test_build_puzzle_dataset.py .gitignore
git commit -F - <<'EOF'
Assemble le pipeline de puzzles et son rapport

Selection, telechargement, appariement, ecriture des deux fichiers
disjoints et rapport chiffre.

Le rapport donne le detail des causes de rejet et la proportion de
puzzles disposant de moins de 8 plies d'historique, qui sont les seuls a
rester partiellement hors distribution. Au-dela de 5 pour cent de
rejets, le programme sort en erreur : l'hypothese sur le format des
donnees serait a revoir avant d'aller plus loin.

L'option --dry-run permet de verifier le filtrage sans declencher aucun
telechargement.
EOF
```

---

### Task 5 : Chargement du nouveau format et rejeu côté C++

**Files:**
- Modify: `src/chessboard.hpp` (déclaration, après `movePieceSAN`)
- Modify: `src/chessboard.cpp` (implémentation, après `movePieceSAN`)
- Modify: `src/selfplay_manager.hpp` (membre `m_tactical_fens` et déclaration `load_tactical_fens`)
- Modify: `src/selfplay_manager.cpp` (constructeur, `reset_game`, `roll_next_move`, `load_tactical_fens`)

**Interfaces:**
- Consumes: le format `<fen_initiale>|<coups_uci>|...` produit par la Task 4
- Produces: `bool Chessboard::movePieceUCI(const std::string& uci)`, `struct TacticalPuzzle { std::string start_fen; std::vector<std::string> moves; }`

- [ ] **Step 1 : Déclarer `movePieceUCI`**

Dans `src/chessboard.hpp`, juste après la ligne `bool movePieceSAN(std::string san);` :

```cpp
        // Applique un coup en notation UCI ("e2e4", "a7a8q").
        // Renvoie false si la chaine est mal formee ou le coup illegal.
        bool movePieceUCI(const std::string& uci);
```

- [ ] **Step 2 : Implémenter `movePieceUCI`**

Dans `src/chessboard.cpp`, juste après la fin de `movePieceSAN` :

```cpp
bool Chessboard::movePieceUCI(const std::string& uci)
{
    if (uci.size() < 4 || uci.size() > 5) return false;

    const int orig_file = uci[0] - 'a';
    const int orig_rank = uci[1] - '1';
    const int dest_file = uci[2] - 'a';
    const int dest_rank = uci[3] - '1';

    if (orig_file < 0 || orig_file > 7 || orig_rank < 0 || orig_rank > 7 ||
        dest_file < 0 || dest_file > 7 || dest_rank < 0 || dest_rank > 7)
        return false;

    PieceType promotion = NONE;
    if (uci.size() == 5) {
        switch (std::tolower(static_cast<unsigned char>(uci[4]))) {
        case 'q': promotion = QUEEN;  break;
        case 'r': promotion = ROOK;   break;
        case 'b': promotion = BISHOP; break;
        case 'n': promotion = KNIGHT; break;
        default: return false;
        }
    }
    else if (m_board[orig_rank * 8 + orig_file].getPiece().getType() == PAWN
             && (dest_rank == 0 || dest_rank == 7)) {
        // Convention AlphaZero : promotion en dame par defaut.
        promotion = QUEEN;
    }

    return movePiece(orig_file, orig_rank, dest_file, dest_rank, promotion, false);
}
```

- [ ] **Step 3 : Remplacer le membre et le chargeur dans le manager**

Dans `src/selfplay_manager.hpp`, remplacer la ligne `std::vector<std::string> m_tactical_fens;` par :

```cpp
    struct TacticalPuzzle {
        std::string start_fen;
        std::vector<std::string> moves; // UCI, jusqu'a la position du puzzle incluse
    };
    std::vector<TacticalPuzzle> m_tactical_puzzles;
```

et renommer la déclaration `void load_tactical_fens(const std::string& filepath);` en :

```cpp
    void load_tactical_puzzles(const std::string& filepath);
```

- [ ] **Step 4 : Implémenter le chargeur**

Dans `src/selfplay_manager.cpp`, remplacer intégralement la fonction `SelfPlayManager::load_tactical_fens` par :

```cpp
void SelfPlayManager::load_tactical_puzzles(const std::string& filepath) {
    std::ifstream file(filepath);
    std::string line;
    int malformed = 0;

    // Format : <fen_initiale>|<coups_uci>|<solution>|<rating>|<themes>
    // Seuls les deux premiers champs nous concernent.
    while (std::getline(file, line)) {
        if (line.empty()) continue;

        const size_t first = line.find('|');
        if (first == std::string::npos) { malformed++; continue; }
        const size_t second = line.find('|', first + 1);

        TacticalPuzzle puzzle;
        puzzle.start_fen = line.substr(0, first);

        const std::string moves_field = (second == std::string::npos)
            ? line.substr(first + 1)
            : line.substr(first + 1, second - first - 1);

        std::istringstream iss(moves_field);
        std::string move;
        while (iss >> move) puzzle.moves.push_back(move);

        if (puzzle.start_fen.empty()) { malformed++; continue; }
        m_tactical_puzzles.push_back(std::move(puzzle));
    }

    std::cout << "Charge " << m_tactical_puzzles.size()
              << " puzzles tactiques avec historique." << std::endl;
    if (malformed > 0) {
        std::cout << "  " << malformed << " ligne(s) mal formee(s) ignoree(s)."
                  << std::endl;
    }
}
```

Ajouter `#include <sstream>` en tête de `src/selfplay_manager.cpp`.

- [ ] **Step 5 : Rejouer les coups dans `reset_game`**

Dans `src/selfplay_manager.cpp`, dans `reset_game`, remplacer le bloc allant du commentaire `// --- INJECTION DE FEN (20% du temps) ---` jusqu'à la fin du `else` qui appelle `setStartupPieces()`, par :

```cpp
    // --- INJECTION DE PUZZLE (20% du temps) ---
    if (!m_tactical_puzzles.empty() && dis(m_rng) < 0.2f) {
        std::uniform_int_distribution<size_t> idx_dis(0, m_tactical_puzzles.size() - 1);
        const TacticalPuzzle& puzzle = m_tactical_puzzles[idx_dis(m_rng)];

        m_boards[game_idx].loadFEN(puzzle.start_fen);

        // On rejoue les coups reels de la partie pour que m_boardHistory
        // contienne un historique authentique. Sans ca, la position serait
        // structurellement identifiable comme un puzzle par le reseau, et
        // l'apprentissage tactique ne se transfererait pas en partie.
        bool replay_ok = true;
        for (const std::string& move : puzzle.moves) {
            if (!m_boards[game_idx].movePieceUCI(move)) {
                replay_ok = false;
                break;
            }
        }

        if (replay_ok) {
            m_is_tactical[game_idx] = true;
        }
        else {
            // Rejeu impossible : on retombe sur une partie normale plutot que
            // de partir d'une position corrompue.
            m_boards[game_idx].clear();
            m_boards[game_idx].setStartupPieces();
            m_is_tactical[game_idx] = false;
        }
    }
    else {
        m_boards[game_idx].setStartupPieces();
        m_is_tactical[game_idx] = false;
    }
```

Et dans le constructeur, remplacer l'appel `load_tactical_fens("../training_data/tactics.txt");` par :

```cpp
    load_tactical_puzzles("../training_data/puzzles_train.txt");
```

- [ ] **Step 6 : Ramener l'amnésie à 1 % et redocumenter**

Dans `src/selfplay_manager.cpp`, dans `roll_next_move`, remplacer le bloc commençant par le commentaire `// equivalent dropout pour éviter le shortcut learning` et couvrant le `if`/`else` sur `setAmnesiaMode`, par :

```cpp
    // Augmentation de donnees : on retire parfois l'historique pour que le
    // reseau sache fonctionner sans lui.
    //
    // Ce n'est PLUS un correctif de confondant : depuis que les positions de
    // puzzles portent l'historique reel de leur partie d'origine, l'absence
    // d'historique ne correle plus avec la tacticite. Le motif restant est la
    // robustesse aux entrees sans historique, cas de la FEN collee a la main
    // dans une GUI.
    //
    // Taux non mesure. Le banc de puzzles pourra le valider en evaluant les
    // memes positions avec et sans historique.
    if (dis(m_rng) < 0.01f) {
        m_boards[game_idx].setAmnesiaMode(true);
    }
    else {
        m_boards[game_idx].setAmnesiaMode(false);
    }
```

Noter que la condition `!m_is_tactical[game_idx] &&` disparaît : l'amnésie n'a plus de raison d'épargner les positions tactiques, puisqu'elle n'est plus un correctif de confondant.

- [ ] **Step 7 : Construire**

```bash
cmake --build build --config Release --target chess_engine
```

Attendu : compilation sans erreur.

- [ ] **Step 8 : Vérifier `movePieceUCI` contre `python-chess`**

Créer `python_src/tests/test_move_piece_uci.py` :

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chess
import chess_engine


def _legal_set(board):
    result = set()
    for move in board.get_all_legal_moves():
        orig, dest = move.get_orig_square(), move.get_dest_square()
        promo = move.get_promotion()
        result.add((orig.get_file(), orig.get_rank(),
                    dest.get_file(), dest.get_rank(), promo))
    return result


def test_uci_replay_reaches_the_same_position_as_load_fen():
    """Le controle central de la tache : le rejeu doit atteindre exactement la
    position attendue, et non une position decalee d'un ply.

    On compare l'ensemble des coups legaux et les trois premiers champs de la
    FEN. On ne compare PAS les hash Zobrist : checkEnPassant positionne le
    drapeau sur toute poussee double, alors que python-chess ne renseigne la
    case que si une capture est possible.
    """
    line = ["e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4", "f3d4", "g8f6"]

    ref = chess.Board()
    for uci in line:
        ref.push(chess.Move.from_uci(uci))
    target_fen = ref.fen()

    replayed = chess_engine.Chessboard()
    replayed.set_startup_pieces()
    for uci in line:
        assert replayed.move_piece_uci(uci), uci

    direct = chess_engine.Chessboard()
    direct.load_fen(target_fen)

    assert _legal_set(replayed) == _legal_set(direct)
    assert replayed.to_fen().split()[:3] == direct.to_fen().split()[:3]


def test_uci_replay_handles_castling():
    line = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5", "e1g1"]  # petit roque

    replayed = chess_engine.Chessboard()
    replayed.set_startup_pieces()
    for uci in line:
        assert replayed.move_piece_uci(uci), uci

    ref = chess.Board()
    for uci in line:
        ref.push(chess.Move.from_uci(uci))

    assert replayed.to_fen().split()[:3] == ref.fen().split()[:3]


def test_uci_replay_handles_promotion_explicit_and_implicit():
    """Promotion explicite ('a7a8q') et implicite ('a7a8'), la seconde etant la
    convention AlphaZero de promotion en dame par defaut."""
    setup = "8/P7/8/8/8/8/7p/K6k w - - 0 1"

    explicit = chess_engine.Chessboard()
    explicit.load_fen(setup)
    assert explicit.move_piece_uci("a7a8q")

    implicit = chess_engine.Chessboard()
    implicit.load_fen(setup)
    assert implicit.move_piece_uci("a7a8")

    assert explicit.to_fen().split()[:3] == implicit.to_fen().split()[:3]

    ref = chess.Board(setup)
    ref.push(chess.Move.from_uci("a7a8q"))
    assert explicit.to_fen().split()[:3] == ref.fen().split()[:3]

    under = chess_engine.Chessboard()
    under.load_fen(setup)
    assert under.move_piece_uci("a7a8n")
    assert under.to_fen().split()[:3] != explicit.to_fen().split()[:3]


def test_uci_rejects_malformed_and_illegal():
    board = chess_engine.Chessboard()
    board.set_startup_pieces()

    assert not board.move_piece_uci("")
    assert not board.move_piece_uci("e2")
    assert not board.move_piece_uci("z9z9")
    assert not board.move_piece_uci("e2e4x")
    assert not board.move_piece_uci("e2e5")  # illegal
```

- [ ] **Step 9 : Exposer `move_piece_uci` dans les bindings et reconstruire**

Dans `src/bindings.cpp`, juste après `.def("move_piece_san", &Chessboard::movePieceSAN)` :

```cpp
        .def("move_piece_uci", &Chessboard::movePieceUCI)
```

```bash
cmake --build build --config Release --target chess_engine
uv run pytest python_src/tests/test_move_piece_uci.py -v
```

Attendu : 4 tests PASSED.

- [ ] **Step 10 : Prouver que le contrôle détecte un décalage de ply**

Un contrôle qui ne se déclenche jamais et un contrôle absent produisent la même sortie. Modifier temporairement le test pour retirer le dernier coup du rejeu :

```python
    for uci in line[:-1]:      # TEMPORAIRE : un ply de moins
        assert replayed.move_piece_uci(uci), uci
```

```bash
uv run pytest python_src/tests/test_move_piece_uci.py::test_uci_replay_reaches_the_same_position_as_load_fen -v
```

Attendu : ÉCHEC sur la comparaison des ensembles de coups légaux.

**Rétablir `for uci in line:`** et relancer pour confirmer le retour au vert.

- [ ] **Step 11 : Vérifier que le perft n'a pas régressé**

`movePieceUCI` appelle `movePiece`, et le manager a changé. Le générateur de coups ne devrait pas être affecté, mais c'est exactement ce que le filet sert à confirmer.

```bash
cmake --build build --config Release --target chess_perft
./build/Release/chess_perft.exe bench --strict --check-fen
```

Attendu : `Resultat : SUCCES`, code de sortie 0.

- [ ] **Step 12 : Commit**

```bash
git add src/chessboard.hpp src/chessboard.cpp src/selfplay_manager.hpp src/selfplay_manager.cpp src/bindings.cpp python_src/tests/test_move_piece_uci.py
git commit -F - <<'EOF'
Charge les puzzles avec historique et rejoue les coups cote C++

reset_game charge la position initiale de la partie puis rejoue les
coups reels jusqu'a la position du puzzle, pour que m_boardHistory
contienne un historique authentique. Sans ca, la position reste
structurellement identifiable comme un puzzle et l'apprentissage
tactique ne se transfere pas en partie.

Ajoute Chessboard::movePieceUCI, expose dans les bindings, avec la
convention AlphaZero de promotion en dame par defaut.

Ramene le mode amnesie de 5 a 1 pour cent et redocumente sa raison
d'etre : ce n'est plus un correctif de confondant mais de
l'augmentation de donnees pour la robustesse aux entrees sans
historique. La condition qui epargnait les positions tactiques
disparait, elle n'a plus d'objet.

Un rejeu impossible fait retomber sur une partie normale plutot que de
partir d'une position corrompue.

Verifie : le rejeu atteint la meme position qu'un loadFEN direct
(ensembles de coups legaux et trois premiers champs de la FEN, jamais
les hash Zobrist), le controle se declenche bien sur un decalage d'un
ply, et le perft ne regresse pas.
EOF
```

---

### Task 6 : Exécution réelle et rapport

**Files:**
- Create: `data/puzzles_bench.txt` (produit par l'exécution, committé)
- Create: `docs/superpowers/specs/2026-08-07-puzzle-pipeline-resultats.md`

**Interfaces:**
- Consumes: tout ce qui précède
- Produces: le rapport qui conditionne la suite

- [ ] **Step 1 : Vérifier le filtrage sans rien télécharger**

Le CSV doit être présent dans `training_data/`. S'il manque, le télécharger depuis <https://database.lichess.org/#puzzles>.

```bash
cd python_src && uv run python build_puzzle_dataset.py --dry-run
```

Attendu : les comptes par tranche, et 100 000 puzzles d'entraînement sélectionnés. Si une tranche du banc est sous 1250, la plage de rating correspondante manque de puzzles passant le filtre de thèmes : le noter et continuer.

- [ ] **Step 2 : Lancer le pipeline complet**

```bash
cd python_src && uv run python build_puzzle_dataset.py
```

Compter plusieurs minutes pour le téléchargement. En cas d'interruption, relancer : le cache évite tout retéléchargement.

Attendu : code de sortie 0, et un rapport avec moins de 5 % d'écartés.

Si le taux dépasse 5 %, **ne pas continuer** : le programme sort en erreur et l'hypothèse sur le format des données est à revoir. Regarder la répartition des causes, `no_match` et `ambiguous` en particulier.

- [ ] **Step 3 : Vérifier la disjonction sur les fichiers réels**

```bash
cd python_src && uv run python -c "
from pathlib import Path
import csv, sys
sys.path.insert(0, '.')
from build_puzzle_dataset import read_puzzle_csv, split_of
t = sum(1 for _ in open('../training_data/puzzles_train.txt', encoding='utf-8'))
b = sum(1 for _ in open('../data/puzzles_bench.txt', encoding='utf-8'))
print(f'train {t} lignes, bench {b} lignes')
"
```

Attendu : environ 100 000 et 5 000. La disjonction est garantie par construction (hachage), et déjà couverte par un test unitaire.

- [ ] **Step 4 : Vérifier qu'une partie entière tourne avec les nouveaux puzzles**

```bash
cd python_src && uv run python -c "
import sys; sys.path.insert(0, '.')
import chess_engine
lines = open('../training_data/puzzles_train.txt', encoding='utf-8').read().splitlines()
ok = 0
for line in lines[:200]:
    fen, moves = line.split('|')[0], line.split('|')[1].split()
    b = chess_engine.Chessboard()
    b.load_fen(fen)
    if all(b.move_piece_uci(m) for m in moves):
        ok += 1
print(f'{ok}/200 rejoues sans erreur')
"
```

Attendu : `200/200`. Tout écart signifie que le pipeline a écrit des coups que le moteur refuse, donc un désaccord entre `python-chess` et le générateur de coups, ce qui serait un résultat majeur à investiguer avec `dev_tools/fuzz_movegen.py --bisect`.

- [ ] **Step 5 : Rédiger le rapport**

Créer `docs/superpowers/specs/2026-08-07-puzzle-pipeline-resultats.md` en remplaçant chaque valeur entre chevrons par la mesure réelle :

```markdown
# Résultats du pipeline de puzzles

Date d'exécution : <date>
Commit : <git rev-parse --short HEAD>
Version du CSV puzzles : <date de téléchargement ou nombre de lignes>

## Sélection

| Ensemble | Lignes écrites |
|---|---|
| Entraînement (1300-2600) | <n> |
| Banc, tranche 1000-1449 | <n> |
| Banc, tranche 1450-1899 | <n> |
| Banc, tranche 1900-2349 | <n> |
| Banc, tranche 2350-2800 | <n> |

## Rejets

| Cause | Nombre | Part |
|---|---|---|
| `no_match` | <n> | <x> % |
| `ambiguous` | <n> | <x> % |
| `game_missing` | <n> | <x> % |
| `unreadable` | <n> | <x> % |
| **Total** | <n> | <x> % |

Seuil d'alerte : 5 %. <Atteint ou non.>

## Historique disponible

Proportion de puzzles disposant de moins de 8 plies d'historique : <x> %.

Ce sont les seuls à rester partiellement hors distribution. Ils viennent de
débuts de partie, donc de positions rarement tactiques.

## Contrôles

- Rejeu de 200 puzzles par le moteur C++ : <n>/200 sans erreur.
- Perft `bench --strict --check-fen` après modification : <SUCCES ou ECHEC>.
- Disjonction train / banc : garantie par hachage, couverte par test unitaire.

## Suite

<Le fine-tuning ou la reprise du self-play sur les données corrigées, puis le
cycle du banc de puzzles. Noter ici toute anomalie à traiter avant.>
```

- [ ] **Step 6 : Commit**

```bash
git add data/puzzles_bench.txt docs/superpowers/specs/2026-08-07-puzzle-pipeline-resultats.md
git commit -F - <<'EOF'
Ajoute le jeu de puzzles du banc et le rapport du pipeline

Jeu du banc committe : il devient un actif stable du depot, reutilisable
pour toutes les mesures futures, et sa disjonction avec l'ensemble
d'entrainement est garantie par hachage du PuzzleId.

Le rapport consigne les comptes par tranche, les causes de rejet, la
proportion de puzzles a moins de 8 plies d'historique, et les controles
de rejeu.
EOF
```

- [ ] **Step 7 : Faire le point**

Présenter le rapport. Deux suites possibles :

- **Tout est vert.** Les données sont corrigées. La suite est le cycle du banc de puzzles (brainstorming, spec, plan), puis le fine-tuning ou la reprise du self-play.
- **Anomalie.** Un taux de rejet élevé, un rejeu refusé par le moteur, ou une tranche du banc incomplète. Chacune fait l'objet d'un traitement séparé avant d'aller plus loin.

---

## Hors périmètre

Rappel de la spec, pour éviter tout glissement pendant l'exécution :

- Le banc de mesure lui-même, qui aura son propre cycle et consommera `data/puzzles_bench.txt`.
- Le fine-tuning ou la reprise du self-play sur les données corrigées.
- La réduction du nombre de plans du tenseur (`docs/backlog.md` §4, en réserve).
- La suppression de `extract_lichess_puzzle.py`, laissé en place le temps de vérifier que le nouveau pipeline produit bien mieux.
- La reconstruction de la position précédente pour les FEN nues collées dans une GUI.

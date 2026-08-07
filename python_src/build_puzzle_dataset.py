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

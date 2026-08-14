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

    Le fichier du banc ne contient pas le PuzzleId : l'index de ligne fait donc
    office d'identifiant, ce qui interdit de reordonner le fichier.
    """
    champs = ligne.rstrip("\n").split("|")
    if len(champs) != 5:
        raise ValueError(f"ligne {index} : {len(champs)} champs au lieu de 5")

    fen, coups, solution, rating, themes = champs
    return BenchPuzzle(
        ligne=index,
        fen_initiale=fen,
        coups_uci=coups.split(),
        solution_uci=solution.split(),
        rating=int(rating),
        themes=themes,
    )

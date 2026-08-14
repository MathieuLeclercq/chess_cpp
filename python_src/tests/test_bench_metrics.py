"""Tests du noyau de mesure du banc.

Aucun modele, aucun processus : les deux acces au reseau sont injectes, sur le
modele du fetcher de lichess_games.fetch_games. Le plateau, lui, est le vrai
Chessboard : il ne coute que 2 Mio a l'import et le simuler reviendrait a
tester une fiction.
"""
import os
import sys

import pytest

RACINE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, RACINE)
os.add_dll_directory(RACINE)

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


def test_parse_bench_line_reads_the_real_bench_file():
    """La lecture doit tenir sur les donnees reelles, pas seulement sur une
    ligne forgee."""
    chemin = os.path.join(RACINE, "..", "data", "puzzles_bench.txt")
    if not os.path.exists(chemin):
        pytest.skip("fichier de banc absent")

    with open(chemin, encoding="utf-8") as f:
        puzzles = [parse_bench_line(i, ligne)
                   for i, ligne in zip(range(20), f)]

    assert len(puzzles) == 20
    assert all(p.coups_uci for p in puzzles)
    assert all(p.solution_uci for p in puzzles)
    assert all(1000 <= p.rating <= 2800 for p in puzzles)
    assert [p.ligne for p in puzzles] == list(range(20))

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


import chess_engine
from bench_metrics import (
    DonneesInvalides,
    charger_position,
    measure_puzzle,
    uci_to_index,
)

DEPART = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _puzzle(coups, solution, fen=DEPART, rating=1500, themes="fork short"):
    return BenchPuzzle(
        ligne=0, fen_initiale=fen, coups_uci=coups, solution_uci=solution,
        rating=rating, themes=themes,
    )


def _faux_reseau(coup_prefere, p=0.7):
    """policy_fn factice : met p sur coup_prefere, repartit le reste."""
    def policy_fn(board):
        indices = board.get_legal_move_indices()
        cible = uci_to_index(board, coup_prefere)
        reste = (1.0 - p) / max(1, len(indices) - 1)
        return {i: (p if i == cible else reste) for i in indices}, 0.25
    return policy_fn


def _visites_sur(board, coup):
    pi = [0.0] * 4672
    pi[uci_to_index(board, coup)] = 1.0
    return pi


def _recherche_sequentielle(coups):
    """search_fn factice : renvoie les coups fournis, dans l'ordre des appels.

    Plus explicite que d'inspecter des cases du plateau pour deviner a quel
    coup de la ligne on se trouve.
    """
    restants = list(coups)

    def search_fn(board):
        return _visites_sur(board, restants.pop(0))
    return search_fn


def test_charger_position_rejoue_l_historique():
    puzzle = _puzzle(["e2e4", "e7e5", "g1f3"], ["b8c6"])

    board = charger_position(puzzle)

    assert board.turn == chess_engine.Color.BLACK
    # Le cavalier est arrive en f3, soit file 5 rang 2.
    assert board.get_square(5, 2).get_piece().get_type() == chess_engine.PieceType.KNIGHT


def test_charger_position_refuse_un_historique_illegal():
    puzzle = _puzzle(["e2e4", "e2e4"], ["b8c6"])

    with pytest.raises(DonneesInvalides) as info:
        charger_position(puzzle)

    assert info.value.cause == "historique_illegal"


def test_charger_position_sans_historique_donne_la_meme_position():
    """Le bras sans historique repart de la FEN atteinte, ce qui vide les plans
    d'historique du tenseur sans changer la position."""
    puzzle = _puzzle(["e2e4", "e7e5", "g1f3"], ["b8c6"])

    avec = charger_position(puzzle)
    sans = charger_position(puzzle, sans_historique=True)

    assert avec.to_fen() == sans.to_fen()
    assert avec.get_legal_move_indices() == sans.get_legal_move_indices()
    assert not (avec.get_alphazero_tensor() == sans.get_alphazero_tensor()).all()


def test_measure_puzzle_compte_une_reussite_au_premier_coup():
    puzzle = _puzzle(["e2e4", "e7e5", "g1f3"], ["b8c6"])

    mesure = measure_puzzle(puzzle, _faux_reseau("b8c6"),
                            _recherche_sequentielle(["b8c6"]))

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
    assert mesure.plies_historique == 3
    assert mesure.nb_coups_legaux > 0


def test_measure_puzzle_compte_un_echec_et_le_rang_du_bon_coup():
    puzzle = _puzzle(["e2e4", "e7e5", "g1f3"], ["b8c6"])

    mesure = measure_puzzle(puzzle, _faux_reseau("g8f6"),
                            _recherche_sequentielle(["g8f6"]))

    assert mesure.reussi_reseau is False
    assert mesure.reussi_recherche is False
    assert mesure.reussi_ligne is False
    assert mesure.premier_ecart == 0
    assert mesure.coup_recherche == "g8f6"
    assert mesure.rang_correct_reseau > 1
    assert mesure.part_visites_correct == pytest.approx(0.0)
    assert mesure.nb_recherches == 1


def test_measure_puzzle_suit_une_ligne_de_trois_coups():
    """Les coups du solveur sont aux index pairs : ici deux recherches."""
    puzzle = _puzzle(["e2e4", "e7e5", "g1f3", "b8c6"],
                     ["f1b5", "a7a6", "b5c6"])

    mesure = measure_puzzle(puzzle, _faux_reseau("f1b5"),
                            _recherche_sequentielle(["f1b5", "b5c6"]))

    assert mesure.erreur == ""
    assert mesure.reussi_recherche is True
    assert mesure.reussi_ligne is True
    assert mesure.premier_ecart == -1
    assert mesure.nb_recherches == 2


def test_measure_puzzle_s_arrete_au_premier_ecart_de_la_ligne():
    puzzle = _puzzle(["e2e4", "e7e5", "g1f3", "b8c6"],
                     ["f1b5", "a7a6", "b5c6"])

    # Premier coup bon, second coup solveur (index 2) faux.
    mesure = measure_puzzle(puzzle, _faux_reseau("f1b5"),
                            _recherche_sequentielle(["f1b5", "b5a4"]))

    assert mesure.reussi_recherche is True      # le premier coup reste bon
    assert mesure.reussi_ligne is False
    assert mesure.premier_ecart == 2
    assert mesure.nb_recherches == 2


def test_measure_puzzle_gere_une_solution_d_un_seul_coup():
    puzzle = _puzzle(["e2e4", "e7e5", "g1f3"], ["b8c6"])

    mesure = measure_puzzle(puzzle, _faux_reseau("b8c6"),
                            _recherche_sequentielle(["b8c6"]))

    assert mesure.nb_recherches == 1
    assert mesure.reussi_ligne is True


def test_measure_puzzle_signale_une_solution_illegale():
    """Second controle, independant des tests de build_puzzle_dataset : si
    solution[0] n'est pas legal, on compte au lieu de planter."""
    puzzle = _puzzle(["e2e4", "e7e5", "g1f3"], ["e2e4"])

    mesure = measure_puzzle(puzzle, _faux_reseau("b8c6"),
                            _recherche_sequentielle(["b8c6"]))

    assert mesure.erreur == "solution_illegale"
    assert mesure.nb_recherches == 0
    assert mesure.reussi_ligne is False


def test_measure_puzzle_signale_un_historique_illegal():
    puzzle = _puzzle(["e2e4", "e2e4"], ["b8c6"])

    mesure = measure_puzzle(puzzle, _faux_reseau("b8c6"),
                            _recherche_sequentielle(["b8c6"]))

    assert mesure.erreur == "historique_illegal"
    assert mesure.nb_recherches == 0


def test_measure_puzzle_compare_des_index_et_pas_des_chaines():
    """Une promotion dame s'ecrit 'a7a8q' cote Lichess et peut se decoder sans
    suffixe : comparer les chaines produirait un faux echec."""
    puzzle = _puzzle(["a2a4"], ["a7a8q"],
                     fen="7k/P7/8/8/8/8/8/7K w - - 0 1")
    # a2a4 n'existe pas dans cette position : on verifie d'abord le rejet,
    # puis on mesure la vraie position sans historique.
    assert measure_puzzle(puzzle, _faux_reseau("a7a8q"),
                          _recherche_sequentielle(["a7a8q"])).erreur == "historique_illegal"

    puzzle = _puzzle([], ["a7a8q"], fen="7k/P7/8/8/8/8/8/7K w - - 0 1")

    mesure = measure_puzzle(puzzle, _faux_reseau("a7a8q"),
                            _recherche_sequentielle(["a7a8q"]))

    assert mesure.erreur == ""
    assert mesure.reussi_recherche is True
    assert mesure.reussi_ligne is True


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

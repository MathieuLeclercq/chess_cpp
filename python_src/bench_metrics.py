"""Noyau de mesure du banc de puzzles.

Toute la logique de scoring vit ici et recoit ses deux acces au reseau par
injection, policy_fn et search_fn, sur le modele du fetcher de
lichess_games.fetch_games. Ce module n'importe donc ni torch ni onnxruntime, et
se teste entierement avec des faux.

Voir docs/superpowers/specs/2026-08-14-puzzle-bench-design.md
"""

import time
from dataclasses import dataclass

import chess_engine
from move_coding import (
    coords_to_uci,
    decode_move_index,
    encode_move,
    gestion_promo_dame,
    parse_uci_to_coords,
)

TAILLE_POLICY = 4672


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


class DonneesInvalides(Exception):
    """La ligne du banc ne decrit pas une position jouable."""

    def __init__(self, cause: str):
        super().__init__(cause)
        self.cause = cause


def uci_to_index(board, uci: str) -> int:
    """Index de policy d'un coup UCI dans la position courante.

    La promotion dame est implicite dans la convention AlphaZero. Lichess ecrit
    bien le suffixe, mais gestion_promo_dame couvre le cas ou il manque.
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
        # Recharger la FEN atteinte donne la meme position, sans le passe.
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


def _mesure(puzzle: BenchPuzzle, duree: float, erreur: str = "", *,
            nb_coups_legaux: int = 0,
            coup_reseau: str = "", reussi_reseau: bool = False,
            p_correct: float = 0.0, rang: int = 0, value: float = 0.0,
            coup_recherche: str = "", reussi_recherche: bool = False,
            part_visites: float = 0.0, premier_ecart: int = -1,
            nb_recherches: int = 0) -> PuzzleMeasure:
    return PuzzleMeasure(
        ligne=puzzle.ligne, rating=puzzle.rating, themes=puzzle.themes,
        plies_historique=len(puzzle.coups_uci),
        nb_coups_legaux=nb_coups_legaux,
        coup_reseau=coup_reseau, reussi_reseau=reussi_reseau,
        p_correct_reseau=float(p_correct), rang_correct_reseau=rang,
        value_reseau=float(value),
        coup_recherche=coup_recherche, reussi_recherche=reussi_recherche,
        part_visites_correct=float(part_visites),
        reussi_ligne=(premier_ecart == -1 and not erreur),
        premier_ecart=premier_ecart, nb_recherches=nb_recherches,
        duree_s=duree, erreur=erreur,
    )


def measure_puzzle(puzzle: BenchPuzzle, policy_fn, search_fn,
                   sans_historique: bool = False,
                   horloge=time.perf_counter) -> PuzzleMeasure:
    """Mesure un puzzle : colonne reseau seul, puis colonne recherche.

    policy_fn(board) -> (probabilites sur les index legaux, value)
    search_fn(board) -> sequence de 4672 flottants, visites normalisees

    Les comparaisons portent sur des index de policy et jamais sur des chaines
    UCI : l'encodage est injectif sur les coups legaux, alors que deux mises en
    forme UCI du meme coup peuvent differer.
    """
    debut = horloge()

    if not puzzle.solution_uci:
        return _mesure(puzzle, horloge() - debut, "solution_vide")

    try:
        board = charger_position(puzzle, sans_historique)
    except DonneesInvalides as exc:
        return _mesure(puzzle, horloge() - debut, exc.cause)

    nb_coups_legaux = len(board.get_legal_move_indices())
    idx_solution = uci_to_index(board, puzzle.solution_uci[0])
    if idx_solution not in set(board.get_legal_move_indices()):
        return _mesure(puzzle, horloge() - debut, "solution_illegale",
                       nb_coups_legaux=nb_coups_legaux)

    # --- Colonne reseau seul, sur la position de depart uniquement ---
    probs, value = policy_fn(board)
    p_correct = probs.get(idx_solution, 0.0)
    rang = 1 + sum(1 for p in probs.values() if p > p_correct)
    idx_reseau = max(probs, key=probs.get)
    coup_reseau = index_to_uci(board, idx_reseau)
    reussi_reseau = idx_reseau == idx_solution

    # --- Colonne recherche : premier coup, puis ligne complete ---
    coup_recherche = ""
    reussi_recherche = False
    part_visites = 0.0
    premier_ecart = -1
    nb_recherches = 0

    for rang_ply, coup_attendu in enumerate(puzzle.solution_uci):
        if rang_ply % 2 == 0:
            idx_attendu = uci_to_index(board, coup_attendu)
            if idx_attendu not in set(board.get_legal_move_indices()):
                return _mesure(
                    puzzle, horloge() - debut, "ligne_illegale",
                    nb_coups_legaux=nb_coups_legaux, coup_reseau=coup_reseau,
                    reussi_reseau=reussi_reseau, p_correct=p_correct, rang=rang,
                    value=value, coup_recherche=coup_recherche,
                    reussi_recherche=reussi_recherche,
                    part_visites=part_visites, premier_ecart=rang_ply,
                    nb_recherches=nb_recherches)

            pi = search_fn(board)
            nb_recherches += 1
            idx_choisi = max(range(TAILLE_POLICY), key=lambda i: pi[i])

            if rang_ply == 0:
                coup_recherche = index_to_uci(board, idx_choisi)
                part_visites = float(pi[idx_attendu])
                reussi_recherche = idx_choisi == idx_attendu

            if idx_choisi != idx_attendu:
                premier_ecart = rang_ply
                break

        if not board.move_piece_uci(coup_attendu):
            return _mesure(
                puzzle, horloge() - debut, "ligne_illegale",
                nb_coups_legaux=nb_coups_legaux, coup_reseau=coup_reseau,
                reussi_reseau=reussi_reseau, p_correct=p_correct, rang=rang,
                value=value, coup_recherche=coup_recherche,
                reussi_recherche=reussi_recherche, part_visites=part_visites,
                premier_ecart=rang_ply, nb_recherches=nb_recherches)

    return _mesure(
        puzzle, horloge() - debut, "",
        nb_coups_legaux=nb_coups_legaux, coup_reseau=coup_reseau,
        reussi_reseau=reussi_reseau, p_correct=p_correct, rang=rang,
        value=value, coup_recherche=coup_recherche,
        reussi_recherche=reussi_recherche, part_visites=part_visites,
        premier_ecart=premier_ecart, nb_recherches=nb_recherches)

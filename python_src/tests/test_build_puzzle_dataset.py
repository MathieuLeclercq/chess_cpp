import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_puzzle_dataset import (
    BENCH_BUCKETS,
    bucket_of,
    matches_themes,
    split_of,
)


def test_matches_real_lichess_theme_fields():
    assert matches_themes("mateIn1 short crushing")
    assert matches_themes("middlegame fork advantage")
    assert not matches_themes("endgame advantage long")
    assert not matches_themes("smotheredMate short crushing")


def test_theme_match_is_on_whole_tokens_not_substrings():
    """Discrimine reellement une implementation par sous-chaine.

    Avec la liste de themes retenue, aucun jeton n'est sous-chaine d'un autre
    theme Lichess : sur des donnees reelles, `theme in champ` et la
    correspondance par jeton donnent le meme resultat. La fragilite est donc
    latente, pas active. Ces cas synthetiques testent la propriete elle-meme,
    pour qu'elle reste vraie si la liste s'allonge un jour.
    """
    for field in ("xmateIn1x", "premateIn1", "mateIn1suffix", "forked", "pinned"):
        assert not matches_themes(field), field

    # Le meme jeton, isole, doit matcher.
    assert matches_themes("mateIn1")
    assert matches_themes("fork")
    assert matches_themes("pin")


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
    """Une divergence de convention sur la case en passant ne doit pas rejeter.

    python-chess n'ecrit la case que si une capture est reellement possible :
    apres 1.e4 il produit '-'. Une source utilisant la convention
    inconditionnelle ecrirait 'e3'. On forge donc 'e3' pour exercer vraiment
    cette divergence, et non un champ identique des deux cotes.
    """
    line = ["e2e4"]
    fields = _fen_after(line).split()
    assert fields[3] == "-", "python-chess a change de convention"

    forged = f"{fields[0]} {fields[1]} {fields[2]} e3 7 42"

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

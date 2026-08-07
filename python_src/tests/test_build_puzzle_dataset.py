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

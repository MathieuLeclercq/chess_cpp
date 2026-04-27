import csv
import chess
import random

INPUT_CSV = "../training_data/lichess_db_puzzle.csv"
OUTPUT_TXT = "../training_data/mateIn1_1900_2400.txt"
# TARGET_THEMES = ["pin", "discoveredAttack", "sacrifice", "skewer"]
TARGET_THEMES = ["mateIn1"]
MAX_FENS = 100000
RATING_RANGE = [1900, 3300]


def extract_tactical_fens():
    fens_saved = 0
    valid_puzzles = []

    print(f"Analyse du fichier CSV...")

    with open(INPUT_CSV, 'r', encoding='utf-8') as infile:
        reader = csv.reader(infile)
        next(reader)  # Skip header

        for row in reader:
            # Index Lichess CSV : 1=FEN, 2=Moves, 3=Rating, 7=Themes
            rating = int(row[3])
            themes = row[7]           

            if RATING_RANGE[0] <= rating <= RATING_RANGE[1] and any(theme in themes for theme in TARGET_THEMES):
                valid_puzzles.append(row)

    print(f"Nombre de puzzles correspondants trouvés : {len(valid_puzzles)}")

    # On mélange pour ne pas avoir que les vieux puzzles
    random.shuffle(valid_puzzles)

    with open(OUTPUT_TXT, 'w', encoding='utf-8') as outfile:
        for row in valid_puzzles:
            if fens_saved >= MAX_FENS:
                break

            fen = row[1]
            moves = row[2].split()

            try:
                board = chess.Board(fen)
                board.push(chess.Move.from_uci(moves[0]))  # On joue la gaffe adverse

                outfile.write(board.fen() + "\n")
                fens_saved += 1
            except Exception as e:
                continue

    print(
        f"Extraction terminée : {fens_saved} FENs tactiques (Rating dans {RATING_RANGE}) sauvegardés.")


if __name__ == "__main__":
    extract_tactical_fens()

"""
- advancedPawn
- advantage
- anastasiaMate
- arabianMate
- attackingF2F7
- attraction
- backRankMate
- balestraMate
- bishopEndgame
- blindSwineMate
- bodenMate
- capturingDefender
- castling
- clearance
- collinear
- collinearMove
- cornerMate
- crushing
- defensiveMove
- deflection
- discoveredAttack
- discoveredCheck
- doubleBishopMate
- doubleCheck
- dovetailMate
- enPassant
- endgame
- epauletteMate
- equality
- exposedKing
- fork
- hangingPiece
- hookMate
- interference
- intermezzo
- killBoxMate
- kingsideAttack
- knightEndgame
- long
- master
- masterVsMaster
- mate
- mateIn1
- mateIn2
- mateIn3
- mateIn4
- mateIn5
- middlegame
- morphysMate
- oneMove
- opening
- operaMate
- pawnEndgame
- pillsburysMate
- pin
- promotion
- queenEndgame
- queenRookEndgame
- queensideAttack
- quietMove
- rookEndgame
- sacrifice
- short
- skewer
- smotheredMate
- superGM
- swallowstailMate
- trappedPiece
- triangleMate
- underPromotion
- veryLong
- vukovicMate
- xRayAttack
- zugzwang

"""
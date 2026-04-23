import csv
import chess
import random

INPUT_CSV = "../training_data/lichess_db_puzzle.csv"
OUTPUT_TXT = "../training_data/tactics.txt"
TARGET_THEMES = ["pin", "discoveredAttack"]
MAX_FENS = 100000
MAX_RATING = 1400  # Seuil pour rester sur de la tactique "évidente"


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

            if rating <= MAX_RATING and any(theme in themes for theme in TARGET_THEMES):
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
                # On joue la gaffe adverse
                board.push(chess.Move.from_uci(moves[0]))

                outfile.write(board.fen() + "\n")
                fens_saved += 1
            except Exception as e:
                continue

    print(
        f"Extraction terminée : {fens_saved} FENs tactiques (Rating <= {MAX_RATING}) sauvegardés.")


if __name__ == "__main__":
    extract_tactical_fens()

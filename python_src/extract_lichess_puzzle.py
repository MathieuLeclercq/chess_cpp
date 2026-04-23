import csv
import chess

INPUT_CSV = "../training_data/lichess_db_puzzle.csv"
OUTPUT_TXT = "../training_data/tactics.txt"
TARGET_THEMES = ["pin", "discoveredAttack"]
MAX_FENS = 100000  # 100k FENs c'est largement suffisant pour diversifier


def extract_tactical_fens():
    fens_saved = 0
    with open(INPUT_CSV, 'r', encoding='utf-8') as infile, \
            open(OUTPUT_TXT, 'w', encoding='utf-8') as outfile:

        reader = csv.reader(infile)
        next(reader)  # Skip header

        for row in reader:
            if fens_saved >= MAX_FENS:
                break

            fen = row[1]
            moves = row[2].split()
            themes = row[7]

            # Vérifier si c'est un thème qui nous intéresse
            if any(theme in themes for theme in TARGET_THEMES):
                try:
                    board = chess.Board(fen)
                    # On joue le premier coup (la gaffe adverse)
                    board.push(chess.Move.from_uci(moves[0]))

                    # On sauvegarde la position où c'est à nous de trouver la tactique
                    outfile.write(board.fen() + "\n")
                    fens_saved += 1
                except Exception as e:
                    print(f"exception: {e}")
                    continue

    print(f"Extraction terminée : {fens_saved} FENs tactiques sauvegardés.")


if __name__ == "__main__":
    extract_tactical_fens()

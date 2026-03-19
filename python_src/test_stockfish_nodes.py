import chess
import chess.engine
import statistics


def estimate_stockfish_nodes(stockfish_path, elo=2500, time_limit=0.5, num_samples=50):
    print(
        f"Lancement de l'estimation sur {num_samples} positions (Temps: {time_limit}s, Elo: {elo})...")

    engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
    engine.configure({"UCI_LimitStrength": True, "UCI_Elo": elo})

    board = chess.Board()
    nodes_list = []

    for i in range(num_samples):
        if board.is_game_over():
            board.reset()

        # On utilise info=chess.engine.INFO_ALL pour forcer la récupération des statistiques
        result = engine.play(board, chess.engine.Limit(time=time_limit), info=chess.engine.INFO_ALL)

        # Récupération du nombre de nodes calculés pour ce coup
        nodes_searched = result.info.get("nodes", 0)
        nodes_list.append(nodes_searched)

        # On joue le coup pour avancer dans la partie
        board.push(result.move)

    engine.quit()

    # Calcul des statistiques
    avg_nodes = int(statistics.mean(nodes_list))
    median_nodes = int(statistics.median(nodes_list))
    min_nodes = min(nodes_list)
    max_nodes = max(nodes_list)

    print("\n=== RÉSULTATS DE L'ESTIMATION ===")
    print(f"Moyenne : {avg_nodes} nodes")
    print(f"Médiane : {median_nodes} nodes")
    print(f"Min     : {min_nodes} nodes")
    print(f"Max     : {max_nodes} nodes")
    print("=================================")

    return median_nodes


if __name__ == "__main__":
    sf_path = r"D:\logiciels\stockfish\stockfish.exe"
    estimate_stockfish_nodes(sf_path)
import sys
import time
# Assure-toi que python_src est dans le path pour trouver chess_engine.cp313-win_amd64.pyd
sys.path.append("./python_src") 
import chess_engine

MODEL_PATH = r"C:\Users\M47h1\Documents\chess_cpp\python_src\checkpoints\model_dynamic.onnx"

def main():
    print("Chargement du modèle sur GPU...")
    # True pour activer CUDA
    evaluator = chess_engine.ONNXEvaluator(MODEL_PATH, True)
    
    CONCURRENT_GAMES = 128   # On commence avec 128 parties en parallèle
    SIMS_PER_MOVE = 800      # Force de l'IA standard
    TOTAL_GAMES = 256        # Nombre total de parties à générer

    print(f"\nLancement de la génération de {TOTAL_GAMES} parties...")
    print(f"Batch GPU : {CONCURRENT_GAMES} | Simulations/coup : {SIMS_PER_MOVE}")
    
    start_time = time.time()
    
    # Appel de notre fonction C++ (Le GIL est relâché, le C++ fait tout le travail)
    games = chess_engine.generate_self_play_games(
        evaluator, 
        CONCURRENT_GAMES, 
        SIMS_PER_MOVE, 
        TOTAL_GAMES
    )
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"\nTerminé en {duration:.1f} secondes !")
    print(f"Vitesse : {TOTAL_GAMES / duration:.2f} parties / seconde.")
    
    # Vérification rapide des données
    if len(games) > 0:
        sample = games[0]
        print(f"\nExemple Partie 1 :")
        print(f" - Longueur : {len(sample.state_tensors)} demi-coups")
        print(f" - Résultat (1=Blanc, -1=Noir, 0=Nulle) : {sample.final_outcome}")

if __name__ == "__main__":
    main()
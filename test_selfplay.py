import sys
import time
import os
import gc
import torch # On utilise torch pour sauvegarder les données proprement
sys.path.append("./python_src") 
import chess_engine

# Configuration
MODEL_PATH = r"C:\Users\M47h1\Documents\chess_cpp\python_src\checkpoints\model_dynamic.onnx"
SAVE_DIR = "selfplay_data"
os.makedirs(SAVE_DIR, exist_ok=True)

def save_chunk(games, chunk_id):
    """Sauvegarde un bloc de parties sur le disque."""
    filename = os.path.join(SAVE_DIR, f"batch_{chunk_id}_{int(time.time())}.pth")
    
    data_to_save = []
    for g in games:
        data_to_save.append({
            'states': g.state_tensors,
            'policies': g.policies,
            'outcome': g.final_outcome
        })
    
    torch.save(data_to_save, filename)
    print(f"  -> Sauvegardé : {filename}")

def main():
    print("Chargement du modèle sur GPU...")
    evaluator = chess_engine.ONNXEvaluator(MODEL_PATH, True)
    
    # --- PARAMÈTRES D'OPTIMISATION ---
    CONCURRENT_GAMES = 32    # Largeur du batch GPU (tu peux tester 512 si ça tient)
    SIMS_PER_MOVE = 200       # Qualité de la recherche
    GAMES_PER_CHUNK = 64     # Nombre de parties avant de vider la RAM
    TOTAL_GOAL = 128         # Objectif total de la session
    # ----------------------------------

    print(f"\nObjectif : {TOTAL_GOAL} parties.")
    print(f"Batch GPU (Largeur) : {CONCURRENT_GAMES}")
    print(f"Chunk Size (Fréquence de vidage RAM) : {GAMES_PER_CHUNK}")

    total_generated = 0
    chunk_count = 0
    start_global = time.time()

    while total_generated < TOTAL_GOAL:
        chunk_count += 1
        print(f"\n[Chunk {chunk_count}] Génération en cours...")
        
        start_chunk = time.time()
        
        # Le manager est créé et détruit à chaque chunk pour libérer la RAM des arbres MCTS
        games = chess_engine.generate_self_play_games(
            evaluator, 
            CONCURRENT_GAMES, 
            SIMS_PER_MOVE, 
            GAMES_PER_CHUNK
        )
        
        duration_chunk = time.time() - start_chunk
        total_generated += len(games)
        
        save_chunk(games, chunk_count)
        
        # Libération TOTALE
        del games
        # Forcer le Garbage Collector à passer tout de suite
        gc.collect()
        
        vitesse = len(games) / duration_chunk
        print(f"Chunk terminé en {duration_chunk:.1f}s ({vitesse:.2f} parties/s)")
        print(f"Progression totale : {total_generated}/{TOTAL_GOAL}")

    end_global = time.time()
    print(f"\n=== SESSION TERMINÉE EN {end_global - start_global:.1f}s ===")
    print(f"Vitesse moyenne : {total_generated / (end_global - start_global):.2f} parties/s")

if __name__ == "__main__":
    main()
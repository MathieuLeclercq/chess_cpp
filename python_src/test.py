import chess_engine

def main():
    # 1. Instanciation du moteur C++
    board = chess_engine.Chessboard()
    board.set_startup_pieces()

    # 2. Vérification d'une case (ex: e2 où se trouve un pion blanc)
    # file 4 = colonne 'e', rank 1 = rangée '2'
    square_e2 = board.get_square(4, 1)
    piece = square_e2.get_piece()
    
    print(f"Case {square_e2.get_name()}:")
    print(f" - Occupée : {square_e2.is_occupied()}")
    if square_e2.is_occupied():
        print(f" - Type de pièce : {piece.get_type().name}")
        print(f" - Couleur : {piece.get_color().name}")

    # 3. Récupération des coups légaux pour ce pion
    print("\nRecherche des coups légaux pour e2...")
    moves = board.get_naive_legal_moves(4, 1)
    
    for i, move in enumerate(moves):
        dest = move.get_dest_square()
        promo = move.get_promotion()
        promo_str = f" (Promotion: {promo.name})" if promo != chess_engine.PieceType.NONE else ""
        print(f" Coup {i+1} : {dest.get_name()}{promo_str}")

if __name__ == "__main__":
    main()
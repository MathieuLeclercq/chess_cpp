#include <iostream>
// #include "piece.hpp"
// #include "square.hpp"
#include "chessboard.hpp"


int main()
{
    std::cout << "Hello World!" << std::endl;
    Chessboard chessboard;
    chessboard.setStartupPieces();
    std::cout<<chessboard.getSquare(0,0).getPiece().getType()<<std::endl;
    // chessboard.board[0][0].setPiece(Piece(WHITE,KING));

    // move the white knight in the middle of the board
    // std::vector<Square> vec_legal_moves = chessboard.getLegalMoves(1,1);
    // std::cout<<"legal moves: "<<std::endl;
    // std::cout<<vec_legal_moves.size()<<std::endl;
    // for (int i = 0; i < vec_legal_moves.size(); i++)
    // {
    //     std::cout<<vec_legal_moves[i].getName()<<std::endl;
    // }

    chessboard.movePiece("a2","a3");
    chessboard.movePiece("a1","a2");
    chessboard.movePiece("d2","d4");

    chessboard.print();
    return 0;
}
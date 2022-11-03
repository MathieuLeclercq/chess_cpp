#include <iostream>
// #include "piece.hpp"
// #include "square.hpp"
#include "chessboard.hpp"


int main()
{
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

    chessboard.movePiece("d2","d4");
    chessboard.movePiece("d7","d5");
    chessboard.movePiece("c2","c4");
    chessboard.movePiece("e7","e5");
    chessboard.movePiece("d1","a4"); // check
    chessboard.movePiece("e8","d7"); // king still under check
    chessboard.movePiece("c8","d7");
    chessboard.movePiece("g1","f3");
    chessboard.movePiece("d7","e6");
    chessboard.movePiece("g8","f6");
    chessboard.movePiece("d4","e5");
    chessboard.movePiece("b8","d7");
    chessboard.movePiece("b8","c6");
    chessboard.movePiece("e2","e3");
    chessboard.movePiece("h7","h6");
    chessboard.movePiece("f1","e2");
    chessboard.movePiece("f8","e7");


    // chessboard.print();
    return 0;
}
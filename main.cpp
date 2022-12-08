#include <iostream>
// #include "piece.hpp"
// #include "square.hpp"
#include "chessboard.hpp"

#include <chrono>


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


    auto t_start = std::chrono::high_resolution_clock::now();


    // chessboard.movePiece("d2","d4");
    // chessboard.movePiece("d7","d5");

    // chessboard.movePiece("c2","c4");
    // chessboard.movePiece("e7","e5");

    // chessboard.movePiece("d1","a4"); // check
    // chessboard.movePiece("e8","d7"); // king still under check
    // chessboard.movePiece("c8","d7");

    // chessboard.movePiece("g1","f3");
    // chessboard.movePiece("d7","e6");//
    // chessboard.movePiece("g8","f6");

    // chessboard.movePiece("d4","e5");
    // chessboard.movePiece("b8","d7");
    // chessboard.movePiece("b8","c6");

    // chessboard.movePiece("e2","e3");
    // chessboard.movePiece("h7","h5");

    // chessboard.movePiece("h1","g1");
    // chessboard.movePiece("h8","g8");

    // chessboard.movePiece("f1","e2");
    // chessboard.movePiece("f8","e7");
    
    // chessboard.movePiece("e1","g1"); // white short castle
    // chessboard.movePiece("e8","g8"); // black short castle




    // chessboard.movePiece("d2","d4");
    // chessboard.movePiece("f7","f6");
    // chessboard.movePiece("d4","d5");
    // chessboard.movePiece("e7","e5");
    // chessboard.movePiece("d5","e6");



    // chessboard.movePiece("d2","d4");
    // chessboard.movePiece("d7","d5");
    // // c4
    // chessboard.movePiece("c2","c4");
    // // e5
    // chessboard.movePiece("e7","e5");
    // // d4xe5
    // chessboard.movePiece("d4","e5");
    // // d4
    // chessboard.movePiece("d5","d4");
    // // e3
    // chessboard.movePiece("e2","e3");
    // // bishop b4
    // chessboard.movePiece("f8","b4");
    // // bishop d2
    // chessboard.movePiece("c1","d2");
    // chessboard.movePiece("d4","e3");
    // chessboard.movePiece("d2","b4");

    // chessboard.movePiece("e3","f2");
    // // king e2
    // chessboard.movePiece("e1","e2");
    // // pawn takes and promotes
    // chessboard.movePiece("f2","g1");




    while (true)
    {
        std::string from;
        std::string to;
        std::cout<<"from: ";
        std::cin>>from;
        std::cout<<"to: ";
        std::cin>>to;
        chessboard.movePiece(from,to);
    }

    auto t_end = std::chrono::high_resolution_clock::now();
    double elapsed_time_ms = std::chrono::duration<double, std::milli>(t_end-t_start).count();
    std::cout<<"elapsed time: "<<elapsed_time_ms<<" ms"<<std::endl;
    // std::cin.get();



    // chessboard.print();
    return 0;
}
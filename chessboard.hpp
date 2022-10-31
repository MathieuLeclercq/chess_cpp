#pragma once
#include <iostream>
#include <vector>
#include "piece.hpp"
#include "square.hpp"


class Chessboard
{
    private:
    

    public:
        // constructors
        Chessboard();
        std::vector<std::vector<Square>> board;

        // getters
        const Square& getSquare(int file, int rank) const; 
        Square& getSquare(int file, int rank);
        int getNumberOfOccupiedSquares() const;
        void print() const;
        std::vector<Square> getLegalMoves(int file, int rank) const;


        // setters
        void Clear();
        void setStartupPieces();
        void printBoard();
};
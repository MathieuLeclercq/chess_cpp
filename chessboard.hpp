#pragma once
#include <iostream>
#include <vector>
#include <algorithm>
#include "piece.hpp"
#include "square.hpp"


class Chessboard
{
    private:
    const std::array<char, 8> files = {'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'};
    const std::array<char, 8> ranks = {'1', '2', '3', '4', '5', '6', '7', '8'};
    

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
        void movePiece(int orig_file,int orig_rank, int file, int rank);
        void movePiece(std::string orig_square, std::string square);
};
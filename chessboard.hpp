#pragma once
#include <iostream>
#include <vector>
#include <map>
#include <algorithm>
#include "piece.hpp"
#include "square.hpp"


class Chessboard
{
    private:
    const std::array<char, 8> files = {'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'};
    const std::array<char, 8> ranks = {'1', '2', '3', '4', '5', '6', '7', '8'};
    std::vector<std::vector<Square>> board;


    
    std::vector<std::map<PieceType, std::array<Square,2>>> moveHistory;
    std::vector<std::vector<std::vector<Square>>> boardHistory;

    public:
        // constructors
        Chessboard();
        

        // getters
        const Square& getSquare(int file, int rank) const; 
        Square& getSquare(int file, int rank);
        int getNumberOfOccupiedSquares() const;
        void print() const;
        void print(std::vector<std::vector<Square>> some_board) const;
        std::vector<Square> getLegalMoves(int file, int rank) const;
        const std::vector<std::map<PieceType, std::array<Square,2>>>& getMoveHistory() const;
        std::vector<std::map<PieceType, std::array<Square,2>>>& getMoveHistory();
        const std::vector<std::vector<std::vector<Square>>>& getBoardHistory() const;
        std::vector<std::vector<std::vector<Square>>>& getBoardHistory();
        
        



        // setters
        void Clear();
        void setStartupPieces();
        void movePiece(int orig_file,int orig_rank, int file, int rank);
        void movePiece(std::string orig_square, std::string square);
        void updateHistory(Square first_square, Square second_square);
};
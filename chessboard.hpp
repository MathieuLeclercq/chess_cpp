#pragma once
#include <iostream>
#include <vector>
#include <unordered_map>
#include <algorithm>
#include "piece.hpp"
#include "square.hpp"
#include "move.hpp"


class Chessboard
{
    private:
    const std::array<char, 8> files = {'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'};
    const std::array<char, 8> ranks = {'1', '2', '3', '4', '5', '6', '7', '8'};
    std::vector<std::vector<Square>> board;
    Color turn = WHITE;
    bool short_castle_white = true;
    bool long_castle_white = true;
    bool short_castle_black = true;
    bool long_castle_black = true;
    bool en_passant = false;
    int en_passant_file = -1;



    
    std::vector<Move> moveHistory;
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
        void printPly() const;
        std::vector<Square> getLegalMoves(int file, int rank) const;
        const std::vector<Move>& getMoveHistory() const;
        std::vector<Move>& getMoveHistory();
        const std::vector<std::vector<std::vector<Square>>>& getBoardHistory() const;
        std::vector<std::vector<std::vector<Square>>>& getBoardHistory();
        void checkEnPassant();
        bool checkForCheck() const;
        
        



        // setters
        void Clear();
        void setStartupPieces();
        void setBoard(std::vector<std::vector<Square>> some_board);
        void movePiece(int orig_file,int orig_rank, int file, int rank);
        void movePiece(std::string orig_square, std::string square);
        void updateHistory(const Square& first_square, const Square& second_square);
        void updateCastleFlags();
};
#pragma once
#include <iostream>
#include <vector>
#include <string>
#include <algorithm>
#include <unordered_map>
#include <array>
#include "piece.hpp"
#include "square.hpp"
#include "move.hpp"

class Chessboard
{
    private:
    const std::array<char, 8> files = {'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'};
    const std::array<char, 8> ranks = {'1', '2', '3', '4', '5', '6', '7', '8'};
    std::array<Square, 64> board;
    Color turn = WHITE;
    bool short_castle_white = true;
    bool long_castle_white = true;
    bool short_castle_black = true;
    bool long_castle_black = true;
    bool en_passant = false;
    int en_passant_file = -1;
    bool checkmate = false;



    
    std::vector<Move> moveHistory;
    std::vector<std::array<Square, 64>> boardHistory;

    public:
        // constructors
        Chessboard();
        

        // getters
        const Square& getSquare(int file, int rank) const; 
        Square& getSquare(int file, int rank);
        int getNumberOfOccupiedSquares() const;
        void print() const;
        void print(std::array<Square, 64> some_board) const;
        void printPly() const;
        std::vector<Square> getLegalMoves(int file, int rank) const;
        const std::vector<Move>& getMoveHistory() const;
        std::vector<Move>& getMoveHistory();
        const std::vector<std::array<Square, 64>>& getBoardHistory() const;
        std::vector<std::array<Square, 64>>& getBoardHistory();
        void checkEnPassant();
        bool checkForCheck() const;
        bool checkForCheckmate();

        
        



        // setters
        void Clear();
        void setStartupPieces();
        void setBoard(std::array<Square, 64> some_board);
        bool movePiece(int orig_file,int orig_rank, int file, int rank, PieceType promotion = NONE);
        bool movePiece(std::string orig_square, std::string square);
        bool movePieceSAN(std::string san);
        void updateHistory(const Square& first_square, const Square& second_square);
        void updateCastleFlags();
        void checkPromotion(Square& second_square, PieceType force_promotion = NONE);
};
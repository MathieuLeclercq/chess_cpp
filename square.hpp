#pragma once
#include <iostream>
#include <array>
#include "piece.hpp"



class Square
{
    private:
        int file;
        int rank;
        bool isOccupied;
        Piece piece;
        const std::array<std::string, 8> files = {"a", "b", "c", "d", "e", "f", "g", "h"};
        const std::array<std::string, 8> ranks = {"1", "2", "3", "4", "5", "6", "7", "8"};

    public:
        // constructors
        Square();
        Square(int file, int rank);
        Square(int file, int rank, Piece piece);

        // getters
        const Piece& getPiece() const;
        Piece& getPiece();
        bool CheckOccupied() const;
        int getFile() const;
        int getRank() const;
        std::string getName() const;
        bool operator == (const Square& square) const;

        // setters
        void setPiece(Piece piece);
        void setPosition(int file, int rank);
        void removePiece();

};
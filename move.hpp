#pragma once

#include <iostream>
#include "piece.hpp"
#include "square.hpp"

class Move
{
private:
    Piece piece;
    Square orig_square;
    Square dest_square;
public:
    Move(Square orig_square, Square dest_square);
    const Piece& getPiece() const;
    Piece& getPiece();

    const Square& getOrigSquare() const;
    Square& getOrigSquare();
    const Square& getDestSquare() const;
    Square& getDestSquare();
};
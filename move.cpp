#include "move.hpp"



//...............Constructors...............
Move::Move(Square orig_square, Square dest_square)
{
    this->piece = dest_square.getPiece();
    this->orig_square = orig_square;
    this->dest_square = dest_square;
}


//...............Getters...............
const Piece& Move::getPiece() const
{
    return this->piece;
}

Piece& Move::getPiece()
{
    return this->piece;
}

const Square& Move::getOrigSquare() const
{
    return this->orig_square;
}

Square& Move::getOrigSquare()
{
    return this->orig_square;
}

const Square& Move::getDestSquare() const
{
    return this->dest_square;
}

Square& Move::getDestSquare()
{
    return this->dest_square;
}
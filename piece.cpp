#include "piece.hpp"


//...............Constructors...............

Piece::Piece()
{
    this->type = NONE;
    this->color = NO_COLOR;
}

Piece::Piece(Color color, PieceType type)
{
    this->color = color;
    this->type = type;
}


//...............Getters...............
const PieceType& Piece::getType() const
{
    return this->type;
}

Color Piece::getColor()
{
    return this->color;
}

const Color& Piece::getColor() const
{
    return this->color;
}


//...............Setters...............
void Piece::setType(PieceType type)
{
    this->type = type;

}

void Piece::move(int file, int rank)
{
    // move the piece
}


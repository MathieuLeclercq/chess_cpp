#include "piece.hpp"


//...............Constructors...............

Piece::Piece()
{
    this->type = NONE;
    this->color = NO_COLOR;
    this->value = 0;
}

Piece::Piece(Color color, PieceType type)
{
    this->color = color;
    this->type = type;
    this->setValue();
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

int Piece::getValue() const
{
    int value = this->value;
    return value;
}

//...............Setters...............
void Piece::setType(PieceType type)
{
    this->type = type;

}



void Piece::setValue()
{
    if (this->type == KING)
        this->value = 1000;
    else if (this->type == QUEEN)
        this->value = 9;
    else if (this->type == ROOK)
        this->value = 5;
    else if (this->type == BISHOP || this->type == KNIGHT)
        this->value = 3;
    else if (this->type == PAWN)
        this->value = 1;
    else
        this->value = 0;
}

void Piece::move(int file, int rank)
{
    // move the piece
}


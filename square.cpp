#include "square.hpp"

//...............Constructors...............

Square::Square()
{
    // set the file and rank to -1
    this->file = -1;
    this->rank = -1;
    // this->isOccupied = false;

}

Square::Square(int file, int rank)
{
    this->file = file;
    this->rank = rank;
    // this->isOccupied = false;
}

Square::Square(int file, int rank, Piece piece)
{
    this->file = file;
    this->rank = rank;
    this->piece = piece;
    // this->isOccupied = true;
}

//...............Getters...............

const Piece& Square::getPiece() const
{
    return this->piece;
}

Piece& Square::getPiece()
{
    return this->piece;
}

bool Square::CheckOccupied() const
{
    bool occupied = this->piece.getType() != NONE;
    return occupied;
}

int Square::getFile() const
/*
Returns an integer between 0 and 7 representing the file of the square
*/
{
    return this->file;
}


int Square::getRank() const
/*
Returns an integer between + and 7 representing the rank of the square
*/
{
    return this->rank;
}


std::string Square::getName() const
{
    std::string square_name = this->files[this->file] + this->ranks[this->rank];
    return square_name;
}

//...............Setters...............

void Square::setPiece(Piece piece)
{
    this->piece = piece;
    // this->isOccupied = true;
}

void Square::setPosition(int file, int rank)
{
    this->file = file;
    this->rank = rank;
}

void Square::removePiece()
{
    this->piece = Piece();
}


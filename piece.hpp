#pragma once
#include <iostream>




enum PieceType
{
    KING,
    QUEEN,
    ROOK,
    BISHOP,
    KNIGHT,
    PAWN,
    NONE
};

enum Color
{
    WHITE,
    BLACK
};

class Piece
{
    private:
        PieceType type;
        Color color;

    public:
        // constructors
        Piece();
        Piece(Color color, PieceType type);


        // getters
        const PieceType& getType() const;
        Color getColor();
    
        // setters
        void setType(PieceType type);
        void move(int file, int rank);

};

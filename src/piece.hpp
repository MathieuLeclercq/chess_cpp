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
    BLACK,
    NO_COLOR
};

class Piece
{
    private:
        PieceType type;
        Color color;
        int value;

    public:
        // constructors
        Piece();
        Piece(Color color, PieceType type);


        // getters
        const PieceType& getType() const;
        const Color& getColor() const;
        Color getColor();
        int getValue() const;

        // setters
        void setType(PieceType type);
        void move(int file, int rank);
        void setValue();

};

#include "chessboard.hpp"

//...............Constructors...............

Chessboard::Chessboard()
{
    // initialize the board
    Clear();
}



//...............Getters...............


const Square& Chessboard::getSquare(int file, int rank) const
{
    return board[file][rank];
}

Square& Chessboard::getSquare(int file, int rank)
{
    return board[file][rank];
}

int Chessboard::getNumberOfOccupiedSquares() const
{
    int count = 0;
    for (int i = 0; i < 8; i++)
    {
        for (int j = 0; j < 8; j++)
        {
            if (board[i][j].CheckOccupied())
            {
                count++;
            }
        }
    }
    return count;
}

void Chessboard::print() const
{
    for (int i = 7; i > -1; i--)
    {
        for (int j = 0; j < 8; j++)
        {
            // if (this->board[j][i].CheckOccupied())
            // {
            //     std::cout << "X ";
            // }
            // else
            // {
            //     std::cout << "O ";
            // }
            std::cout << board[j][i].getPiece().getType() << " ";
        }
        std::cout << std::endl;
    }
}



std::vector<Square> Chessboard::getLegalMoves(int file, int rank) const
{
    Square square = board[file][rank];
    std::vector<Square> legalMoves;
    PieceType type = square.getPiece().getType();
    Color color = square.getPiece().getColor();

    Color oppositeColor = (color == WHITE) ? BLACK : WHITE;

    switch (type)
    {
        case PAWN:

        {
            if (color == WHITE && rank<7 && this->board[file][rank + 1].CheckOccupied() == false)
            {
                legalMoves.push_back(this->board[file][rank + 1]);
                if (rank == 1 && this->board[file][rank + 2].CheckOccupied() == false) // can move 2 squares if first square
                {
                    legalMoves.push_back(this->board[file][rank + 2]);
                }
            }
            else if (color == BLACK && rank > 0 && this->board[file][rank - 1].CheckOccupied() == false)
            {
                legalMoves.push_back(this->board[file][rank - 1]);
                if (rank == 6 && this->board[file][rank - 2].CheckOccupied() == false) // can move 2 squares if first square
                {
                    legalMoves.push_back(this->board[file][rank - 2]);
                }
            }

            if (color == WHITE && rank<7)
            {
                if (file<7 && this->board[file + 1][rank + 1].getPiece().getColor() == oppositeColor)
                {
                    legalMoves.push_back(this->board[file + 1][rank + 1]);
                }
                if (file>0 && this->board[file - 1][rank + 1].getPiece().getColor() == oppositeColor)
                {
                    legalMoves.push_back(this->board[file - 1][rank + 1]);
                }
            }
            else if (color == BLACK && rank>0)
            {
                if (file<7 && this->board[file + 1][rank - 1].getPiece().getColor() == oppositeColor)
                {
                    legalMoves.push_back(this->board[file + 1][rank - 1]);
                }
                if (file>0 && this->board[file - 1][rank - 1].getPiece().getColor() == oppositeColor)
                {
                    legalMoves.push_back(this->board[file - 1][rank - 1]);
                }
            }
            break;

        }
        case ROOK:
        {
            for (int i = rank+1; i<8; i++) // top
            {
                if (this->board[file][i].CheckOccupied()==false)
                    legalMoves.push_back(this->board[file][i]);
                else if (this->board[file][i].getPiece().getColor() == oppositeColor)
                {
                    legalMoves.push_back(this->board[file][i]);
                    break; // break because stop after first opponent piece
                }
                else
                    break;
            }
            for (int i = rank-1; i>-1; i--) // bottom
            {
                if (this->board[file][i].CheckOccupied()==false)
                    legalMoves.push_back(this->board[file][i]);

                else if (this->board[file][i].getPiece().getColor() == oppositeColor)
                {
                    legalMoves.push_back(this->board[file][i]);
                    break;
                }
                else
                    break;
            }
            for (int i = file+1; i<8; i++) // right
            {
                if (this->board[i][rank].CheckOccupied()==false)
                    legalMoves.push_back(this->board[i][rank]);

                else if (this->board[i][rank].getPiece().getColor() == oppositeColor)
                {
                    legalMoves.push_back(this->board[i][rank]);
                    break;
                }
                else
                    break;
            }
            for (int i = file-1; i>-1; i--) // left
            {
                if (this->board[i][rank].CheckOccupied()==false)
                    legalMoves.push_back(this->board[i][rank]);

                else if (this->board[i][rank].getPiece().getColor() == oppositeColor)
                {
                    legalMoves.push_back(this->board[i][rank]);
                    break;
                }
                else
                    break;
            }
            break;
        }
        case KNIGHT:
        {
            if (file+2<8 && rank+1<8 && this->board[file+2][rank+1].getPiece().getColor()!=color)
                legalMoves.push_back(this->board[file+2][rank+1]);
            if (file+2<8 && rank-1>-1 && this->board[file+2][rank-1].getPiece().getColor()!=color)
                legalMoves.push_back(this->board[file+2][rank-1]);
            if (file-2>-1 && rank+1<8 && this->board[file-2][rank+1].getPiece().getColor()!=color)
                legalMoves.push_back(this->board[file-2][rank+1]);
            if (file-2>-1 && rank-1>-1 && this->board[file-2][rank-1].getPiece().getColor()!=color)
                legalMoves.push_back(this->board[file-2][rank-1]);
            if (file+1<8 && rank+2<8 && this->board[file+1][rank+2].getPiece().getColor()!=color)
                legalMoves.push_back(this->board[file+1][rank+2]);
            if (file+1<8 && rank-2>-1 && this->board[file+1][rank-2].getPiece().getColor()!=color)
                legalMoves.push_back(this->board[file+1][rank-2]);
            if (file-1>-1 && rank+2<8 && this->board[file-1][rank+2].getPiece().getColor()!=color)
                legalMoves.push_back(this->board[file-1][rank+2]);
            if (file-1>-1 && rank-2>-1 && this->board[file-1][rank-2].getPiece().getColor()!=color)
                legalMoves.push_back(this->board[file-1][rank-2]);
            break;
        }
        case BISHOP:
        {
            // TODO: check if possible to do this with 1 loop? Not sure if possible
            for (int i = 1; i<8; i++)
            {
                if (file+i<8 && rank+i<8 && this->board[file+i][rank+i].CheckOccupied()==false) // up right
                    legalMoves.push_back(this->board[file+i][rank+i]);
                else if (file+i<8 && rank+i<8 && this->board[file+i][rank+i].getPiece().getColor() == oppositeColor)
                {
                    legalMoves.push_back(this->board[file+i][rank+i]);
                    break;
                }
                else
                    break;
            }
            for (int i = 1; i<8; i++)
            {
                if (file-i>-1 && rank+i<8 && this->board[file-i][rank+i].CheckOccupied()==false) // up left
                    legalMoves.push_back(this->board[file-i][rank+i]);

                else if (file-i>-1 && rank+i<8 && this->board[file-i][rank+i].getPiece().getColor() == oppositeColor)
                {
                    legalMoves.push_back(this->board[file-i][rank+i]);
                    break;
                }
                else
                    break;
            }
            for (int i = 1; i<8; i++)
            {
                if (file+i<8 && rank-i>-1 && this->board[file+i][rank-i].CheckOccupied()==false) // down right
                    legalMoves.push_back(this->board[file+i][rank-i]);
                else if (file+i<8 && rank-i>-1 && this->board[file+i][rank-i].getPiece().getColor() == oppositeColor)
                {
                    legalMoves.push_back(this->board[file+i][rank-i]);
                    break;
                }
                else
                    break;
            }
            for (int i = 1; i<8; i++)
            {
                if (file-i>-1 && rank-i>-1 && this->board[file-i][rank-i].CheckOccupied()==false) // down left
                    legalMoves.push_back(this->board[file-i][rank-i]);
                else if (file-i>-1 && rank-i>-1 && this->board[file-i][rank-i].getPiece().getColor() == oppositeColor)
                {
                    legalMoves.push_back(this->board[file-i][rank-i]);
                    break;
                }
                else
                    break;
            }
            break;
        }
        case QUEEN:
        {
            for (int i = rank+1; i<8; i++)  // up
            {
                if (this->board[file][i].CheckOccupied()==false)
                    legalMoves.push_back(this->board[file][i]);
                else if (this->board[file][i].getPiece().getColor() == oppositeColor)
                {
                    legalMoves.push_back(this->board[file][i]);
                    break;
                }
                else
                    break;

            }
            for (int i = rank-1; i>-1; i--) // down
            {
                if (this->board[file][i].CheckOccupied()==false)
                    legalMoves.push_back(this->board[file][i]);
                else if (this->board[file][i].getPiece().getColor() == oppositeColor)
                {
                    legalMoves.push_back(this->board[file][i]);
                    break;
                }
                else
                    break;

            }
            for (int i = file+1; i<8; i++) // right
            {
                if (this->board[i][rank].CheckOccupied()==false)
                    legalMoves.push_back(this->board[i][rank]);
                else if (this->board[i][rank].getPiece().getColor() == oppositeColor)
                {
                    legalMoves.push_back(this->board[i][rank]);
                    break;
                }
                else
                    break;

            }
            for (int i = file-1; i>-1; i--) // left
            {
                if (this->board[i][rank].CheckOccupied()==false)
                    legalMoves.push_back(this->board[i][rank]);
                else if (this->board[i][rank].getPiece().getColor() == oppositeColor)
                {
                    legalMoves.push_back(this->board[i][rank]);
                    break;
                }
                else
                    break;

            }
            for (int i = 1; i<8; i++) 
            {
                if (file+i<8 && rank+i<8 && this->board[file+i][rank+i].CheckOccupied()==false) // up right
                    legalMoves.push_back(this->board[file+i][rank+i]);
                else if (file+i<8 && rank+i<8 && this->board[file+i][rank+i].getPiece().getColor() == oppositeColor)
                {
                    legalMoves.push_back(this->board[file+i][rank+i]);
                    break;
                }
                else
                    break;


            }
            for (int i = 1; i<8; i++)
            {
                if (file-i>-1 && rank+i<8 && this->board[file-i][rank+i].CheckOccupied()==false) // up left
                    legalMoves.push_back(this->board[file-i][rank+i]);
                else if (file-i>-1 && rank+i<8 && this->board[file-i][rank+i].getPiece().getColor() == oppositeColor)
                {
                    legalMoves.push_back(this->board[file-i][rank+i]);
                    break;
                }
                else
                    break;


            }
            for (int i = 1; i<8; i++)
            {
                if (file+i<8 && rank-i>-1 && this->board[file+i][rank-i].CheckOccupied()==false) // down right
                    legalMoves.push_back(this->board[file+i][rank-i]);
                else if (file+i<8 && rank-i>-1 && this->board[file+i][rank-i].getPiece().getColor() == oppositeColor)
                {
                    legalMoves.push_back(this->board[file+i][rank-i]);
                    break;
                }
                else
                    break;


            }
            for (int i = 1; i<8; i++)
            {
                if (file-i>-1 && rank-i>-1 && this->board[file-i][rank-i].CheckOccupied()==false) // down left
                    legalMoves.push_back(this->board[file-i][rank-i]);
                else if (file-i>-1 && rank-i>-1 && this->board[file-i][rank-i].getPiece().getColor() == oppositeColor)
                {
                    legalMoves.push_back(this->board[file-i][rank-i]);
                    break;
                }
                else
                    break;


            }
            break;
        }
        case KING:
        {
            if (file+1<8 && rank+1<8 && this->board[file+1][rank+1].getPiece().getColor() != color) // up right
                legalMoves.push_back(this->board[file+1][rank+1]);
            if (file+1<8 && rank-1>-1 && this->board[file+1][rank-1].getPiece().getColor() != color) // down right
                legalMoves.push_back(this->board[file+1][rank-1]);
            if (file-1>-1 && rank+1<8 && this->board[file-1][rank+1].getPiece().getColor() != color)  // up left
                legalMoves.push_back(this->board[file-1][rank+1]);
            if (file-1>-1 && rank-1>-1 && this->board[file-1][rank-1].getPiece().getColor() != color) // down left
                legalMoves.push_back(this->board[file-1][rank-1]);
            if (file+1<8 && this->board[file+1][rank].getPiece().getColor() != color) // right
                legalMoves.push_back(this->board[file+1][rank]);
            if (file-1>-1 && this->board[file-1][rank].getPiece().getColor() != color) // left
                legalMoves.push_back(this->board[file-1][rank]);
            if (rank+1<8 && this->board[file][rank+1].getPiece().getColor() != color) // up
                legalMoves.push_back(this->board[file][rank+1]);
            if (rank-1>-1 && this->board[file][rank-1].getPiece().getColor() != color) // down
                legalMoves.push_back(this->board[file][rank-1]);
            break;
        }

    }
    return legalMoves;

}


//...............Setters...............


void Chessboard::Clear()
{

    this->board = std::vector<std::vector<Square>>(8, std::vector<Square>(8));
    for (int i = 0; i<8; i++)
    {
        for (int j = 0; j<8; j++)
        {
            this->board[i][j].setPosition(i,j);
        }
    }

}

void Chessboard::setStartupPieces()
{

    for (int i = 0; i < 8; i++)
    {
        for (int j = 0; j < 8; j++)
        {
            // pawns
            int file = i+1;
            int rank = j+1;
            if (rank == 2)
            {
                board[i][j].setPiece(Piece(WHITE, PAWN));
            }
            else if (rank == 7)
            {
                board[i][j].setPiece(Piece(BLACK, PAWN));
            }
            // rooks
            else if (rank == 1 && (file == 1 || file == 8))
            {
                board[i][j].setPiece(Piece(WHITE, ROOK));
            }
            else if (rank == 8 && (file == 1 || file == 8))
            {
                board[i][j].setPiece(Piece(BLACK, ROOK));
            }

            // knights
            else if (rank == 1 && (file == 2 || file == 7))
            {
                board[i][j].setPiece(Piece(WHITE, KNIGHT));
            }
            else if (rank == 8 && (file == 2 || file == 7))
            {
                board[i][j].setPiece(Piece(BLACK, KNIGHT));
            }

            // bishops
            else if (rank == 1 && ( file == 3 || file == 6))
            {
                board[i][j].setPiece(Piece(WHITE, BISHOP));
            }
            else if (rank == 8 && (file == 3 || file == 6))
            {
                board[i][j].setPiece(Piece(BLACK, BISHOP));
            }

            // queen
            else if (rank == 1 && file == 4)
            {
                board[i][j].setPiece(Piece(WHITE, QUEEN));
            }
            else if (rank == 8 && file == 4)
            {
                board[i][j].setPiece(Piece(BLACK, QUEEN));
            }

            // king
            else if (rank == 1 && file == 5)
            {
                board[i][j].setPiece(Piece(WHITE, KING));
            }
            else if (rank == 8 && file == 5)
            {
                board[i][j].setPiece(Piece(BLACK, KING));
            }

            // empty squares
            else
            {
                board[i][j].setPiece(Piece());
            }

            
        }
    }
}

void Chessboard::movePiece(int orig_file,int orig_rank, int file, int rank)
{
    Square first_square = this->board[orig_file][orig_rank];
    Square second_square = this->board[file][rank];
    const std::vector<Square> legalMoves = this->getLegalMoves(orig_file, orig_rank);
    if (std::find(legalMoves.begin(), legalMoves.end(), second_square) != legalMoves.end())
    {
        this->board[file][rank].setPiece(first_square.getPiece());
        this->board[orig_file][orig_rank].setPiece(Piece());
    }
    else
    {
        std::cout << "Illegal move" << std::endl;
    }
}

void Chessboard::movePiece(std::string orig_square, std::string square)
{
    // find index of orig_square[0] in files
    int orig_file = std::find(files.begin(), files.end(), orig_square[0]) - files.begin();
    int orig_rank = std::find(ranks.begin(), ranks.end(), orig_square[1]) - ranks.begin();

    // find index of square[0] in files
    int file = std::find(files.begin(), files.end(), square[0]) - files.begin();
    int rank = std::find(ranks.begin(), ranks.end(), square[1]) - ranks.begin();
    std::cout<<"orig_file: " << orig_file << " orig_rank: " << orig_rank << " file: " << file << " rank: " << rank << std::endl;
    this->movePiece(orig_file, orig_rank, file, rank);
}
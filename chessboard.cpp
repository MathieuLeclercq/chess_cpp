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
    switch (type)
    {
        case PAWN:

        {
            if (color == WHITE && this->board[file][rank + 1].CheckOccupied() == false)
            {
                legalMoves.push_back(this->board[file][rank + 1]);
                if (rank == 1 && this->board[file][rank + 2].CheckOccupied() == false) // can move 2 squares if first square
                {
                    legalMoves.push_back(this->board[file][rank + 2]);
                }
            }
            else if (color == BLACK && this->board[file][rank - 1].CheckOccupied() == false)
            {
                legalMoves.push_back(this->board[file][rank - 1]);
                if (rank == 6 && this->board[file][rank - 2].CheckOccupied() == false) // can move 2 squares if first square
                {
                    legalMoves.push_back(this->board[file][rank - 2]);
                }
            }
            break;

        }
        case ROOK:
        {
            for (int i = rank+1; i<8; i++)
            {
                if (this->board[file][i].CheckOccupied()==false)
                    legalMoves.push_back(this->board[file][i]);
                else
                    break;
            }
            for (int i = rank-1; i>-1; i--)
            {
                if (this->board[file][i].CheckOccupied()==false)
                    legalMoves.push_back(this->board[file][i]);
                else
                    break;
            }
            for (int i = file+1; i<8; i++)
            {
                if (this->board[i][rank].CheckOccupied()==false)
                    legalMoves.push_back(this->board[i][rank]);
                else
                    break;
            }
            for (int i = file-1; i>-1; i--)
            {
                if (this->board[i][rank].CheckOccupied()==false)
                    legalMoves.push_back(this->board[i][rank]);
                else
                    break;
            }
            break;
        }
        case KNIGHT:
        {
            if (file+2<8 && rank+1<8 && this->board[file+2][rank+1].CheckOccupied()==false)
                legalMoves.push_back(this->board[file+2][rank+1]);
            if (file+2<8 && rank-1>-1 && this->board[file+2][rank-1].CheckOccupied()==false)
                legalMoves.push_back(this->board[file+2][rank-1]);
            if (file-2>-1 && rank+1<8 && this->board[file-2][rank+1].CheckOccupied()==false)
                legalMoves.push_back(this->board[file-2][rank+1]);
            if (file-2>-1 && rank-1>-1 && this->board[file-2][rank-1].CheckOccupied()==false)
                legalMoves.push_back(this->board[file-2][rank-1]);
            if (file+1<8 && rank+2<8 && this->board[file+1][rank+2].CheckOccupied()==false)
                legalMoves.push_back(this->board[file+1][rank+2]);
            if (file+1<8 && rank-2>-1 && this->board[file+1][rank-2].CheckOccupied()==false)
                legalMoves.push_back(this->board[file+1][rank-2]);
            if (file-1>-1 && rank+2<8 && this->board[file-1][rank+2].CheckOccupied()==false)
                legalMoves.push_back(this->board[file-1][rank+2]);
            if (file-1>-1 && rank-2>-1 && this->board[file-1][rank-2].CheckOccupied()==false)
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
                else
                    break;
            }
            for (int i = 1; i<8; i++)
            {
                if (file-i>-1 && rank+i<8 && this->board[file-i][rank+i].CheckOccupied()==false) // up left
                    legalMoves.push_back(this->board[file-i][rank+i]);
                else
                    break;
            }
            for (int i = 1; i<8; i++)
            {
                if (file+i<8 && rank-i>-1 && this->board[file+i][rank-i].CheckOccupied()==false) // down right
                    legalMoves.push_back(this->board[file+i][rank-i]);
                else
                    break;
            }
            for (int i = 1; i<8; i++)
            {
                if (file-i>-1 && rank-i>-1 && this->board[file-i][rank-i].CheckOccupied()==false) // down left
                    legalMoves.push_back(this->board[file-i][rank-i]);
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
                else
                    break;
            }
            for (int i = rank-1; i>-1; i--) // down
            {
                if (this->board[file][i].CheckOccupied()==false)
                    legalMoves.push_back(this->board[file][i]);
                else
                    break;
            }
            for (int i = file+1; i<8; i++) // right
            {
                if (this->board[i][rank].CheckOccupied()==false)
                    legalMoves.push_back(this->board[i][rank]);
                else
                    break;
            }
            for (int i = file-1; i>-1; i--) // left
            {
                if (this->board[i][rank].CheckOccupied()==false)
                    legalMoves.push_back(this->board[i][rank]);
                else
                    break;
            }
            for (int i = 1; i<8; i++) 
            {
                if (file+i<8 && rank+i<8 && this->board[file+i][rank+i].CheckOccupied()==false) // up right
                    legalMoves.push_back(this->board[file+i][rank+i]);
                else
                    break;
            }
            for (int i = 1; i<8; i++)
            {
                if (file-i>-1 && rank+i<8 && this->board[file-i][rank+i].CheckOccupied()==false) // up left
                    legalMoves.push_back(this->board[file-i][rank+i]);
                else
                    break;
            }
            for (int i = 1; i<8; i++)
            {
                if (file+i<8 && rank-i>-1 && this->board[file+i][rank-i].CheckOccupied()==false) // down right
                    legalMoves.push_back(this->board[file+i][rank-i]);
                else
                    break;
            }
            for (int i = 1; i<8; i++)
            {
                if (file-i>-1 && rank-i>-1 && this->board[file-i][rank-i].CheckOccupied()==false) // down left
                    legalMoves.push_back(this->board[file-i][rank-i]);
                else
                    break;
            }
            break;
        }
        case KING:
        {
            if (file+1<8 && rank+1<8 && this->board[file+1][rank+1].CheckOccupied()==false) // up right
                legalMoves.push_back(this->board[file+1][rank+1]);
            if (file+1<8 && rank-1>-1 && this->board[file+1][rank-1].CheckOccupied()==false) // down right
                legalMoves.push_back(this->board[file+1][rank-1]);
            if (file-1>-1 && rank+1<8 && this->board[file-1][rank+1].CheckOccupied()==false)  // up left
                legalMoves.push_back(this->board[file-1][rank+1]);
            if (file-1>-1 && rank-1>-1 && this->board[file-1][rank-1].CheckOccupied()==false) // down left
                legalMoves.push_back(this->board[file-1][rank-1]);
            if (file+1<8 && this->board[file+1][rank].CheckOccupied()==false) // right
                legalMoves.push_back(this->board[file+1][rank]);
            if (file-1>-1 && this->board[file-1][rank].CheckOccupied()==false) // left
                legalMoves.push_back(this->board[file-1][rank]);
            if (rank+1<8 && this->board[file][rank+1].CheckOccupied()==false) // up
                legalMoves.push_back(this->board[file][rank+1]);
            if (rank-1>-1 && this->board[file][rank-1].CheckOccupied()==false) // down
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
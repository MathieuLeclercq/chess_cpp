#include "chessboard.hpp"
#include <assert.h>


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
            // std::cout << this->board[j][i].getPiece().getType() << " ";
            std::cout << this->board[j][i].getPiece().getValue() << " ";
        }
        std::cout << std::endl;
    }
}

void Chessboard::print(std::vector<std::vector<Square>> some_board) const
{
    for (int i = 7; i > -1; i--)
    {
        for (int j = 0; j < 8; j++)
        {
            std::cout << some_board[j][i].getPiece().getType() << " ";
        }
        std::cout << std::endl;
    }
}

const std::vector<Move>& Chessboard::getMoveHistory() const
{
    return moveHistory;
}

std::vector<Move>& Chessboard::getMoveHistory()
{
    return moveHistory;
}

const std::vector<std::vector<std::vector<Square>>>& Chessboard::getBoardHistory() const
{
    return boardHistory;
}

std::vector<std::vector<std::vector<Square>>>& Chessboard::getBoardHistory()
{
    return boardHistory;
}


std::vector<Square> Chessboard::getLegalMoves(int file, int rank) const
{

    /**
     * Function to get all legal moves for a piece on a square.
     * This does not check for threats to the king.
     * Thats means that this function can return moves that put the king in check.
     * This is why the method CheckForCheck() is used to check if the king is in check.
    */
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
                if (this->en_passant && rank == 4 && abs(file - this->en_passant_file) == 1) // en passant
                {
                    legalMoves.push_back(this->board[this->en_passant_file][rank + 1]);
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
                if (this->en_passant && rank == 3 && abs(file - this->en_passant_file) == 1) // en passant
                {
                    legalMoves.push_back(this->board[this->en_passant_file][rank - 1]);
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

            // short castle
            if (color == WHITE && this->short_castle_white==true && this->board[5][0].CheckOccupied()==false && this->board[6][0].CheckOccupied()==false)
                legalMoves.push_back(this->board[6][0]);
            if (color == BLACK && this->short_castle_black==true && this->board[5][7].CheckOccupied()==false && this->board[6][7].CheckOccupied()==false)
                legalMoves.push_back(this->board[6][7]);
            // long castle
            if (color == WHITE && this->long_castle_white==true && this->board[1][0].CheckOccupied()==false && this->board[2][0].CheckOccupied()==false && this->board[3][0].CheckOccupied()==false)
                legalMoves.push_back(this->board[2][0]);
            if (color == BLACK && this->long_castle_black==true && this->board[1][7].CheckOccupied()==false && this->board[2][7].CheckOccupied()==false && this->board[3][7].CheckOccupied()==false)
                legalMoves.push_back(this->board[2][7]);
            



            break;
        }

    }
    return legalMoves;

}


bool Chessboard::checkForCheck() const
{
    Color oppositeColor = (this->turn == WHITE) ? BLACK : WHITE;
    // check if king is in check
    for (int i = 0; i<8; i++)
    {
        for (int j = 0; j<8; j++)
        {
            if (this->board[i][j].getPiece().getColor() == oppositeColor)
            {
                std::vector<Square> legalMoves = this->getLegalMoves(i,j);
                for (int k = 0; k<legalMoves.size(); k++)
                {
                    if (legalMoves[k].getPiece().getType() == KING)
                    {
                        return true;
                    }
                }
            }
        }
    }
    return false;
}

bool Chessboard::checkForCheckmate()
{
    Color color = this->turn;

    std::cout.setstate(std::ios_base::failbit);



    // check if king is in checkmate
    for (int i = 0; i<8; i++)
    {
        for (int j = 0; j<8; j++)
        {
            if (this->board[i][j].getPiece().getColor() == color)
            {
                std::vector<Square> legalMoves = this->getLegalMoves(i,j);
                for (int k = 0; k<legalMoves.size(); k++)
                {
                    Chessboard temp = *this;
                    temp.movePiece(i,j,legalMoves[k].getFile(),legalMoves[k].getRank());
                    if (temp.checkForCheck() == false)
                    {
                        std::cout.clear();
                        return false;
                    }
                        
                }

            }
        }
    }
    std::cout.clear();
    checkmate = true;
    return true;
}

void Chessboard::checkEnPassant()
{
    // check if pawn has moved two squares
    Move lastMove = this->moveHistory.back();
    if (lastMove.getPiece().getType() == PAWN && abs(lastMove.getDestSquare().getRank()-lastMove.getOrigSquare().getRank())==2)
    {
        this->en_passant = true;
        this->en_passant_file = lastMove.getDestSquare().getFile();
    }
    else
        this->en_passant = false;
}

void Chessboard::printPly() const
{
    std::cout<< "ply "<<this->boardHistory.size()<<"."<<std::endl;
    this->print();
    std::string color_str = (this->turn == WHITE) ? "White" : "Black";
    std::cout<< color_str<< " to move"<<"\n\n"<<std::endl;
    bool check = this->checkForCheck();
    if (check)
        std::cout<<"Check!"<<std::endl;
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

void Chessboard::setBoard(std::vector<std::vector<Square>> some_board)
{
    
    // for (int i = 0; i<8; i++)
    // {
    //     for (int j = 0; j<8; j++)
    //     {
    //         this->board[i][j].setPiece(some_board[i][j].getPiece());
    //         this->board[i][j].setPosition(i,j);
    //         // assert both boards have the same piece
    //         assert(this->board[i][j].getPiece().getType() == some_board[i][j].getPiece().getType());
    //     }
    // }
    this->board = some_board;
}

void Chessboard::updateHistory(const Square& first_square,const Square& second_square)
{
    this->moveHistory.push_back(Move(first_square, second_square));
    this->boardHistory.push_back(this->board);
}

void Chessboard::updateCastleFlags()
{
    // get last move
    Move lastMove = this->moveHistory.back();
    // check if king or rook moved
    if (lastMove.getPiece().getType() == KING)
    {
        if (lastMove.getPiece().getColor() == WHITE)
        {
            this->short_castle_white = false;
            this->long_castle_white = false;
        }
        else if (lastMove.getPiece().getColor() == BLACK)
        {
            this->short_castle_black = false;
            this->long_castle_black = false;
        }
        else
            std::cout << "Error: invalid move" << std::endl;
    }
    else if (lastMove.getPiece().getType() == ROOK)
    {
        if (lastMove.getPiece().getColor() == WHITE)
        {
            if (lastMove.getOrigSquare().getFile() == 0)
                this->long_castle_white = false;
            else if (lastMove.getOrigSquare().getFile() == 7)
                this->short_castle_white = false;
        }
        else if (lastMove.getPiece().getColor() == BLACK)
        {
            if (lastMove.getOrigSquare().getFile() == 0)
                this->long_castle_black = false;
            else if (lastMove.getOrigSquare().getFile() == 7)
                this->short_castle_black = false;
        }
        else
            std::cout << "Error: invalid move" << std::endl;
    }
    // std::map<Piece,std::array<Square,2>> lastMove = this->moveHistory.back();
    // // get size of last move
    // int size = moveHistory.size();
    // std::cout<<"size of move history: "<<size<<std::endl;
}

void Chessboard::checkPromotion(Square& second_square, PieceType force_promotion)
{
    // check if pawn reached end of board
    // if so, ask user what piece to promote to
    // update piece

    PieceType type_piece = second_square.getPiece().getType();
    Color color_piece = second_square.getPiece().getColor();

    // cas 1 : force promotion. pas besoin de check 
    if (force_promotion != NONE)
    {
        second_square.setPiece(Piece(color_piece, force_promotion));
        return;

    }

    int rank = second_square.getRank();
    if (type_piece == PAWN)
    {
        if (rank == 0 || rank == 7)
        {


            // cas 2 : l'utilisateur rentre le truc

            std::cout << "Pawn reached end of board. What piece would you like to promote to?" << std::endl;
            std::cout << "1. Queen" << std::endl;
            std::cout << "2. Rook" << std::endl;
            std::cout << "3. Bishop" << std::endl;
            std::cout << "4. Knight" << std::endl;
            int choice;
            std::cin >> choice;
            switch (choice)
            {
            case 1:
                second_square.setPiece(Piece(color_piece, QUEEN));
                break;
            case 2:
                second_square.setPiece(Piece(color_piece, ROOK));
                break;
            case 3:
                second_square.setPiece(Piece(color_piece, BISHOP));
                break;
            case 4:
                second_square.setPiece(Piece(color_piece, KNIGHT));
                break;
            default:
                std::cout << "Invalid choice. Defaulting to Queen." << std::endl;
                second_square.setPiece(Piece(second_square.getPiece().getColor(), QUEEN));
                break;
            }
        }
    }
    

}

bool Chessboard::movePiece(int orig_file,int orig_rank, int file, int rank, PieceType promotion)
{
    Square& first_square = this->board[orig_file][orig_rank];
    Square& second_square = this->board[file][rank];
    const std::vector<Square> legalMoves = this->getLegalMoves(orig_file, orig_rank);

    if (first_square.getPiece().getColor() != this ->turn) // check turn
    {
        std::cout<<"It is not your turn!"<<std::endl;
        return false;
    }


    if (std::find(legalMoves.begin(), legalMoves.end(), second_square) != legalMoves.end()) // naive legal move check
    {
        // copy of the board
        std::vector<std::vector<Square>> board_copy = this->board;
        
        if (first_square.getPiece().getType() == KING && abs(orig_file-file) == 2) // castling
        {
            if (file == 6) // kingside
                this->board[orig_file+1][rank].setPiece(first_square.getPiece());
            else if (file == 2) // queenside
                this->board[orig_file-1][rank].setPiece(first_square.getPiece());
            else
            {
                std::cout << "Invalid castling move!" << std::endl; // should never happen
                return false;
            }
                

            if (this->checkForCheck())
                {
                    std::cout<<"You cannot castle: there are threats on the way."<<std::endl;
                    this->setBoard(board_copy);
                    return false;
                }
            if (file == 6)
            {
                this->board[5][rank].setPiece(Piece(this->turn,ROOK)); // move rook
                this->board[7][rank].setPiece(Piece());
            }

            else if (file == 2)
            {
                // move rook
                this->board[3][rank].setPiece(Piece(first_square.getPiece().getColor(),ROOK));
                this->board[0][rank].setPiece(Piece());
            }

        }

        if (second_square.getPiece().getType() == NONE && first_square.getPiece().getType() == PAWN && abs(orig_file-file) == 1) // en passant
        {
            this->board[file][orig_rank].setPiece(Piece());

        }
        second_square.setPiece(first_square.getPiece()); // move piece
        first_square.setPiece(Piece()); // empty square where piece was



        if (this->checkForCheck()) // handles pins and checks
        {
            std::cout<<"Illegal move: your king is checked"<<std::endl;    
            std::cout<<"-------------------------"<<std::endl;
            this->print();
            std::cout<<"-------------------------"<<std::endl;  
            this->setBoard(board_copy); // put board back to original state
            return false;
        }

        this->checkPromotion(second_square); // check if pawn promotion is needed
        this->updateHistory(first_square, second_square);
        this->turn = (this->turn == WHITE) ? BLACK : WHITE;
        this->printPly();
        if (this->checkForCheck())
        {
            if (this->checkForCheckmate())
                std::cout<<"Checkmate!"<<std::endl;
        }


        
        this->updateCastleFlags();
        this->checkEnPassant();
        
        return true;
    }

    else
    {
        std::cout << "Illegal move" << std::endl;
        return false;
        // std::cout<<"-------------------------"<<std::endl;
        // this->print();
        // std::cout<<"-------------------------"<<std::endl;  
    }
}

bool Chessboard::movePiece(std::string orig_square, std::string square)
{
    // find index of orig_square
    int orig_file = std::find(files.begin(), files.end(), orig_square[0]) - files.begin();
    int orig_rank = std::find(ranks.begin(), ranks.end(), orig_square[1]) - ranks.begin();

    // find index of squares
    int file = std::find(files.begin(), files.end(), square[0]) - files.begin();
    int rank = std::find(ranks.begin(), ranks.end(), square[1]) - ranks.begin();
    // std::cout<<"orig_file: " << orig_file << " orig_rank: " << orig_rank << " file: " << file << " rank: " << rank << std::endl;
    return this->movePiece(orig_file, orig_rank, file, rank);
}

bool Chessboard::movePieceSAN(std::string san)
{
    // 1. Nettoyage
    san.erase(std::remove(san.begin(), san.end(), '+'), san.end());
    san.erase(std::remove(san.begin(), san.end(), '#'), san.end());
    san.erase(std::remove(san.begin(), san.end(), '!'), san.end());
    san.erase(std::remove(san.begin(), san.end(), '?'), san.end());

    // 2. Traitement immédiat des Roques
    if (san == "O-O" || san == "O-O-O")
    {
        int rank = (this->turn == WHITE) ? 0 : 7;
        int orig_file = 4; // Colonne e
        int dest_file = (san == "O-O") ? 6 : 2; // Colonne g (petit roque) ou c (grand roque)

        
        return this->movePiece(orig_file, rank, dest_file, rank);;
    }

    // 3. Détection et extraction de la Promotion
    PieceType promotion_type = NONE;
    size_t equal_pos = san.find('=');
    if (equal_pos != std::string::npos)
    {
        char p = san.back();
        if (p == 'Q') promotion_type = QUEEN;
        else if (p == 'R') promotion_type = ROOK;
        else if (p == 'B') promotion_type = BISHOP;
        else if (p == 'N') promotion_type = KNIGHT;

        san = san.substr(0, equal_pos); // On coupe la partie "=Q"
    }

    // Sécurité anti-crash
    if (san.length() < 2) return false;

    // 4. Identification de la case de destination
    char dest_f_char = san[san.length() - 2];
    char dest_r_char = san[san.length() - 1];
    int dest_file = dest_f_char - 'a';
    int dest_rank = dest_r_char - '1';
    san = san.substr(0, san.length() - 2); // On retire la destination

    // 5. Déduction du type de pièce et gestion de la capture
    PieceType p_type = PAWN;
    if (!san.empty() && isupper(san[0])) // isupper nécessite <cctype> mais souvent inclus via <iostream>
    {
        char p = san[0];
        if (p == 'K') p_type = KING;
        else if (p == 'Q') p_type = QUEEN;
        else if (p == 'R') p_type = ROOK;
        else if (p == 'B') p_type = BISHOP;
        else if (p == 'N') p_type = KNIGHT;
        san = san.substr(1); // On retire la lettre de la pièce
    }

    if (!san.empty() && san.back() == 'x')
    {
        san.pop_back(); // On retire le 'x' de la prise
    }

    // 6. Extraction des indices de désambiguïsation
    int orig_file_hint = -1;
    int orig_rank_hint = -1;
    for (char c : san)
    {
        if (c >= 'a' && c <= 'h') orig_file_hint = c - 'a';
        if (c >= '1' && c <= '8') orig_rank_hint = c - '1';
    }

    // 7. Résolution via le moteur
    int final_orig_file = -1;
    int final_orig_rank = -1;
    int match_count = 0;

    for (int i = 0; i < 8; i++)
    {
        for (int j = 0; j < 8; j++)
        {
            const Square& sq = this->board[i][j];
            if (sq.CheckOccupied() && sq.getPiece().getColor() == this->turn && sq.getPiece().getType() == p_type)
            {
                // Application des filtres de désambiguïsation
                if (orig_file_hint != -1 && i != orig_file_hint) continue;
                if (orig_rank_hint != -1 && j != orig_rank_hint) continue;

                // Vérification des mouvements légaux
                std::vector<Square> legal_moves = this->getLegalMoves(i, j);
                for (const Square& m : legal_moves)
                {
                    if (m.getFile() == dest_file && m.getRank() == dest_rank)
                    {
                        final_orig_file = i;
                        final_orig_rank = j;
                        match_count++;
                        break;
                    }
                }
            }
        }
    }

    // 8. Exécution
    if (match_count == 1)
    {
        return this->movePiece(final_orig_file, final_orig_rank, dest_file, dest_rank);

        // TODO: Gérer l'application de 'promotion_type' ici si la pièce était un pion
    }
    else
    {
        std::cerr << "Erreur SAN : " << match_count << " origines trouvées pour le coup " << san << std::endl;
        return false;
    }
}

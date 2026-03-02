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
    return board[rank * 8 + file];
}

Square& Chessboard::getSquare(int file, int rank)
{
    return board[rank * 8 + file];
}

int Chessboard::getNumberOfOccupiedSquares() const
{
    int count = 0;
    for (int i = 0; i < 8; i++)
    {
        for (int j = 0; j < 8; j++)
        {
            // i = rank, j = file pour rester cohérent, ou l'inverse, l'essentiel est de balayer les 64 cases
            if (board[i * 8 + j].CheckOccupied())
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
            // i = rank, j = file
            std::cout << this->board[i * 8 + j].getPiece().getValue() << " ";
        }
        std::cout << std::endl;
    }
}

void Chessboard::print(std::array<Square, 64> some_board) const
{
    for (int i = 7; i > -1; i--)
    {
        for (int j = 0; j < 8; j++)
        {
            std::cout << some_board[i * 8 + j].getPiece().getType() << " ";
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

const std::vector<std::array<Square, 64>>& Chessboard::getBoardHistory() const
{
    return boardHistory;
}

std::vector<std::array<Square, 64>>& Chessboard::getBoardHistory()
{
    return boardHistory;
}

Color Chessboard::getTurn() const
{
    return this->turn;
}

GameState Chessboard::getGameState() const
{
    return this->current_state;
}

std::vector<Move> Chessboard::getLegalMoves(int file, int rank) const
{
    Square orig_square = board[rank * 8 + file];
    std::vector<Move> legalMoves;
    PieceType type = orig_square.getPiece().getType();
    Color color = orig_square.getPiece().getColor();

    Color oppositeColor = (color == WHITE) ? BLACK : WHITE;

    // Fonction lambda pour gérer automatiquement les sous-promotions
    auto addMove = [&](const Square& target_square) {
        if (type == PAWN && (target_square.getRank() == 0 || target_square.getRank() == 7))
        {
            legalMoves.push_back(Move(orig_square, target_square, QUEEN));
            legalMoves.push_back(Move(orig_square, target_square, ROOK));
            legalMoves.push_back(Move(orig_square, target_square, BISHOP));
            legalMoves.push_back(Move(orig_square, target_square, KNIGHT));
        }
        else
        {
            legalMoves.push_back(Move(orig_square, target_square, NONE));
        }
    };

    switch (type)
    {
    case PAWN:
    {
        if (color == WHITE && rank < 7 && this->board[(rank + 1) * 8 + file].CheckOccupied() == false)
        {
            addMove(this->board[(rank + 1) * 8 + file]);
            if (rank == 1 && this->board[(rank + 2) * 8 + file].CheckOccupied() == false)
            {
                addMove(this->board[(rank + 2) * 8 + file]);
            }
        }
        else if (color == BLACK && rank > 0 && this->board[(rank - 1) * 8 + file].CheckOccupied() == false)
        {
            addMove(this->board[(rank - 1) * 8 + file]);
            if (rank == 6 && this->board[(rank - 2) * 8 + file].CheckOccupied() == false)
            {
                addMove(this->board[(rank - 2) * 8 + file]);
            }
        }

        if (color == WHITE && rank < 7)
        {
            if (file < 7 && this->board[(rank + 1) * 8 + (file + 1)].getPiece().getColor() == oppositeColor)
            {
                addMove(this->board[(rank + 1) * 8 + (file + 1)]);
            }
            if (file > 0 && this->board[(rank + 1) * 8 + (file - 1)].getPiece().getColor() == oppositeColor)
            {
                addMove(this->board[(rank + 1) * 8 + (file - 1)]);
            }
            if (this->en_passant && rank == 4 && abs(file - this->en_passant_file) == 1)
            {
                addMove(this->board[(rank + 1) * 8 + this->en_passant_file]);
            }
        }
        else if (color == BLACK && rank > 0)
        {
            if (file < 7 && this->board[(rank - 1) * 8 + (file + 1)].getPiece().getColor() == oppositeColor)
            {
                addMove(this->board[(rank - 1) * 8 + (file + 1)]);
            }
            if (file > 0 && this->board[(rank - 1) * 8 + (file - 1)].getPiece().getColor() == oppositeColor)
            {
                addMove(this->board[(rank - 1) * 8 + (file - 1)]);
            }
            if (this->en_passant && rank == 3 && abs(file - this->en_passant_file) == 1)
            {
                addMove(this->board[(rank - 1) * 8 + this->en_passant_file]);
            }
        }
        break;
    }
    case ROOK:
    {
        for (int i = rank + 1; i < 8; i++) // top
        {
            if (this->board[i * 8 + file].CheckOccupied() == false)
                addMove(this->board[i * 8 + file]);
            else if (this->board[i * 8 + file].getPiece().getColor() == oppositeColor)
            {
                addMove(this->board[i * 8 + file]);
                break;
            }
            else break;
        }
        for (int i = rank - 1; i > -1; i--) // bottom
        {
            if (this->board[i * 8 + file].CheckOccupied() == false)
                addMove(this->board[i * 8 + file]);
            else if (this->board[i * 8 + file].getPiece().getColor() == oppositeColor)
            {
                addMove(this->board[i * 8 + file]);
                break;
            }
            else break;
        }
        for (int i = file + 1; i < 8; i++) // right
        {
            if (this->board[rank * 8 + i].CheckOccupied() == false)
                addMove(this->board[rank * 8 + i]);
            else if (this->board[rank * 8 + i].getPiece().getColor() == oppositeColor)
            {
                addMove(this->board[rank * 8 + i]);
                break;
            }
            else break;
        }
        for (int i = file - 1; i > -1; i--) // left
        {
            if (this->board[rank * 8 + i].CheckOccupied() == false)
                addMove(this->board[rank * 8 + i]);
            else if (this->board[rank * 8 + i].getPiece().getColor() == oppositeColor)
            {
                addMove(this->board[rank * 8 + i]);
                break;
            }
            else break;
        }
        break;
    }
    case KNIGHT:
    {
        if (file + 2 < 8 && rank + 1 < 8 && this->board[(rank + 1) * 8 + (file + 2)].getPiece().getColor() != color)
            addMove(this->board[(rank + 1) * 8 + (file + 2)]);
        if (file + 2 < 8 && rank - 1 > -1 && this->board[(rank - 1) * 8 + (file + 2)].getPiece().getColor() != color)
            addMove(this->board[(rank - 1) * 8 + (file + 2)]);
        if (file - 2 > -1 && rank + 1 < 8 && this->board[(rank + 1) * 8 + (file - 2)].getPiece().getColor() != color)
            addMove(this->board[(rank + 1) * 8 + (file - 2)]);
        if (file - 2 > -1 && rank - 1 > -1 && this->board[(rank - 1) * 8 + (file - 2)].getPiece().getColor() != color)
            addMove(this->board[(rank - 1) * 8 + (file - 2)]);
        if (file + 1 < 8 && rank + 2 < 8 && this->board[(rank + 2) * 8 + (file + 1)].getPiece().getColor() != color)
            addMove(this->board[(rank + 2) * 8 + (file + 1)]);
        if (file + 1 < 8 && rank - 2 > -1 && this->board[(rank - 2) * 8 + (file + 1)].getPiece().getColor() != color)
            addMove(this->board[(rank - 2) * 8 + (file + 1)]);
        if (file - 1 > -1 && rank + 2 < 8 && this->board[(rank + 2) * 8 + (file - 1)].getPiece().getColor() != color)
            addMove(this->board[(rank + 2) * 8 + (file - 1)]);
        if (file - 1 > -1 && rank - 2 > -1 && this->board[(rank - 2) * 8 + (file - 1)].getPiece().getColor() != color)
            addMove(this->board[(rank - 2) * 8 + (file - 1)]);
        break;
    }
    case BISHOP:
    {
        for (int i = 1; i < 8; i++) // up right
        {
            if (file + i < 8 && rank + i < 8 && this->board[(rank + i) * 8 + (file + i)].CheckOccupied() == false)
                addMove(this->board[(rank + i) * 8 + (file + i)]);
            else if (file + i < 8 && rank + i < 8 && this->board[(rank + i) * 8 + (file + i)].getPiece().getColor() == oppositeColor)
            {
                addMove(this->board[(rank + i) * 8 + (file + i)]);
                break;
            }
            else break;
        }
        for (int i = 1; i < 8; i++) // up left
        {
            if (file - i > -1 && rank + i < 8 && this->board[(rank + i) * 8 + (file - i)].CheckOccupied() == false)
                addMove(this->board[(rank + i) * 8 + (file - i)]);
            else if (file - i > -1 && rank + i < 8 && this->board[(rank + i) * 8 + (file - i)].getPiece().getColor() == oppositeColor)
            {
                addMove(this->board[(rank + i) * 8 + (file - i)]);
                break;
            }
            else break;
        }
        for (int i = 1; i < 8; i++) // down right
        {
            if (file + i < 8 && rank - i > -1 && this->board[(rank - i) * 8 + (file + i)].CheckOccupied() == false)
                addMove(this->board[(rank - i) * 8 + (file + i)]);
            else if (file + i < 8 && rank - i > -1 && this->board[(rank - i) * 8 + (file + i)].getPiece().getColor() == oppositeColor)
            {
                addMove(this->board[(rank - i) * 8 + (file + i)]);
                break;
            }
            else break;
        }
        for (int i = 1; i < 8; i++) // down left
        {
            if (file - i > -1 && rank - i > -1 && this->board[(rank - i) * 8 + (file - i)].CheckOccupied() == false)
                addMove(this->board[(rank - i) * 8 + (file - i)]);
            else if (file - i > -1 && rank - i > -1 && this->board[(rank - i) * 8 + (file - i)].getPiece().getColor() == oppositeColor)
            {
                addMove(this->board[(rank - i) * 8 + (file - i)]);
                break;
            }
            else break;
        }
        break;
    }
    case QUEEN:
    {
        // Combinaison des logiques ROOK et BISHOP
        for (int i = rank + 1; i < 8; i++)  // up
        {
            if (this->board[i * 8 + file].CheckOccupied() == false)
                addMove(this->board[i * 8 + file]);
            else if (this->board[i * 8 + file].getPiece().getColor() == oppositeColor)
            {
                addMove(this->board[i * 8 + file]);
                break;
            }
            else break;
        }
        for (int i = rank - 1; i > -1; i--) // down
        {
            if (this->board[i * 8 + file].CheckOccupied() == false)
                addMove(this->board[i * 8 + file]);
            else if (this->board[i * 8 + file].getPiece().getColor() == oppositeColor)
            {
                addMove(this->board[i * 8 + file]);
                break;
            }
            else break;
        }
        for (int i = file + 1; i < 8; i++) // right
        {
            if (this->board[rank * 8 + i].CheckOccupied() == false)
                addMove(this->board[rank * 8 + i]);
            else if (this->board[rank * 8 + i].getPiece().getColor() == oppositeColor)
            {
                addMove(this->board[rank * 8 + i]);
                break;
            }
            else break;
        }
        for (int i = file - 1; i > -1; i--) // left
        {
            if (this->board[rank * 8 + i].CheckOccupied() == false)
                addMove(this->board[rank * 8 + i]);
            else if (this->board[rank * 8 + i].getPiece().getColor() == oppositeColor)
            {
                addMove(this->board[rank * 8 + i]);
                break;
            }
            else break;
        }
        for (int i = 1; i < 8; i++) // up right
        {
            if (file + i < 8 && rank + i < 8 && this->board[(rank + i) * 8 + (file + i)].CheckOccupied() == false)
                addMove(this->board[(rank + i) * 8 + (file + i)]);
            else if (file + i < 8 && rank + i < 8 && this->board[(rank + i) * 8 + (file + i)].getPiece().getColor() == oppositeColor)
            {
                addMove(this->board[(rank + i) * 8 + (file + i)]);
                break;
            }
            else break;
        }
        for (int i = 1; i < 8; i++) // up left
        {
            if (file - i > -1 && rank + i < 8 && this->board[(rank + i) * 8 + (file - i)].CheckOccupied() == false)
                addMove(this->board[(rank + i) * 8 + (file - i)]);
            else if (file - i > -1 && rank + i < 8 && this->board[(rank + i) * 8 + (file - i)].getPiece().getColor() == oppositeColor)
            {
                addMove(this->board[(rank + i) * 8 + (file - i)]);
                break;
            }
            else break;
        }
        for (int i = 1; i < 8; i++) // down right
        {
            if (file + i < 8 && rank - i > -1 && this->board[(rank - i) * 8 + (file + i)].CheckOccupied() == false)
                addMove(this->board[(rank - i) * 8 + (file + i)]);
            else if (file + i < 8 && rank - i > -1 && this->board[(rank - i) * 8 + (file + i)].getPiece().getColor() == oppositeColor)
            {
                addMove(this->board[(rank - i) * 8 + (file + i)]);
                break;
            }
            else break;
        }
        for (int i = 1; i < 8; i++) // down left
        {
            if (file - i > -1 && rank - i > -1 && this->board[(rank - i) * 8 + (file - i)].CheckOccupied() == false)
                addMove(this->board[(rank - i) * 8 + (file - i)]);
            else if (file - i > -1 && rank - i > -1 && this->board[(rank - i) * 8 + (file - i)].getPiece().getColor() == oppositeColor)
            {
                addMove(this->board[(rank - i) * 8 + (file - i)]);
                break;
            }
            else break;
        }
        break;
    }
    case KING:
    {
        if (file + 1 < 8 && rank + 1 < 8 && this->board[(rank + 1) * 8 + (file + 1)].getPiece().getColor() != color)
            addMove(this->board[(rank + 1) * 8 + (file + 1)]);
        if (file + 1 < 8 && rank - 1 > -1 && this->board[(rank - 1) * 8 + (file + 1)].getPiece().getColor() != color)
            addMove(this->board[(rank - 1) * 8 + (file + 1)]);
        if (file - 1 > -1 && rank + 1 < 8 && this->board[(rank + 1) * 8 + (file - 1)].getPiece().getColor() != color)
            addMove(this->board[(rank + 1) * 8 + (file - 1)]);
        if (file - 1 > -1 && rank - 1 > -1 && this->board[(rank - 1) * 8 + (file - 1)].getPiece().getColor() != color)
            addMove(this->board[(rank - 1) * 8 + (file - 1)]);
        if (file + 1 < 8 && this->board[rank * 8 + (file + 1)].getPiece().getColor() != color)
            addMove(this->board[rank * 8 + (file + 1)]);
        if (file - 1 > -1 && this->board[rank * 8 + (file - 1)].getPiece().getColor() != color)
            addMove(this->board[rank * 8 + (file - 1)]);
        if (rank + 1 < 8 && this->board[(rank + 1) * 8 + file].getPiece().getColor() != color)
            addMove(this->board[(rank + 1) * 8 + file]);
        if (rank - 1 > -1 && this->board[(rank - 1) * 8 + file].getPiece().getColor() != color)
            addMove(this->board[(rank - 1) * 8 + file]);

        // short castle
        if (color == WHITE && this->short_castle_white == true && this->board[0 * 8 + 5].CheckOccupied() == false && this->board[0 * 8 + 6].CheckOccupied() == false)
            addMove(this->board[0 * 8 + 6]);
        if (color == BLACK && this->short_castle_black == true && this->board[7 * 8 + 5].CheckOccupied() == false && this->board[7 * 8 + 6].CheckOccupied() == false)
            addMove(this->board[7 * 8 + 6]);
        // long castle
        if (color == WHITE && this->long_castle_white == true && this->board[0 * 8 + 1].CheckOccupied() == false && this->board[0 * 8 + 2].CheckOccupied() == false && this->board[0 * 8 + 3].CheckOccupied() == false)
            addMove(this->board[0 * 8 + 2]);
        if (color == BLACK && this->long_castle_black == true && this->board[7 * 8 + 1].CheckOccupied() == false && this->board[7 * 8 + 2].CheckOccupied() == false && this->board[7 * 8 + 3].CheckOccupied() == false)
            addMove(this->board[7 * 8 + 2]);
        break;
    }
    }
    return legalMoves;
}

bool Chessboard::isInCheck() const
{
    Color color = this->turn;
    Color oppositeColor = (color == WHITE) ? BLACK : WHITE;

    // 1. Récupérer les coordonnées de notre roi
    int king_file = (color == WHITE) ? this->white_king_file : this->black_king_file;
    int king_rank = (color == WHITE) ? this->white_king_rank : this->black_king_rank;

    // 2. Vérifier les menaces de Cavaliers
    static constexpr int knight_moves[8][2] = { {1, 2}, {2, 1}, {2, -1}, {1, -2}, {-1, -2}, {-2, -1}, {-2, 1}, {-1, 2} };
    for (int i = 0; i < 8; i++)
    {
        int r = king_rank + knight_moves[i][0];
        int f = king_file + knight_moves[i][1];
        if (r >= 0 && r < 8 && f >= 0 && f < 8)
        {
            const Piece& p = this->board[r * 8 + f].getPiece();
            if (p.getType() == KNIGHT && p.getColor() == oppositeColor)
                return true;
        }
    }

    // 3. Vérifier les menaces de Pions
    int pawn_direction = (color == WHITE) ? 1 : -1;
    int pr = king_rank + pawn_direction;
    if (pr >= 0 && pr < 8)
    {
        if (king_file - 1 >= 0)
        {
            const Piece& p = this->board[pr * 8 + (king_file - 1)].getPiece();
            if (p.getType() == PAWN && p.getColor() == oppositeColor) return true;
        }
        if (king_file + 1 < 8)
        {
            const Piece& p = this->board[pr * 8 + (king_file + 1)].getPiece();
            if (p.getType() == PAWN && p.getColor() == oppositeColor) return true;
        }
    }

    // 4. Vérifier les menaces Lignes/Colonnes
    static constexpr int orth_dirs[4][2] = { {1, 0}, {-1, 0}, {0, 1}, {0, -1} };
    for (int d = 0; d < 4; d++)
    {
        for (int i = 1; i < 8; i++)
        {
            int r = king_rank + orth_dirs[d][0] * i;
            int f = king_file + orth_dirs[d][1] * i;
            if (r < 0 || r >= 8 || f < 0 || f >= 8) break;

            const Piece& p = this->board[r * 8 + f].getPiece();
            if (p.getType() != NONE)
            {
                if (p.getColor() == oppositeColor && (p.getType() == ROOK || p.getType() == QUEEN))
                    return true;
                break;
            }
        }
    }

    // 5. Vérifier les menaces Diagonales
    static constexpr int diag_dirs[4][2] = { {1, 1}, {1, -1}, {-1, -1}, {-1, 1} };
    for (int d = 0; d < 4; d++)
    {
        for (int i = 1; i < 8; i++)
        {
            int r = king_rank + diag_dirs[d][0] * i;
            int f = king_file + diag_dirs[d][1] * i;
            if (r < 0 || r >= 8 || f < 0 || f >= 8) break;

            const Piece& p = this->board[r * 8 + f].getPiece();
            if (p.getType() != NONE)
            {
                if (p.getColor() == oppositeColor && (p.getType() == BISHOP || p.getType() == QUEEN))
                    return true;
                break;
            }
        }
    }

    // 6. Vérifier le Roi adverse (pas besoin normalement)
    static constexpr int king_moves[8][2] = { {1, 0}, {1, 1}, {0, 1}, {-1, 1}, {-1, 0}, {-1, -1}, {0, -1}, {1, -1} };
    for (int i = 0; i < 8; i++)
    {
        int r = king_rank + king_moves[i][0];
        int f = king_file + king_moves[i][1];
        if (r >= 0 && r < 8 && f >= 0 && f < 8)
        {
            const Piece& p = this->board[r * 8 + f].getPiece();
            if (p.getType() == KING && p.getColor() == oppositeColor)
                return true;
        }
    }

    return false;
}


bool Chessboard::hasAnyLegalMove()
{
    Color color = this->turn;

    for (int i = 0; i < 8; i++) // i = file
    {
        for (int j = 0; j < 8; j++) // j = rank
        {
            if (this->board[j * 8 + i].getPiece().getColor() == color)
            {
                std::vector<Move> legalMoves = this->getLegalMoves(i, j);
                for (int k = 0; k < legalMoves.size(); k++)
                {
                    int dest_file = legalMoves[k].getDestSquare().getFile();
                    int dest_rank = legalMoves[k].getDestSquare().getRank();

                    bool is_king_move = (this->board[j * 8 + i].getPiece().getType() == KING);
                    if (is_king_move) {
                        if (color == WHITE) { this->white_king_file = dest_file; this->white_king_rank = dest_rank; }
                        else { this->black_king_file = dest_file; this->black_king_rank = dest_rank; }
                    }

                    std::array<Square, 64> board_copy = this->board;

                    // Gestion du pion capturé en passant lors de la simulation
                    bool is_en_passant = (this->board[j * 8 + i].getPiece().getType() == PAWN &&
                        abs(i - dest_file) == 1 &&
                        this->board[dest_rank * 8 + dest_file].getPiece().getType() == NONE);

                    if (is_en_passant) {
                        this->board[j * 8 + dest_file].setPiece(Piece());
                    }

                    this->board[dest_rank * 8 + dest_file].setPiece(this->board[j * 8 + i].getPiece());
                    this->board[j * 8 + i].setPiece(Piece());

                    bool still_in_check = this->isInCheck();

                    this->board = board_copy;

                    if (is_king_move) {
                        if (color == WHITE) { this->white_king_file = i; this->white_king_rank = j; }
                        else { this->black_king_file = i; this->black_king_rank = j; }
                    }

                    if (!still_in_check)
                    {
                        return true;
                    }
                }
            }
        }
    }

    this->current_state = CHECKMATE;
    return false;
}

void Chessboard::checkEnPassant()
{
    Move lastMove = this->moveHistory.back();
    if (lastMove.getPiece().getType() == PAWN && abs(lastMove.getDestSquare().getRank() - lastMove.getOrigSquare().getRank()) == 2)
    {
        this->en_passant = true;
        this->en_passant_file = lastMove.getDestSquare().getFile();
    }
    else
        this->en_passant = false;
}

void Chessboard::printPly() const
{
    std::cout << "ply " << this->boardHistory.size() << "." << std::endl;
    this->print();
    std::string color_str = (this->turn == WHITE) ? "White" : "Black";
    std::cout << color_str << " to move" << "\n\n" << std::endl;
    bool check = this->isInCheck();
    if (check)
        std::cout << "Check!" << std::endl;
}

//...............Setters...............

void Chessboard::Clear()
{
    this->board = std::array<Square, 64>();
    for (int i = 0; i < 8; i++) // i = file
    {
        for (int j = 0; j < 8; j++) // j = rank
        {
            this->board[j * 8 + i].setPosition(i, j);
        }
    }
    this->current_state = ONGOING;
}

void Chessboard::setStartupPieces()
{
    this->white_king_file = 4;
    this->white_king_rank = 0;
    this->black_king_file = 4;
    this->black_king_rank = 7;

    for (int i = 0; i < 8; i++) // i = file index
    {
        for (int j = 0; j < 8; j++) // j = rank index
        {
            int file = i + 1;
            int rank = j + 1;

            // pawns
            if (rank == 2)
            {
                board[j * 8 + i].setPiece(Piece(WHITE, PAWN));
            }
            else if (rank == 7)
            {
                board[j * 8 + i].setPiece(Piece(BLACK, PAWN));
            }
            // rooks
            else if (rank == 1 && (file == 1 || file == 8))
            {
                board[j * 8 + i].setPiece(Piece(WHITE, ROOK));
            }
            else if (rank == 8 && (file == 1 || file == 8))
            {
                board[j * 8 + i].setPiece(Piece(BLACK, ROOK));
            }
            // knights
            else if (rank == 1 && (file == 2 || file == 7))
            {
                board[j * 8 + i].setPiece(Piece(WHITE, KNIGHT));
            }
            else if (rank == 8 && (file == 2 || file == 7))
            {
                board[j * 8 + i].setPiece(Piece(BLACK, KNIGHT));
            }
            // bishops
            else if (rank == 1 && (file == 3 || file == 6))
            {
                board[j * 8 + i].setPiece(Piece(WHITE, BISHOP));
            }
            else if (rank == 8 && (file == 3 || file == 6))
            {
                board[j * 8 + i].setPiece(Piece(BLACK, BISHOP));
            }
            // queen
            else if (rank == 1 && file == 4)
            {
                board[j * 8 + i].setPiece(Piece(WHITE, QUEEN));
            }
            else if (rank == 8 && file == 4)
            {
                board[j * 8 + i].setPiece(Piece(BLACK, QUEEN));
            }
            // king
            else if (rank == 1 && file == 5)
            {
                board[j * 8 + i].setPiece(Piece(WHITE, KING));
            }
            else if (rank == 8 && file == 5)
            {
                board[j * 8 + i].setPiece(Piece(BLACK, KING));
            }
            // empty squares
            else
            {
                board[j * 8 + i].setPiece(Piece());
            }
        }
    }
}

void Chessboard::setBoard(std::array<Square, 64> some_board)
{
    this->board = some_board;
}

void Chessboard::updateHistory(const Square& first_square, const Square& second_square)
{
    this->moveHistory.push_back(Move(first_square, second_square));
    this->boardHistory.push_back(this->board);
}

//void Chessboard::updateCastleFlags()
//{
//    Move lastMove = this->moveHistory.back();
//    if (lastMove.getPiece().getType() == KING)
//    {
//        if (lastMove.getPiece().getColor() == WHITE)
//        {
//            this->short_castle_white = false;
//            this->long_castle_white = false;
//        }
//        else if (lastMove.getPiece().getColor() == BLACK)
//        {
//            this->short_castle_black = false;
//            this->long_castle_black = false;
//        }
//    }
//    else if (lastMove.getPiece().getType() == ROOK)
//    {
//        if (lastMove.getPiece().getColor() == WHITE)
//        {
//            if (lastMove.getOrigSquare().getFile() == 0)
//                this->long_castle_white = false;
//            else if (lastMove.getOrigSquare().getFile() == 7)
//                this->short_castle_white = false;
//        }
//        else if (lastMove.getPiece().getColor() == BLACK)
//        {
//            if (lastMove.getOrigSquare().getFile() == 0)
//                this->long_castle_black = false;
//            else if (lastMove.getOrigSquare().getFile() == 7)
//                this->short_castle_black = false;
//        }
//    }
//}


void Chessboard::updateCastleFlags()
{
    // 3 cas à gérer : 
    // roi a bougé
    // tour a bougé
    // tour capturée (sans forcément avoir bougé avant)
    Move lastMove = this->moveHistory.back();

    // 1. Perte des deux droits si le roi bouge
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
    }

    // 2. Perte d'un droit spécifique si une case de tour est impliquée (départ ou arrivée)
    int orig_f = lastMove.getOrigSquare().getFile();
    int orig_r = lastMove.getOrigSquare().getRank();
    int dest_f = lastMove.getDestSquare().getFile();
    int dest_r = lastMove.getDestSquare().getRank();

    // Tour blanche a1 (Grand roque blanc)
    if ((orig_f == 0 && orig_r == 0) || (dest_f == 0 && dest_r == 0))
        this->long_castle_white = false;

    // Tour blanche h1 (Petit roque blanc)
    if ((orig_f == 7 && orig_r == 0) || (dest_f == 7 && dest_r == 0))
        this->short_castle_white = false;

    // Tour noire a8 (Grand roque noir)
    if ((orig_f == 0 && orig_r == 7) || (dest_f == 0 && dest_r == 7))
        this->long_castle_black = false;

    // Tour noire h8 (Petit roque noir)
    if ((orig_f == 7 && orig_r == 7) || (dest_f == 7 && dest_r == 7))
        this->short_castle_black = false;
}



void Chessboard::checkPromotion(Square& second_square, PieceType force_promotion)
{
    if (force_promotion != NONE)
    {
        second_square.setPiece(Piece(second_square.getPiece().getColor(), force_promotion));
    }
}

bool Chessboard::isCastlePossible(int orig_file, int orig_rank, int file, int rank, const std::array<Square, 64>& board_copy)
{
    bool short_castle = (file == 6);
    bool long_castle = (file == 2);

    if (!short_castle && !long_castle)
    {
        std::cout << "Invalid castling move!" << std::endl;
        return false;
    }

    int dir = short_castle ? 1 : -1;
    Piece king_piece = this->board[orig_rank * 8 + orig_file].getPiece();

    for (int i = 0; i <= 2; i++)
    {
        int current_file = orig_file + (i * dir);
        this->setBoard(board_copy);

        // On place le roi sur la case testée et on vide l'origine (si on a bougé)
        this->board[orig_rank * 8 + current_file].setPiece(king_piece);
        if (current_file != orig_file) {
            this->board[orig_rank * 8 + orig_file].setPiece(Piece());
        }

        // Mise à jour temporaire du cache des coordonnées pour checkForCheck()
        if (this->turn == WHITE) {
            this->white_king_file = current_file;
        }
        else {
            this->black_king_file = current_file;
        }

        bool is_checked = this->isInCheck();
        if (this->turn == WHITE) {
            this->white_king_file = orig_file;
        }
        else {
            this->black_king_file = orig_file;
        }

        if (is_checked)
        {
            std::cout << "You cannot castle: there are threats on the way." << std::endl;
            this->setBoard(board_copy);
            return false;
        }
    }

    // On restaure le plateau propre avant de valider les mouvements finaux
    this->setBoard(board_copy);

    // On est sûr que le castle est valide : on bouge la tour
    if (short_castle)
    {
        this->board[rank * 8 + 5].setPiece(Piece(this->turn, ROOK));
        this->board[rank * 8 + 7].setPiece(Piece());
    }
    else if (long_castle)
    {
        this->board[rank * 8 + 3].setPiece(Piece(this->turn, ROOK));
        this->board[rank * 8 + 0].setPiece(Piece());
    }
    return true;
}

bool Chessboard::movePiece(int orig_file, int orig_rank, int file, int rank, PieceType promotion)
{
    Square& first_square = this->board[orig_rank * 8 + orig_file];
    Square& second_square = this->board[rank * 8 + file];

    const std::vector<Move> legalMoves = this->getLegalMoves(orig_file, orig_rank);

    if (first_square.getPiece().getColor() != this->turn)
    {
        std::cout << "It is not your turn!" << std::endl;
        return false;
    }

    // 2. Création du coup tenté (incluant la promotion demandée)
    Move attempted_move(first_square, second_square, promotion);

    // 3. Validation : la case et la promotion doivent correspondre
    if (std::find(legalMoves.begin(), legalMoves.end(), attempted_move) != legalMoves.end())
    {
        std::array<Square, 64> board_copy = this->board;

        Piece moving_piece = first_square.getPiece();
        bool is_king_move = (moving_piece.getType() == KING);
        Color moving_color = moving_piece.getColor();

        // si on veut castle: regarder si on est en échec, ou si le chemin est safe
        if (first_square.getPiece().getType() == KING && abs(orig_file - file) == 2)
        {
            if (!this->isCastlePossible(orig_file, orig_rank, file, rank, board_copy))
                return false;
        }

        // check si on a pris en passant
        if (second_square.getPiece().getType() == NONE && first_square.getPiece().getType() == PAWN && abs(orig_file - file) == 1)
        {
            this->board[orig_rank * 8 + file].setPiece(Piece());
        }

        second_square.setPiece(first_square.getPiece());
        first_square.setPiece(Piece());


        // maj du cache si le roi bouge
        if (is_king_move)
        {
            if (moving_color == WHITE) {
                this->white_king_file = file; this->white_king_rank = rank;
            }
            else {
                this->black_king_file = file; this->black_king_rank = rank;
            }
        }

        if (this->isInCheck())
        {
            std::cout << "Illegal move." << std::endl;
            this->setBoard(board_copy);

            // Restauration du cache
            if (is_king_move)
            {
                if (moving_color == WHITE) {
                    this->white_king_file = orig_file; this->white_king_rank = orig_rank;
                }
                else {
                    this->black_king_file = orig_file; this->black_king_rank = orig_rank;
                }
            }
            return false;
        }

        this->checkPromotion(second_square, promotion);
        this->updateHistory(first_square, second_square);

        this->updateCastleFlags();
        this->checkEnPassant();

        this->turn = (this->turn == WHITE) ? BLACK : WHITE;

        if (!this->hasAnyLegalMove())  // soit mat soit pat
        {
            if (this->isInCheck())
            {
                this->current_state = CHECKMATE;
                std::cout << "Checkmate!" << std::endl;
            }
            else
            {
                this->current_state = STALEMATE;
                std::cout << "Stalemate!" << std::endl;
            }
        }

        return true;
    }
    else
    {
        std::cout << "Illegal move" << std::endl;
        return false;
    }
}

bool Chessboard::movePiece(std::string orig_square, std::string square)
{
    // Attention: files et ranks sont dans le .hpp, assure-toi qu'ils sont accessibles ou crée une conversion propre
    int orig_file = orig_square[0] - 'a';
    int orig_rank = orig_square[1] - '1';
    int file = square[0] - 'a';
    int rank = square[1] - '1';

    return this->movePiece(orig_file, orig_rank, file, rank);
}

bool Chessboard::movePieceSAN(std::string san)
{
    san.erase(std::remove(san.begin(), san.end(), '+'), san.end());
    san.erase(std::remove(san.begin(), san.end(), '#'), san.end());
    san.erase(std::remove(san.begin(), san.end(), '!'), san.end());
    san.erase(std::remove(san.begin(), san.end(), '?'), san.end());

    if (san == "O-O" || san == "O-O-O")
    {
        int rank = (this->turn == WHITE) ? 0 : 7;
        int orig_file = 4;
        int dest_file = (san == "O-O") ? 6 : 2;
        return this->movePiece(orig_file, rank, dest_file, rank);
    }

    PieceType promotion_type = NONE;
    size_t equal_pos = san.find('=');
    if (equal_pos != std::string::npos)
    {
        char p = san.back();
        if (p == 'Q') promotion_type = QUEEN;
        else if (p == 'R') promotion_type = ROOK;
        else if (p == 'B') promotion_type = BISHOP;
        else if (p == 'N') promotion_type = KNIGHT;
        san = san.substr(0, equal_pos);
    }

    if (san.length() < 2) return false;

    char dest_f_char = san[san.length() - 2];
    char dest_r_char = san[san.length() - 1];
    int dest_file = dest_f_char - 'a';
    int dest_rank = dest_r_char - '1';
    san = san.substr(0, san.length() - 2);

    PieceType p_type = PAWN;
    if (!san.empty() && isupper(san[0]))
    {
        char p = san[0];
        if (p == 'K') p_type = KING;
        else if (p == 'Q') p_type = QUEEN;
        else if (p == 'R') p_type = ROOK;
        else if (p == 'B') p_type = BISHOP;
        else if (p == 'N') p_type = KNIGHT;
        san = san.substr(1);
    }

    if (!san.empty() && san.back() == 'x')
    {
        san.pop_back();
    }

    int orig_file_hint = -1;
    int orig_rank_hint = -1;
    for (char c : san)
    {
        if (c >= 'a' && c <= 'h') orig_file_hint = c - 'a';
        if (c >= '1' && c <= '8') orig_rank_hint = c - '1';
    }

    int final_orig_file = -1;
    int final_orig_rank = -1;
    int match_count = 0;

    for (int i = 0; i < 8; i++) // i = file
    {
        for (int j = 0; j < 8; j++) // j = rank
        {
            const Square& sq = this->board[j * 8 + i];
            if (sq.CheckOccupied() && sq.getPiece().getColor() == this->turn && sq.getPiece().getType() == p_type)
            {
                if (orig_file_hint != -1 && i != orig_file_hint) continue;
                if (orig_rank_hint != -1 && j != orig_rank_hint) continue;

                std::vector<Move> legal_moves = this->getLegalMoves(i, j);
                for (const Move& m : legal_moves)
                {
                    if (m.getDestSquare().getFile() == dest_file && m.getDestSquare().getRank() == dest_rank)
                    {
                        if (promotion_type != NONE && m.getPromotion() != promotion_type)
                        {
                            continue; // On passe au coup légal suivant (ex: on ignore e8=R si on cherche e8=Q)
                        }

                        bool is_king_move = (p_type == KING);

                        if (is_king_move) {
                            if (this->turn == WHITE) { this->white_king_file = dest_file; this->white_king_rank = dest_rank; }
                            else { this->black_king_file = dest_file; this->black_king_rank = dest_rank; }
                        }

                        std::array<Square, 64> board_copy = this->board;

                        // Gestion du pion capturé en passant lors de la simulation
                        bool is_en_passant = (this->board[j * 8 + i].getPiece().getType() == PAWN &&
                            abs(i - dest_file) == 1 &&
                            this->board[dest_rank * 8 + dest_file].getPiece().getType() == NONE);

                        if (is_en_passant) {
                            this->board[j * 8 + dest_file].setPiece(Piece());
                        }

                        this->board[dest_rank * 8 + dest_file].setPiece(this->board[j * 8 + i].getPiece());
                        this->board[j * 8 + i].setPiece(Piece());

                        bool leaves_king_in_check = this->isInCheck();


                        this->board = board_copy;

                        if (is_king_move) {
                            if (this->turn == WHITE) { this->white_king_file = i; this->white_king_rank = j; }
                            else { this->black_king_file = i; this->black_king_rank = j; }
                        }

                        if (!leaves_king_in_check)
                        {
                            final_orig_file = i;
                            final_orig_rank = j;
                            match_count++;
                        }
                        break;
                    }
                }
            }
        }
    }

    if (match_count == 1)
    {
        return this->movePiece(final_orig_file, final_orig_rank, dest_file, dest_rank, promotion_type);
    }
    else
    {
        std::cerr << "Erreur SAN : " << match_count << " origines trouvées pour le coup " << san << std::endl;
        return false;
    }
}

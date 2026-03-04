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

bool Chessboard::checkThreefoldRepetition() const
{
    if (this->boardHistory.size() < 5) return false;

    int count = 0;
    const std::array<Square, 64>& current_board = this->board;

    for (const auto& past_board : this->boardHistory)
    {
        if (past_board == current_board)
        {
            count++;
        }
    }

    // Le plateau actuel est déjà dans l'historique au moment où on l'appelle,
    // on cherche donc au moins 3 occurrences.
    return count >= 3;
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

int Chessboard::getHalfMoveClock() const
{
    return this->half_move_clock;
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


std::vector<Move> Chessboard::getAllLegalMoves()
{
    std::vector<Move> result;
    Color color = this->turn;

    for (int i = 0; i < 8; i++) // file
    {
        for (int j = 0; j < 8; j++) // rank
        {
            if (this->board[j * 8 + i].getPiece().getColor() != color)
                continue;

            std::vector<Move> pseudo_moves = this->getLegalMoves(i, j);
            for (const Move& move : pseudo_moves)
            {
                int dest_file = move.getDestSquare().getFile();
                int dest_rank = move.getDestSquare().getRank();
                PieceType p_type = this->board[j * 8 + i].getPiece().getType();
                bool is_king_move = (p_type == KING);

                // Roque : vérification dédiée
                if (is_king_move && std::abs(i - dest_file) == 2)
                {
                    std::array<Square, 64> board_copy = this->board;
                    if (!this->isCastlePossible(i, j, dest_file, dest_rank, board_copy))
                        continue;

                    // Restaurer car isCastlePossible a déplacé la tour sur this->board
                    this->board = board_copy;
                }

                // Simulation du coup
                if (is_king_move) {
                    if (color == WHITE) { this->white_king_file = dest_file; this->white_king_rank = dest_rank; }
                    else { this->black_king_file = dest_file; this->black_king_rank = dest_rank; }
                }

                std::array<Square, 64> board_copy = this->board;

                bool is_en_passant = (p_type == PAWN &&
                    std::abs(i - dest_file) == 1 &&
                    this->board[dest_rank * 8 + dest_file].getPiece().getType() == NONE);

                if (is_en_passant)
                    this->board[j * 8 + dest_file].setPiece(Piece());

                this->board[dest_rank * 8 + dest_file].setPiece(this->board[j * 8 + i].getPiece());
                this->board[j * 8 + i].setPiece(Piece());

                bool in_check = this->isInCheck();

                this->board = board_copy;

                if (is_king_move) {
                    if (color == WHITE) { this->white_king_file = i; this->white_king_rank = j; }
                    else { this->black_king_file = i; this->black_king_rank = j; }
                }

                if (!in_check)
                    result.push_back(move);
            }
        }
    }
    return result;
}

bool Chessboard::hasAnyLegalMove()
{
    return !this->getAllLegalMoves().empty();
}

int Chessboard::encodeMove(const Move& move) const
{
    int orig_f = move.getOrigSquare().getFile();
    int orig_r = move.getOrigSquare().getRank();
    int dest_f = move.getDestSquare().getFile();
    int dest_r = move.getDestSquare().getRank();
    PieceType promotion = move.getPromotion();
    bool is_black = (this->turn == BLACK);

    if (is_black)
    {
        orig_r = 7 - orig_r;
        dest_r = 7 - dest_r;
    }

    int df = dest_f - orig_f;
    int dr = dest_r - orig_r;
    int plane = -1;

    if (promotion == KNIGHT || promotion == BISHOP || promotion == ROOK)
    {
        int dir_idx = df + 1;
        int p_idx = 0;
        if (promotion == KNIGHT) p_idx = 0;
        else if (promotion == BISHOP) p_idx = 1;
        else if (promotion == ROOK) p_idx = 2;
        plane = 64 + dir_idx * 3 + p_idx;
    }
    else if ((std::abs(df) == 2 && std::abs(dr) == 1) || (std::abs(df) == 1 && std::abs(dr) == 2))
    {
        int knight_moves[8][2] = { {1, 2}, {2, 1}, {2, -1}, {1, -2}, {-1, -2}, {-2, -1}, {-2, 1}, {-1, 2} };
        for (int i = 0; i < 8; ++i)
        {
            if (knight_moves[i][0] == df && knight_moves[i][1] == dr)
            {
                plane = 56 + i;
                break;
            }
        }
    }
    else
    {
        int dirs[8][2] = { {0, 1}, {1, 1}, {1, 0}, {1, -1}, {0, -1}, {-1, -1}, {-1, 0}, {-1, 1} };
        int dist = std::max(std::abs(df), std::abs(dr));
        if (dist == 0) return -1;

        int dir_f = df / dist;
        int dir_r = dr / dist;
        int dir_idx = -1;
        for (int i = 0; i < 8; ++i)
        {
            if (dirs[i][0] == dir_f && dirs[i][1] == dir_r)
            {
                dir_idx = i;
                break;
            }
        }
        if (dir_idx != -1)
        {
            plane = dir_idx * 7 + (dist - 1);
        }
    }

    if (plane == -1) return -1;
    return plane * 64 + orig_r * 8 + orig_f;
}

std::vector<int> Chessboard::getLegalMoveIndices()
{
    std::vector<int> indices;
    std::vector<Move> all_legal_moves = this->getAllLegalMoves();

    for (const Move& move : all_legal_moves)
    {
        int idx = this->encodeMove(move);
        if (idx != -1)
        {
            indices.push_back(idx);
        }
    }
    return indices;
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
    //if (check)
    //    std::cout << "Check!" << std::endl;
}

//...............Setters...............

void Chessboard::Clear()
{
    this->board = std::array<Square, 64>();
    for (int i = 0; i < 8; i++)
    {
        for (int j = 0; j < 8; j++)
        {
            this->board[j * 8 + i].setPosition(i, j);
        }
    }
    this->current_state = ONGOING;
    this->half_move_clock = 0;

    this->moveHistory.clear();
    this->boardHistory.clear();
    this->snapshotHistory.clear();
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
    this->boardHistory.push_back(this->board);
}

void Chessboard::setBoard(std::array<Square, 64> some_board)
{
    this->board = some_board;
}

void Chessboard::updateHistory(const Move& move)
{
    this->moveHistory.push_back(move);
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
        //std::cout << "Invalid castling move!" << std::endl;
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
            //std::cout << "You cannot castle: there are threats on the way." << std::endl;
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

void Chessboard::createAndPushSnapshot()
{
    StateSnapshot snapshot;
    snapshot.short_castle_white = this->short_castle_white;
    snapshot.long_castle_white = this->long_castle_white;
    snapshot.short_castle_black = this->short_castle_black;
    snapshot.long_castle_black = this->long_castle_black;
    snapshot.en_passant = this->en_passant;
    snapshot.en_passant_file = this->en_passant_file;
    snapshot.half_move_clock = this->half_move_clock;
    snapshot.current_state = this->current_state;
    snapshot.white_king_file = this->white_king_file;
    snapshot.white_king_rank = this->white_king_rank;
    snapshot.black_king_file = this->black_king_file;
    snapshot.black_king_rank = this->black_king_rank;

    this->snapshotHistory.push_back(snapshot);
}

void Chessboard::evaluateGameState()
{
    if (!this->hasAnyLegalMove())  // soit mat soit pat
    {
        if (this->isInCheck())
        {
            this->current_state = CHECKMATE;
            //std::cout << "Checkmate!" << std::endl;
        }
        else
        {
            this->current_state = STALEMATE;
            //std::cout << "Stalemate!" << std::endl;
        }
    }
    else if (this->checkThreefoldRepetition())
    {
        this->current_state = DRAW_REPETITION;
        //std::cout << "Draw by threefold repetition!" << std::endl;
    }
    else if (this->half_move_clock >= 100) // Fin de partie par la règle des 50 coups
    {
        this->current_state = DRAW_50_MOVES;
        //std::cout << "Draw by 50-move rule!" << std::endl;
    }
}

bool Chessboard::movePiece(int orig_file, int orig_rank, int file, int rank, PieceType promotion, bool check_game_end)
{
    Square& first_square = this->board[orig_rank * 8 + orig_file];
    Square& second_square = this->board[rank * 8 + file];

    const std::vector<Move> legalMoves = this->getLegalMoves(orig_file, orig_rank);

    if (first_square.getPiece().getColor() != this->turn)
    {
        //std::cout << "It is not your turn!" << std::endl;
        return false;
    }

    // 2. Création du coup tenté
    Move attempted_move(first_square, second_square, promotion);

    // 3. Validation
    if (std::find(legalMoves.begin(), legalMoves.end(), attempted_move) != legalMoves.end())
    {
        std::array<Square, 64> board_copy = this->board;

        Piece moving_piece = first_square.getPiece();
        bool is_king_move = (moving_piece.getType() == KING);
        Color moving_color = moving_piece.getColor();

        bool is_en_passant_capture = (second_square.getPiece().getType() == NONE &&
            moving_piece.getType() == PAWN &&
            abs(orig_file - file) == 1);
        bool is_capture = second_square.CheckOccupied() || is_en_passant_capture;
        bool is_pawn_move = (moving_piece.getType() == PAWN);

        // Roque
        if (is_king_move && abs(orig_file - file) == 2)
        {
            if (!this->isCastlePossible(orig_file, orig_rank, file, rank, board_copy))
                return false;
        }

        // Prise en passant
        if (is_en_passant_capture)
        {
            this->board[orig_rank * 8 + file].setPiece(Piece());
        }

        second_square.setPiece(first_square.getPiece());
        first_square.setPiece(Piece());

        // Mise à jour du cache si le roi bouge
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
            //std::cout << "Illegal move." << std::endl;
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

        this->createAndPushSnapshot();

        this->checkPromotion(second_square, promotion);
        this->updateHistory(attempted_move);

        this->updateCastleFlags();
        this->checkEnPassant();

        this->turn = (this->turn == WHITE) ? BLACK : WHITE;

        // maj du compteur de la règle des 50 coups
        if (is_capture || is_pawn_move) {
            this->half_move_clock = 0;
        }
        else {
            this->half_move_clock++;
        }

        if (check_game_end)
        {
            this->evaluateGameState();
        }

        return true;
    }
    else
    {
        //std::cout << "Illegal move" << std::endl;
        return false;
    }
}

bool Chessboard::movePiece(std::string orig_square, std::string square)
{
    int orig_file = orig_square[0] - 'a';
    int orig_rank = orig_square[1] - '1';
    int file = square[0] - 'a';
    int rank = square[1] - '1';

    return this->movePiece(orig_file, orig_rank, file, rank);
}

bool Chessboard::movePieceSAN(std::string san)
{
    // 1. Nettoyage de la chaîne
    san.erase(std::remove(san.begin(), san.end(), '+'), san.end());
    san.erase(std::remove(san.begin(), san.end(), '#'), san.end());
    san.erase(std::remove(san.begin(), san.end(), '!'), san.end());
    san.erase(std::remove(san.begin(), san.end(), '?'), san.end());

    // 2. Traitement des roques
    if (san == "O-O" || san == "O-O-O")
    {
        int rank = (this->turn == WHITE) ? 0 : 7;
        int orig_file = 4;
        int dest_file = (san == "O-O") ? 6 : 2;
        return this->movePiece(orig_file, rank, dest_file, rank);
    }

    // 3. Traitement des promotions
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

    // 4. Extraction de la destination
    char dest_f_char = san[san.length() - 2];
    char dest_r_char = san[san.length() - 1];
    int dest_file = dest_f_char - 'a';
    int dest_rank = dest_r_char - '1';
    san = san.substr(0, san.length() - 2);

    // 5. Déduction du type de pièce
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

    // 6. Suppression du symbole de capture
    if (!san.empty() && san.back() == 'x')
    {
        san.pop_back();
    }

    // 7. Extraction des indices de désambiguïsation
    int orig_file_hint = -1;
    int orig_rank_hint = -1;
    for (char c : san)
    {
        if (c >= 'a' && c <= 'h') orig_file_hint = c - 'a';
        if (c >= '1' && c <= '8') orig_rank_hint = c - '1';
    }

    // 8. Recherche du coup parmi les coups strictement légaux
    int final_orig_file = -1;
    int final_orig_rank = -1;
    int match_count = 0;

    std::vector<Move> all_legal_moves = this->getAllLegalMoves();

    for (const Move& m : all_legal_moves)
    {
        int o_f = m.getOrigSquare().getFile();
        int o_r = m.getOrigSquare().getRank();
        int d_f = m.getDestSquare().getFile();
        int d_r = m.getDestSquare().getRank();
        PieceType move_p_type = m.getPiece().getType();

        // Filtrage successif pour trouver le match exact
        if (move_p_type != p_type) continue;
        if (d_f != dest_file || d_r != dest_rank) continue;
        if (orig_file_hint != -1 && o_f != orig_file_hint) continue;
        if (orig_rank_hint != -1 && o_r != orig_rank_hint) continue;
        if (promotion_type != NONE && m.getPromotion() != promotion_type) continue;

        final_orig_file = o_f;
        final_orig_rank = o_r;
        match_count++;
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

void Chessboard::undoMove()
{
    if (this->moveHistory.empty()) return;

    // 1. Retrait du dernier coup
    this->moveHistory.pop_back();
    this->boardHistory.pop_back();

    // La position précédente est maintenant le dernier élément de boardHistory
    // (car l'état initial est indexé en 0 par setStartupPieces)
    this->board = this->boardHistory.back();

    // 2. Restauration des métadonnées via le snapshot
    StateSnapshot snapshot = this->snapshotHistory.back();
    this->snapshotHistory.pop_back();

    this->short_castle_white = snapshot.short_castle_white;
    this->long_castle_white = snapshot.long_castle_white;
    this->short_castle_black = snapshot.short_castle_black;
    this->long_castle_black = snapshot.long_castle_black;
    this->en_passant = snapshot.en_passant;
    this->en_passant_file = snapshot.en_passant_file;
    this->half_move_clock = snapshot.half_move_clock;
    this->current_state = snapshot.current_state;
    this->white_king_file = snapshot.white_king_file;
    this->white_king_rank = snapshot.white_king_rank;
    this->black_king_file = snapshot.black_king_file;
    this->black_king_rank = snapshot.black_king_rank;

    // 3. Restitution du trait
    this->turn = (this->turn == WHITE) ? BLACK : WHITE;
}

std::vector<float> Chessboard::getAlphaZeroTensor() const
{
    // Allocation d'un vecteur plat de 7616 valeurs (119 plans * 8 rangées * 8 colonnes), initialisé à 0
    std::vector<float> tensor(119 * 64, 0.0f);

    Color p1_color = this->turn;
    Color p2_color = (p1_color == WHITE) ? BLACK : WHITE;

    bool flip = (p1_color == BLACK);

    // Remplissage de l'historique (112 premiers plans)
    for (int t = 0; t < 8; t++)
    {
        int history_idx = this->boardHistory.size() - 1 - t;
        if (history_idx < 0) break; // Padding implicite (les plans resteront à zéro si la partie a moins de 8 coups)

        const std::array<Square, 64>& hist_board = this->boardHistory[history_idx];
        int plane_offset = t * 14 * 64;

        // Calcul des répétitions à cet instant précis du passé
        int rep_count = 0;
        for (int i = 0; i <= history_idx; i++) {
            if (this->boardHistory[i] == hist_board) rep_count++;
        }

        for (int rank = 0; rank < 8; rank++)
        {
            for (int file = 0; file < 8; file++)
            {
                const Piece& piece = hist_board[rank * 8 + file].getPiece();
                // Calcul des coordonnées inversées si c'est aux Noirs de jouer
                int tensor_rank = flip ? (7 - rank) : rank;
                int flat_idx = tensor_rank * 8 + file;

                if (piece.getType() != NONE)
                {
                    int piece_idx = -1;
                    switch (piece.getType()) {
                    case PAWN:   piece_idx = 0; break;
                    case KNIGHT: piece_idx = 1; break;
                    case BISHOP: piece_idx = 2; break;
                    case ROOK:   piece_idx = 3; break;
                    case QUEEN:  piece_idx = 4; break;
                    case KING:   piece_idx = 5; break;
                    default: break;
                    }

                    // P1 = 0 à 5, P2 = 6 à 11
                    if (piece.getColor() == p1_color) {
                        tensor[plane_offset + piece_idx * 64 + flat_idx] = 1.0f;
                    }
                    else {
                        tensor[plane_offset + (6 + piece_idx) * 64 + flat_idx] = 1.0f;
                    }
                }

                // Plans 12 et 13 : Répétitions
                if (rep_count == 2) {
                    tensor[plane_offset + 12 * 64 + flat_idx] = 1.0f;
                }
                else if (rep_count >= 3) {
                    tensor[plane_offset + 13 * 64 + flat_idx] = 1.0f;
                }
            }
        }
    }

    // Remplissage des 7 plans de contexte (Offset = 112 * 64 = 7168)
    int constant_offset = 112 * 64;

    float color_val = (this->turn == WHITE) ? 1.0f : 0.0f;
    // Normalisation des compteurs pour le réseau de neurones (sur une base arbitraire de 100)
    float total_moves_val = std::min(1.0f, (float)(this->boardHistory.size() / 2) / 100.0f);
    float p1_castle_k = (p1_color == WHITE) ? (this->short_castle_white ? 1.0f : 0.0f) : (this->short_castle_black ? 1.0f : 0.0f);
    float p1_castle_q = (p1_color == WHITE) ? (this->long_castle_white ? 1.0f : 0.0f) : (this->long_castle_black ? 1.0f : 0.0f);
    float p2_castle_k = (p2_color == WHITE) ? (this->short_castle_white ? 1.0f : 0.0f) : (this->short_castle_black ? 1.0f : 0.0f);
    float p2_castle_q = (p2_color == WHITE) ? (this->long_castle_white ? 1.0f : 0.0f) : (this->long_castle_black ? 1.0f : 0.0f);
    float no_progress_val = (float)this->half_move_clock / 100.0f;

    for (int i = 0; i < 64; i++)
    {
        tensor[constant_offset + 0 * 64 + i] = color_val;
        tensor[constant_offset + 1 * 64 + i] = total_moves_val;
        tensor[constant_offset + 2 * 64 + i] = p1_castle_k;
        tensor[constant_offset + 3 * 64 + i] = p1_castle_q;
        tensor[constant_offset + 4 * 64 + i] = p2_castle_k;
        tensor[constant_offset + 5 * 64 + i] = p2_castle_q;
        tensor[constant_offset + 6 * 64 + i] = no_progress_val;
    }

    return tensor;
}

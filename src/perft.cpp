#include "perft.hpp"

#include <string>
#include <unordered_set>

namespace {

void report_violation(PerftReport& report, const std::string& message) {
    report.violations++;
    if (report.messages.size() < MAX_PERFT_MESSAGES) {
        report.messages.push_back(message);
    }
}

// Les contrôles stricts sont implémentés en tâche 3.
void run_strict_checks(Chessboard& board,
                       const std::vector<Move>& moves,
                       PerftReport& report) {
    (void)board;
    (void)moves;
    (void)report;
}

// Le contrôle FEN est implémenté en tâche 4.
void run_fen_check(Chessboard& board, PerftReport& report) {
    (void)board;
    (void)report;
}

uint64_t perft_rec(Chessboard& board, int depth,
                   const PerftOptions& opts, PerftReport& report) {
    if (depth == 0) return 1;

    std::vector<Move> moves = board.getAllLegalMoves();

    if (opts.strict)    run_strict_checks(board, moves, report);
    if (opts.check_fen) run_fen_check(board, report);

    uint64_t nodes = 0;
    for (const Move& move : moves) {
        const int orig_f = move.getOrigSquare().getFile();
        const int orig_r = move.getOrigSquare().getRank();
        const int dest_f = move.getDestSquare().getFile();
        const int dest_r = move.getDestSquare().getRank();

        // Un refus ici signifie que movePiece rejette un coup que le moteur
        // vient lui-même de générer : c'est un bug, pas un cas normal.
        if (!board.movePiece(orig_f, orig_r, dest_f, dest_r, move.getPromotion(), false)) {
            report_violation(report,
                "movePiece a refuse un coup genere : " + move_to_uci(move));
            continue;
        }

        nodes += perft_rec(board, depth - 1, opts, report);
        board.undoMove();
    }
    return nodes;
}

} // namespace

std::string move_to_uci(const Move& move) {
    std::string uci;
    uci += static_cast<char>('a' + move.getOrigSquare().getFile());
    uci += static_cast<char>('1' + move.getOrigSquare().getRank());
    uci += static_cast<char>('a' + move.getDestSquare().getFile());
    uci += static_cast<char>('1' + move.getDestSquare().getRank());

    switch (move.getPromotion()) {
    case QUEEN:  uci += 'q'; break;
    case ROOK:   uci += 'r'; break;
    case BISHOP: uci += 'b'; break;
    case KNIGHT: uci += 'n'; break;
    default: break;
    }
    return uci;
}

PerftReport perft(Chessboard& board, int depth, const PerftOptions& opts) {
    PerftReport report;
    report.nodes = perft_rec(board, depth, opts, report);
    return report;
}

std::vector<std::pair<std::string, uint64_t>> perft_divide(
    Chessboard& board, int depth, const PerftOptions& opts) {

    std::vector<std::pair<std::string, uint64_t>> result;
    if (depth <= 0) return result;

    PerftReport scratch;
    std::vector<Move> moves = board.getAllLegalMoves();
    result.reserve(moves.size());

    for (const Move& move : moves) {
        const int orig_f = move.getOrigSquare().getFile();
        const int orig_r = move.getOrigSquare().getRank();
        const int dest_f = move.getDestSquare().getFile();
        const int dest_r = move.getDestSquare().getRank();

        if (!board.movePiece(orig_f, orig_r, dest_f, dest_r, move.getPromotion(), false)) {
            result.emplace_back(move_to_uci(move), 0);
            continue;
        }

        result.emplace_back(move_to_uci(move), perft_rec(board, depth - 1, opts, scratch));
        board.undoMove();
    }
    return result;
}

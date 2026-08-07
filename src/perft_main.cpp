#include <algorithm>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

#include "chessboard.hpp"
#include "perft.hpp"

namespace {

const char* STARTPOS_FEN =
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

void load_position(Chessboard& board, const std::string& fen) {
    board.loadFEN(fen == "startpos" ? STARTPOS_FEN : fen);
}

void print_messages(const PerftReport& report) {
    for (const std::string& message : report.messages) {
        std::cout << "    [VIOLATION] " << message << "\n";
    }
    if (report.violations > report.messages.size()) {
        std::cout << "    [VIOLATION] ... et "
                  << (report.violations - report.messages.size())
                  << " autre(s), non affichee(s).\n";
    }
}

int cmd_divide(const std::string& fen, int depth, const PerftOptions& opts) {
    Chessboard board;
    load_position(board, fen);

    const auto start = std::chrono::steady_clock::now();
    const auto entries = perft_divide(board, depth, opts);
    const double seconds =
        std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();

    uint64_t total = 0;
    for (const auto& entry : entries) {
        std::cout << entry.first << ": " << entry.second << "\n";
        total += entry.second;
    }

    std::cout << "\nCoups racine : " << entries.size() << "\n";
    std::cout << "Total        : " << total << "\n";
    std::cout << "Temps        : " << std::fixed << std::setprecision(2) << seconds << " s\n";
    if (seconds > 0.0) {
        std::cout << "Vitesse      : "
                  << static_cast<uint64_t>(total / seconds) << " noeuds/s\n";
    }
    return 0;
}

void print_usage() {
    std::cout <<
        "Usage :\n"
        "  chess_perft divide <fen|startpos> <profondeur> [--strict] [--check-fen]\n";
}

} // namespace

int main(int argc, char** argv) {
    std::vector<std::string> args(argv + 1, argv + argc);

    PerftOptions opts;
    std::vector<std::string> positional;
    for (const std::string& arg : args) {
        if (arg == "--strict")         opts.strict = true;
        else if (arg == "--check-fen") opts.check_fen = true;
        else                           positional.push_back(arg);
    }

    if (positional.empty()) {
        print_usage();
        return 2;
    }

    const std::string& command = positional[0];

    if (command == "divide") {
        if (positional.size() < 3) {
            print_usage();
            return 2;
        }
        return cmd_divide(positional[1], std::stoi(positional[2]), opts);
    }

    print_usage();
    return 2;
}

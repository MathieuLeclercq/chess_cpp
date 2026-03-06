#include <pybind11/pybind11.h>
#include <pybind11/stl.h> // Indispensable pour la conversion des std::vector et std::array
#include "chessboard.hpp"
#include "piece.hpp"
#include "move.hpp"
#include "square.hpp"
#include <pybind11/numpy.h>

namespace py = pybind11;

PYBIND11_MODULE(chess_engine, m) {
    m.doc() = "Moteur d'échecs C++ bindé pour Python";

    // --- Enums ---
    py::enum_<Color>(m, "Color")
        .value("WHITE", WHITE)
        .value("BLACK", BLACK)
        .value("NO_COLOR", NO_COLOR)
        .export_values();

    py::enum_<PieceType>(m, "PieceType")
        .value("NONE", NONE)
        .value("PAWN", PAWN)
        .value("KNIGHT", KNIGHT)
        .value("BISHOP", BISHOP)
        .value("ROOK", ROOK)
        .value("QUEEN", QUEEN)
        .value("KING", KING)
        .export_values();

    py::enum_<GameState>(m, "GameState")
        .value("ONGOING", ONGOING)
        .value("CHECKMATE", CHECKMATE)
        .value("STALEMATE", STALEMATE)
        .value("DRAW_REPETITION", DRAW_REPETITION)
        .value("DRAW_50_MOVES", DRAW_50_MOVES)
        .export_values();

    // --- Classes ---
    py::class_<Piece>(m, "Piece")
        .def(py::init<>())
        .def(py::init<Color, PieceType>())
        .def("get_type", &Piece::getType)
        .def("get_color", static_cast<const Color & (Piece::*)() const>(&Piece::getColor)); // Cast nécessaire à cause de la surcharge dans ton code

    py::class_<Square>(m, "Square")
        .def(py::init<>())
        .def(py::init<int, int>())
        .def("get_file", &Square::getFile)
        .def("get_rank", &Square::getRank)
        .def("get_piece", static_cast<const Piece & (Square::*)() const>(&Square::getPiece))
        .def("is_occupied", &Square::CheckOccupied)
        .def("get_name", &Square::getName);

    py::class_<Move>(m, "Move")
        .def("get_dest_square", static_cast<const Square & (Move::*)() const>(&Move::getDestSquare))
        .def("get_orig_square", static_cast<const Square & (Move::*)() const>(&Move::getOrigSquare))
        .def("get_promotion", &Move::getPromotion);

    py::class_<Chessboard>(m, "Chessboard")
        .def(py::init<>())
        .def("set_startup_pieces", &Chessboard::setStartupPieces)
        .def("get_square", static_cast<const Square & (Chessboard::*)(int, int) const>(&Chessboard::getSquare))
        .def("get_naive_legal_moves", &Chessboard::getNaiveLegalMoves)
        .def("move_piece", static_cast<bool (Chessboard::*)(int, int, int, int, PieceType, bool)>(&Chessboard::movePiece),
            py::arg("orig_file"), py::arg("orig_rank"), py::arg("file"), py::arg("rank"), py::arg("promotion") = NONE, py::arg("check_game_end") = true)
        .def("has_any_legal_move", &Chessboard::hasAnyLegalMove)
        .def("is_in_check", &Chessboard::isInCheck)
        .def("undo_move", &Chessboard::undoMove)
        .def_property_readonly("turn", &Chessboard::getTurn)
        .def_property_readonly("game_state", &Chessboard::getGameState)
        .def_property_readonly("half_move_clock", &Chessboard::getHalfMoveClock)
        .def("get_alphazero_tensor", [](const Chessboard& cb) {
        std::vector<float> tensor = cb.getAlphaZeroTensor();
        return py::array_t<float>({ 119, 8, 8 }, tensor.data());
            })
        .def("move_piece_san", &Chessboard::movePieceSAN)
        .def("get_legal_move_indices", &Chessboard::getLegalMoveIndices)
        .def("get_last_move_data", [](const Chessboard& cb) {
        if (cb.getMoveHistory().empty()) return py::make_tuple(-1, -1, -1, -1, NONE);
        const Move& last_move = cb.getMoveHistory().back();
        return py::make_tuple(
            last_move.getOrigSquare().getFile(),
            last_move.getOrigSquare().getRank(),
            last_move.getDestSquare().getFile(),
            last_move.getDestSquare().getRank(),
            last_move.getPromotion()
        );
            });
}

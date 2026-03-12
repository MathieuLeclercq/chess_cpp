"""
Moteur d'échecs C++ bindé pour Python
"""
from __future__ import annotations
import numpy
import pybind11_stubgen.typing_ext
import typing
__all__: list[str] = ['BISHOP', 'BLACK', 'CHECKMATE', 'Chessboard', 'Color', 'DRAW_50_MOVES', 'DRAW_INSUFF_MATERIAL', 'DRAW_REPETITION', 'GameState', 'KING', 'KNIGHT', 'MCTS', 'Move', 'NONE', 'NO_COLOR', 'ONGOING', 'PAWN', 'Piece', 'PieceType', 'QUEEN', 'ROOK', 'STALEMATE', 'Square', 'WHITE']
class Chessboard:
    def __init__(self) -> None:
        ...
    def get_alphazero_tensor(self) -> numpy.ndarray[numpy.float32]:
        ...
    def get_board_history(self) -> list[typing.Annotated[list[Square], pybind11_stubgen.typing_ext.FixedSize(64)]]:
        ...
    def get_last_move_data(self) -> tuple:
        ...
    def get_legal_move_indices(self) -> list[int]:
        ...
    def get_legal_moves(self, arg0: int, arg1: int) -> list[Move]:
        ...
    def get_square(self, arg0: int, arg1: int) -> Square:
        ...
    def has_any_legal_move(self) -> bool:
        ...
    def is_in_check(self) -> bool:
        ...
    def move_piece(self, orig_file: int, orig_rank: int, file: int, rank: int, promotion: PieceType = PieceType.NONE, check_game_end: bool = True) -> bool:
        ...
    def move_piece_san(self, arg0: str) -> bool:
        ...
    def set_kiwipete(self) -> None:
        ...
    def set_startup_pieces(self) -> None:
        ...
    def undo_move(self) -> None:
        ...
    @property
    def game_state(self) -> GameState:
        ...
    @property
    def half_move_clock(self) -> int:
        ...
    @property
    def turn(self) -> Color:
        ...
class Color:
    """
    Members:
    
      WHITE
    
      BLACK
    
      NO_COLOR
    """
    BLACK: typing.ClassVar[Color]  # value = <Color.BLACK: 1>
    NO_COLOR: typing.ClassVar[Color]  # value = <Color.NO_COLOR: 2>
    WHITE: typing.ClassVar[Color]  # value = <Color.WHITE: 0>
    __members__: typing.ClassVar[dict[str, Color]]  # value = {'WHITE': <Color.WHITE: 0>, 'BLACK': <Color.BLACK: 1>, 'NO_COLOR': <Color.NO_COLOR: 2>}
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: int) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: int) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class GameState:
    """
    Members:
    
      ONGOING
    
      CHECKMATE
    
      STALEMATE
    
      DRAW_REPETITION
    
      DRAW_50_MOVES
    
      DRAW_INSUFF_MATERIAL
    """
    CHECKMATE: typing.ClassVar[GameState]  # value = <GameState.CHECKMATE: 1>
    DRAW_50_MOVES: typing.ClassVar[GameState]  # value = <GameState.DRAW_50_MOVES: 4>
    DRAW_INSUFF_MATERIAL: typing.ClassVar[GameState]  # value = <GameState.DRAW_INSUFF_MATERIAL: 5>
    DRAW_REPETITION: typing.ClassVar[GameState]  # value = <GameState.DRAW_REPETITION: 3>
    ONGOING: typing.ClassVar[GameState]  # value = <GameState.ONGOING: 0>
    STALEMATE: typing.ClassVar[GameState]  # value = <GameState.STALEMATE: 2>
    __members__: typing.ClassVar[dict[str, GameState]]  # value = {'ONGOING': <GameState.ONGOING: 0>, 'CHECKMATE': <GameState.CHECKMATE: 1>, 'STALEMATE': <GameState.STALEMATE: 2>, 'DRAW_REPETITION': <GameState.DRAW_REPETITION: 3>, 'DRAW_50_MOVES': <GameState.DRAW_50_MOVES: 4>, 'DRAW_INSUFF_MATERIAL': <GameState.DRAW_INSUFF_MATERIAL: 5>}
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: int) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: int) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class MCTS:
    def __init__(self, model_path: str) -> None:
        ...
    def mcts_search(self, board: Chessboard, num_simulations: int, c_puct: float = 1.399999976158142, add_dirichlet: bool = False) -> list[float]:
        ...
class Move:
    def get_dest_square(self) -> Square:
        ...
    def get_orig_square(self) -> Square:
        ...
    def get_promotion(self) -> PieceType:
        ...
class Piece:
    @typing.overload
    def __init__(self) -> None:
        ...
    @typing.overload
    def __init__(self, arg0: Color, arg1: PieceType) -> None:
        ...
    def get_color(self) -> Color:
        ...
    def get_type(self) -> PieceType:
        ...
class PieceType:
    """
    Members:
    
      NONE
    
      PAWN
    
      KNIGHT
    
      BISHOP
    
      ROOK
    
      QUEEN
    
      KING
    """
    BISHOP: typing.ClassVar[PieceType]  # value = <PieceType.BISHOP: 3>
    KING: typing.ClassVar[PieceType]  # value = <PieceType.KING: 0>
    KNIGHT: typing.ClassVar[PieceType]  # value = <PieceType.KNIGHT: 4>
    NONE: typing.ClassVar[PieceType]  # value = <PieceType.NONE: 6>
    PAWN: typing.ClassVar[PieceType]  # value = <PieceType.PAWN: 5>
    QUEEN: typing.ClassVar[PieceType]  # value = <PieceType.QUEEN: 1>
    ROOK: typing.ClassVar[PieceType]  # value = <PieceType.ROOK: 2>
    __members__: typing.ClassVar[dict[str, PieceType]]  # value = {'NONE': <PieceType.NONE: 6>, 'PAWN': <PieceType.PAWN: 5>, 'KNIGHT': <PieceType.KNIGHT: 4>, 'BISHOP': <PieceType.BISHOP: 3>, 'ROOK': <PieceType.ROOK: 2>, 'QUEEN': <PieceType.QUEEN: 1>, 'KING': <PieceType.KING: 0>}
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: int) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: int) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class Square:
    @typing.overload
    def __init__(self) -> None:
        ...
    @typing.overload
    def __init__(self, arg0: int, arg1: int) -> None:
        ...
    def get_file(self) -> int:
        ...
    def get_name(self) -> str:
        ...
    def get_piece(self) -> Piece:
        ...
    def get_rank(self) -> int:
        ...
    def is_occupied(self) -> bool:
        ...
BISHOP: PieceType  # value = <PieceType.BISHOP: 3>
BLACK: Color  # value = <Color.BLACK: 1>
CHECKMATE: GameState  # value = <GameState.CHECKMATE: 1>
DRAW_50_MOVES: GameState  # value = <GameState.DRAW_50_MOVES: 4>
DRAW_INSUFF_MATERIAL: GameState  # value = <GameState.DRAW_INSUFF_MATERIAL: 5>
DRAW_REPETITION: GameState  # value = <GameState.DRAW_REPETITION: 3>
KING: PieceType  # value = <PieceType.KING: 0>
KNIGHT: PieceType  # value = <PieceType.KNIGHT: 4>
NONE: PieceType  # value = <PieceType.NONE: 6>
NO_COLOR: Color  # value = <Color.NO_COLOR: 2>
ONGOING: GameState  # value = <GameState.ONGOING: 0>
PAWN: PieceType  # value = <PieceType.PAWN: 5>
QUEEN: PieceType  # value = <PieceType.QUEEN: 1>
ROOK: PieceType  # value = <PieceType.ROOK: 2>
STALEMATE: GameState  # value = <GameState.STALEMATE: 2>
WHITE: Color  # value = <Color.WHITE: 0>

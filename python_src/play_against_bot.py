import warnings
import threading
import pygame
import sys
import numpy as np

warnings.filterwarnings("ignore", category=UserWarning, message="pkg_resources is deprecated")
warnings.filterwarnings("ignore", message=".*weights_only=False.*")

import chess_engine
from lib_gui import (
    SQUARE_SIZE,
    pygame_init,
    load_images,
    rendu
)
from lib import (move_to_san, print_pgn, decode_move_index, chose_move_idx)

# ============================================================
#                     CONFIGURATION
# ============================================================

HUMAN_COLOR = chess_engine.Color.WHITE
CHECKPOINT_PATH = "checkpoints/2026_03_13_01h31_iter18_unsupervised.onnx"

NUM_SIMULATIONS = 1200

TAU_FIRST_MOVE = 2
TAU_OPENING = 1
TAU_ENDGAME = 0.1
TAU_THRESHOLD = 8  # Nombre de demi-coups avant de basculer sur TAU_ENDGAME


# ============================================================
#                     FONCTION WORKER (THREAD)
# ============================================================

def mcts_worker(san_moves_copy, mcts_engine, num_simulations, result_container):
    """
    Exécute le MCTS en arrière-plan avec logique de température.
    """
    # 1. Recréation de l'état du plateau
    temp_board = chess_engine.Chessboard()
    temp_board.set_startup_pieces()
    for move in san_moves_copy:
        temp_board.move_piece_san(move)

    # 2. Lancement de la recherche C++ / ONNX
    pi_raw = mcts_engine.mcts_search(temp_board, num_simulations, 1.4, False)
    pi = np.array(pi_raw, dtype=np.float32)

    # 3. Logique de température
    move_count = len(san_moves_copy)
    if move_count < 2:
        current_tau = TAU_FIRST_MOVE
    elif move_count < TAU_THRESHOLD:
        current_tau = TAU_OPENING
    else:
        current_tau = TAU_ENDGAME

    best_idx = chose_move_idx(pi, current_tau)

    # 5. Décodage
    is_black = (temp_board.turn == chess_engine.Color.BLACK)
    orig_f, orig_r, dest_f, dest_r, promo = decode_move_index(temp_board, best_idx, is_black)

    # Affichage console
    san = move_to_san(temp_board, orig_f, orig_r, dest_f, dest_r, promo)
    # On affiche la probabilité réelle de l'index choisi pour voir l'influence de Tau
    print(f"\n[AI] Coup choisi : {san} (Tau: {current_tau})")

    result_container.append((orig_f, orig_r, dest_f, dest_r, promo))


# ============================================================
#                     BOUCLE PRINCIPALE
# ============================================================


class ChessGame:
    def __init__(
            self,
            board: chess_engine.Chessboard,
            mcts_engine: chess_engine.MCTS,
            human_color: chess_engine.Color = chess_engine.Color.WHITE
    ):
        self.board: chess_engine.Chessboard = board
        self.mcts_engine: chess_engine.MCTS = mcts_engine
        self.human_color = human_color

        self.selected_square: tuple[int, int] | None = None
        self.san_moves: list = []
        self.ai_result_container: list = []
        self.current_legal_moves: list[chess_engine.Move] = []
        self.drag_pos: tuple[int, int] = (0, 0)

        self.red_squares: set = set()

        # states
        self.is_human_turn: bool = False
        self._is_running: bool = False  # game process
        self._game_over: bool = False  # chess game
        self._is_dragging: bool = False
        self._is_ai_thinking: bool = False

        self.screen, self.clock = pygame_init()
        load_images()

    def start(self):
        if self._is_running:
            raise Exception("Game is already running!")
        self._is_running = True

    def stop(self):
        if not self._is_running:
            raise Exception("Process is not Currently running!")
        self._game_over = True
        self._is_running = False

    def endGame(self):
        if self._game_over:
            raise Exception("Game has already stopped!")
        self._game_over = True

    def isRunning(self):
        return self._is_running

    def gameEnded(self):
        return self._game_over

    def isAiThinking(self):
        return self._is_ai_thinking

    def AiStartThinking(self):
        if self._is_ai_thinking:
            raise Exception("AI is already thinking!")
        self._is_ai_thinking = True

    def AiStopThinking(self):
        if not self._is_ai_thinking:
            raise Exception("AI is NOT currently thinking!")
        self._is_ai_thinking = False

    def isDragging(self):
        return self._is_dragging

    def startDragging(self, clicked_sq, mouse_x, mouse_y):
        if self._is_dragging:
            raise Exception("Already currently dragging!")
        self.selected_square = clicked_sq
        self._is_dragging = True
        self.drag_pos = (mouse_x, mouse_y)

    def stopDragging(self):
        if not self._is_dragging:
            raise Exception("Not currently dragging!")
        self._is_dragging = False

    def computeClickedSquare(self):
        x, y = pygame.mouse.get_pos()
        if self.human_color == chess_engine.Color.WHITE:
            clicked_file = x // SQUARE_SIZE
            clicked_rank = 7 - (y // SQUARE_SIZE)
        else:
            clicked_file = 7 - (x // SQUARE_SIZE)
            clicked_rank = y // SQUARE_SIZE

        clicked_sq = (clicked_file, clicked_rank)
        return clicked_sq, x, y

    def clearActions(self):
        self.selected_square = None
        self.current_legal_moves = []

    def eventLeftClickDown(self, clicked_sq, mouse_x, mouse_y):
        # 2 possibilités : drag ou cliquer sur case d'arrivée pour bouger (move)

        clicked_file, clicked_rank = clicked_sq
        self.red_squares.clear()
        if self.selected_square is None:
            # Cas 1 : Aucune pièce sélectionnée, on en saisit une
            sq = self.board.get_square(clicked_file, clicked_rank)
            if sq.is_occupied():
                self.startDragging(clicked_sq, mouse_x, mouse_y)
                if sq.get_piece().get_color() == self.human_color:
                    self.current_legal_moves = self.board.get_legal_moves(clicked_file,
                                                                          clicked_rank)
        else:
            # Cas 2 : Une pièce est déjà sélectionnée (Click-to-Click)
            valid_move = None
            promotion_type = chess_engine.PieceType.NONE

            for move in self.current_legal_moves:
                if (move.get_dest_square().get_file() == clicked_file and
                        move.get_dest_square().get_rank() == clicked_rank):
                    valid_move = move
                    if move.get_promotion() == chess_engine.PieceType.QUEEN:
                        promotion_type = chess_engine.PieceType.QUEEN
                        break

            if valid_move is not None and self.is_human_turn and not self.gameEnded():
                orig_f, orig_r = self.selected_square
                san = move_to_san(self.board, orig_f, orig_r, clicked_file, clicked_rank,
                                  promotion_type)
                success = self.board.move_piece(orig_f, orig_r, clicked_file, clicked_rank,
                                                promotion_type)

                if success:
                    self.clearActions()
                    if self.board.game_state == chess_engine.GameState.CHECKMATE:
                        san += "#"
                    elif self.board.is_in_check():
                        san += "+"
                    self.san_moves.append(san)
                    if self.board.game_state != chess_engine.GameState.ONGOING:
                        self.endGame()
                else:
                    raise Exception("Error while moving piece")

                self.selected_square = None
                self.current_legal_moves = []
            else:  # pas de coup valide donc on drag la pièce actuelle
                sq = self.board.get_square(clicked_file, clicked_rank)
                if sq.is_occupied():
                    # On change la sélection
                    self.startDragging(clicked_sq, mouse_x, mouse_y)
                    if sq.get_piece().get_color() == self.human_color:
                        self.current_legal_moves = self.board.get_legal_moves(clicked_file,
                                                                              clicked_rank)
                else:
                    self.current_legal_moves = []

    def loop(self):
        self.is_human_turn = (self.board.turn == HUMAN_COLOR)
        for event in pygame.event.get():
            clicked_sq, mouse_x, mouse_y = self.computeClickedSquare()
            clicked_file, clicked_rank = clicked_sq

            if event.type == pygame.QUIT:
                self.stop()

            # --- CLIC DROIT : Surlignage rouge ---
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                if clicked_sq in self.red_squares:
                    self.red_squares.remove(clicked_sq)
                else:
                    self.red_squares.add(clicked_sq)

            # --- CLIC GAUCHE (DOWN) : Saisir ou Cliquer-pour-bouger ---
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.eventLeftClickDown(clicked_sq, mouse_x, mouse_y)

            # --- SOURIS (MOTION) : Faire glisser ---
            elif event.type == pygame.MOUSEMOTION:
                if self.isDragging():
                    self.drag_pos = event.pos

            # --- CLIC GAUCHE (UP) : Relâcher la pièce (Drag-and-Drop) ---
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.isDragging():
                    self.stopDragging()
                    if (clicked_file, clicked_rank) == self.selected_square:
                        pass
                    else:
                        valid_move = None
                        promotion_type = chess_engine.PieceType.NONE

                        for move in self.current_legal_moves:
                            if (move.get_dest_square().get_file() == clicked_file and
                                    move.get_dest_square().get_rank() == clicked_rank):
                                valid_move = move
                                if move.get_promotion() == chess_engine.PieceType.QUEEN:
                                    promotion_type = chess_engine.PieceType.QUEEN
                                    break

                        if valid_move is not None:
                            orig_f, orig_r = self.selected_square
                            san = move_to_san(self.board, orig_f, orig_r, clicked_file,
                                              clicked_rank,
                                              promotion_type)
                            success = self.board.move_piece(orig_f, orig_r, clicked_file,
                                                            clicked_rank,
                                                            promotion_type)

                            if success:
                                self.clearActions()
                                if self.board.game_state == chess_engine.GameState.CHECKMATE:
                                    san += "#"
                                elif self.board.is_in_check():
                                    san += "+"
                                self.san_moves.append(san)
                                if self.board.game_state != chess_engine.GameState.ONGOING:
                                    self.endGame()

                        else:
                            pass

        # 2. Tour de l'IA
        if not self.is_human_turn and not self.gameEnded():
            if not self.isAiThinking():
                self.AiStartThinking()
                self.ai_result_container.clear()
                thread = threading.Thread(
                    target=mcts_worker,
                    args=(self.san_moves.copy(), self.mcts_engine, NUM_SIMULATIONS,
                          self.ai_result_container)
                )
                thread.start()

            elif len(self.ai_result_container) > 0:
                result = self.ai_result_container.pop()
                if result is not None:
                    orig_f, orig_r, dest_f, dest_r, promo = result
                    san = move_to_san(self.board, orig_f, orig_r, dest_f, dest_r, promo)
                    success = self.board.move_piece(orig_f, orig_r, dest_f, dest_r, promo)
                    self.clearActions()
                    if not success:
                        raise Exception("Error while getting AI's move.")

                    if self.board.game_state == chess_engine.GameState.CHECKMATE:
                        san += "#"
                    elif self.board.is_in_check():
                        san += "+"
                    self.san_moves.append(san)

                if self.board.game_state != chess_engine.GameState.ONGOING:
                    self.endGame()
                self.AiStopThinking()

        # 3. Appel de rendu mis à jour
        self.clock = rendu(
            self.screen,
            self.board,
            self.selected_square,
            self.current_legal_moves,
            self.clock,
            self.isDragging(),
            self.drag_pos,
            self.red_squares,
            perspective=HUMAN_COLOR
        )


def main():
    print(f"Chargement du moteur MCTS avec {CHECKPOINT_PATH}...")
    mcts_engine = chess_engine.MCTS(CHECKPOINT_PATH)

    board = chess_engine.Chessboard()
    board.set_startup_pieces()
    game = ChessGame(
        board=board,
        mcts_engine=mcts_engine,
        human_color=HUMAN_COLOR)
    game.start()

    while game.isRunning():
        game.loop()
    print_pgn(game.board, game.san_moves)
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()

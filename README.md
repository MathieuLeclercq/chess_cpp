# LapZero-Chess

A custom chess engine built in C++ and Python.

* AlphaZero-style (MCTS + Neural Network).
* Designed for training on consumer-grade setups (single GPU).
* Supervised pretraining (Lichess & Grandmaster datasets), Unsupervised self-play.
* Move generator validated by a full perft suite (610M nodes, zero mismatches).
* UCI compatible.
* [Lichess Profile (rating: 2217 in Rapid)](https://lichess.org/@/mboobot)

![Interface graphique AlphaChess-Zero](docs/screenshots/gui.png)

## 🚀 Overview

The goal of this project was to implement a deep learning-based chess entity on a single laptop. To overcome hardware limitations, the project follows a two-stage learning process:
1. **Supervised Learning (SL):** Initializing the policy and value networks using a dataset of Grandmaster games and high-level Lichess games (freely available on [Lichess Datasets](https://database.lichess.org/)).
2. **Reinforcement Learning (RL):** Improving the model through self-play using Monte Carlo Tree Search (MCTS).

![Évolution du classement Elo des bots](docs/screenshots/bot_elo.png)

## 🆚 Differences from the Original AlphaZero

While the core architecture heavily relies on DeepMind's 2017 paper, several adaptations were made to allow efficient training on a consumer-grade laptop (RTX 3070):

- **Supervised Initialization:** Instead of starting from purely random weights (Zero-knowledge), the Policy and Value networks were pre-trained on a dataset of Grandmaster and high-level Lichess games. This massively accelerates the initial grasp of chess fundamentals.
- **Optimizer:** The original implementation used SGD with Momentum and manual step decay. This project uses **AdamW**, which provides decoupled weight decay and faster, more stable convergence for this scale.
- **Compute-Aware Self-Play (Fast/Slow Moves):** To maximize hardware efficiency, self-play games mix "fast" moves (100 MCTS simulations) and "slow" moves (700 simulations). This generates more terminal game states to train the Value head faster, while maintaining enough deep MCTS searches to provide high-quality targets for the Policy head. The slow-move ratio is raised in endgames (6 pieces or fewer), where Grandmaster datasets provide few mating examples.
- **First Play Urgency (FPU):** In DeepMind's paper, unvisited MCTS nodes are initialized with a Q-value of 0. In this engine, inheriting [LeelaChessZero](https://github.com/LeelaChessZero/lc0)'s approach, unvisited nodes inherit their parent's value. This reduces catastrophic blunders during early exploration.
- **Tactical FEN Injection:** 20% of self-play games start from a Lichess puzzle position instead of the initial position, with a deeper first search and stronger root noise, to expose the network to sharp tactics it would rarely reach on its own.
- **History Dropout ("amnesia mode"):** Puzzle positions carry no move history, full games do. To stop the network from using the presence of history planes as a shortcut signal, the 8-ply history stack is randomly collapsed to a single position on 5% of moves.
- **Network Size & Pipeline:** The ResNet is scaled down (10 blocks, 128 filters vs 20 blocks, 256 filters) to fit local VRAM constraints, with Squeeze-and-Excitation blocks added. The training loop is synchronous (Self-Play -> Train -> Evaluate) rather than fully asynchronous across thousands of TPUs.

## 🛠 Core Features

### ⚡ High-Performance C++ Engine
Unlike many Python-based RL projects, this engine is built in **C++17** for maximum efficiency:
- **Custom Move Generator:** No external chess libraries used. Every rule (castling, en passant, promotion) is implemented from scratch.
- **Validated:** The generator passes perft on the six standard reference positions, 610,195,852 nodes with zero mismatches. See [Testing](#-testing).
- **Speed:** Roughly **1.8M nodes/second** in perft (Intel Core Ultra 7 255H, single thread), where each node includes full legal move generation, move execution with incremental Zobrist update, and unmake.
- **Pybind11 Integration:** The core logic is exposed to Python as a highly optimized module (`chess_engine`), allowing the RL loop to interact with the C++ state without overhead.

### 🧠 AlphaZero Pipeline
- **Zero-Knowledge Philosophy:** The engine provides no heuristic evaluation; the model learns purely from board geometry and game outcomes.
- **Batched MCTS:** Self-play runs many concurrent games in C++ and groups their leaf evaluations into a single GPU batch, keeping the GPU saturated without needing virtual loss.
- **Model Architecture:** A deep Residual Convolutional Neural Network (ResNet) with Squeeze-and-Excitation blocks, Policy and Value heads.

### 📊 Evaluation & Tournament System
- **WHR (Whole History Rating):** Instead of a simple Elo, the project uses a WHR system to track the relative strength evolution of different model iterations.
- **Dynamic Tournament:** A script manages matches between bots. New models are automatically challenged by the current "Champion" to ensure accurate ranking.
- **Stockfish Anchor:** Periodic matches against a node-limited Stockfish give an absolute reference point during training.

### 🖥 GUI & Tools
- **Custom GUI:** A Pygame-based interface to play against your trained models in real-time.
- **Dataset Pipeline:** Tools to extract, clean, and shard Lichess/GM data into a binary format for high-speed training.

## 📂 Project Structure

### C++ Source (`/src`)
- `chessboard.cpp/hpp`: Core board representation, move generation and validation.
- `mcts.cpp/hpp`: Tree search, transposition table, FPU, Dirichlet noise.
- `selfplay_manager.cpp/hpp`: Concurrent game orchestration and GPU batching.
- `onnx_evaluator.cpp/hpp`: ONNX Runtime inference wrapper (CUDA or CPU).
- `perft.cpp/hpp`, `perft_main.cpp`: Move generator validation suite.
- `zobrist.cpp/hpp`: Incremental position hashing.
- `pgn_parser.cpp/hpp`: High-speed PGN/SAN string processing.
- `piece.cpp`, `square.cpp`, `move.cpp`: Atomic chess entities.
- `bindings.cpp`: Pybind11 bridge definitions.

### Python Source (`/python_src`)
- `model.py`: PyTorch implementation of the ResNet.
- `train_supervised.py`: Script for the initial imitation learning phase.
- `train_self_play.py`: The RL loop (multi-processed on CPU for game generation, GPU for training).
- `tournament_elo.py`: Tournament manager using the WHR algorithm.
- `stockfish_player.py`: Stockfish anchor evaluation.
- `uci.py`: UCI adapter, used for the Lichess bot.
- `play_against_bot.py`: Visual GUI for human-vs-bot matches.
- `lib.py`: Common utilities for move decoding and model loading.
- `dev_tools/`: Diagnostic tooling, not part of the engine or its validation.

## 🧪 Testing

The move generator has a dedicated validation suite. The C++ layer is the source of truth and depends on nothing outside the standard library; reference node counts are hardcoded from the [Chess Programming Wiki](https://www.chessprogramming.org/Perft_Results).

```bash
# Fast tier: 6 reference positions, depths 1-3, plus internal consistency checks
./build/Release/chess_perft.exe bench --strict --check-fen

# Full tier: up to depth 6, ~610M nodes, around 6 minutes
./build/Release/chess_perft.exe deep --strict

# Per-root-move breakdown, for locating a mismatch
./build/Release/chess_perft.exe divide startpos 5
```

`--strict` additionally verifies that `encodeMove` loses no legal move, that policy
indices stay within `[0, 4671]` and are pairwise distinct, and that
`hasAnyLegalMove` agrees with `getAllLegalMoves`. `--check-fen` verifies that
`loadFEN(toFEN(b))` reproduces the same Zobrist hash as `b`.

A separate differential fuzzer plays random legal games and compares the legal
move set against `python-chess` at every ply. It is a **diagnostic tool only**:
it never gates validation, so the engine's independence from external chess
libraries holds for its test suite too.

```bash
# 200k positions, biased towards castling and promotions
python python_src/dev_tools/fuzz_movegen.py

# Locate where a perft mismatch originates
python python_src/dev_tools/fuzz_movegen.py --bisect "<fen>" 5
```

Latest results: [docs/superpowers/specs/2026-08-07-perft-resultats.md](docs/superpowers/specs/2026-08-07-perft-resultats.md).

## 📈 Performance & Technical Notes

- **Independent Logic:** This project does **not** rely on `python-chess` for game simulation. All chess logic is handled by the custom C++ core.
- **Resource Optimization:** Game generation is parallelized across CPU cores using OpenMP to saturate the hardware during the Self-Play phase, while the GPU is reserved for neural network batches and backpropagation.

## 🛠 Installation & Build

### 1. Prerequisites
- **Windows** (Tested on W11)
- **CMake** (>= 3.15, the one bundled with Visual Studio works)
- **C++17 Compiler** (MSVC)
- **Python 3.13** (required: `CMakeLists.txt` asks for it and the compiled module is a `cp313`)
- **CUDA Toolkit 12.x** with cuDNN, for ONNX Runtime GPU inference
- **[uv](https://docs.astral.sh/uv/)** for the Python environment

### 2. Python Environment

Dependencies are declared in `pyproject.toml` and locked in `uv.lock`. uv installs the
right Python version on its own:

```bash
uv sync
```

This creates `.venv` with Python 3.13 and a CUDA build of PyTorch (`cu126`). To target
a different CUDA version, edit the `[[tool.uv.index]]` block in `pyproject.toml` and
re-run `uv lock`.

Without uv, install manually. Note the separate index for the CUDA build of torch:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu126
pip install lightning numpy onnx chess zstandard whr wandb tqdm pygame requests urllib3 beautifulsoup4 psutil pybind11-stubgen
```

### 3. Build the C++ Engine

The build system automatically downloads ONNX Runtime and Pybind11.

```bash
cmake -S . -B build -DPython3_EXECUTABLE=.venv/Scripts/python.exe
cmake --build build --config Release
```

This generates the `chess_engine` shared library in the `python_src` folder, plus the
`chess_perft` validation executable in `build/Release`.

#### Local Configuration (IDE)
If you have multiple Python environments, create a `CMakeUserPresets.json` at the root
to point to your specific interpreter:

```
{
  "version": 3,
  "configurePresets": [
    {
      "name": "local-env",
      "displayName": "Local Environment Override",
      "cacheVariables": {
        "Python3_EXECUTABLE": "C:/path/to/your/python.exe"
      }
    }
  ]
}
```

### 🎮 Usage
- Train Supervised: ```uv run python python_src/train_supervised.py```
- Self-Play (RL): ```uv run python python_src/train_self_play.py```
- Run Tournament: ```uv run python python_src/tournament_elo.py```
- Play against Bot: ```uv run python python_src/play_against_bot.py```

## 🔮 Future Work & Roadmap

- **Slimmer Board Representation:** `Square` stores its own file and rank (redundant with its index) and `Piece` carries an unused material value, making a board 1280 bytes. Since `movePiece` pushes a full board copy into history on every move, this costs roughly 4.6 GB/s of memcpy during search. Packing the board and keeping only the 8 history positions the input tensor actually needs is the largest available CPU win.
- **Transposition Table Rework:** Each entry reserves room for 128 moves (1040 bytes), so the default table costs gigabytes for ~35 useful moves per position. The key is also incomplete: it omits the move history, the fifty-move counter and the amnesia flag, all of which feed the network input, so a cache hit can return a value computed under a different context.
- **Bitboard Representation:** Refactoring the internal board state to use bitboards. Now that a perft suite exists, this refactor can be validated rather than merely hoped for.
- **Transformer Architecture:** Exploring Attention mechanisms to replace or augment the current ResNet topology, following recent architectural shifts in modern engines like Leela Chess Zero.

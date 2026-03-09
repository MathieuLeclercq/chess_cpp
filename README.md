# AlphaChess-Zero: Custom C++ Engine & AlphaZero-style RL

A complete Chess ecosystem built from scratch, featuring a high-performance C++ move-generation engine and a Reinforcement Learning pipeline based on the AlphaZero architecture.

## 🚀 Overview

The goal of this project was to implement a deep learning-based chess entity on a single laptop. To overcome hardware limitations, the project follows a two-stage learning process:
1. **Supervised Learning (SL):** Initializing the policy and value networks using a dataset of Grandmaster games.
2. **Reinforcement Learning (RL):** Improving the model through self-play using Monte Carlo Tree Search (MCTS).

## 🛠 Core Features

### ⚡ High-Performance C++ Engine
Unlike many Python-based RL projects, this engine is built in **C++17** for maximum efficiency:
- **Custom Move Generator:** No external chess libraries used. Every rule (castling, en passant, promotion) is implemented from scratch.
- **Speed:** Move execution—including SAN (Standard Algebraic Notation) parsing, move validation, and board state update—takes approximately **0.05ms**.
- **Pybind11 Integration:** The core logic is exposed to Python as a highly optimized module (`chess_engine`), allowing the RL loop to interact with the C++ state without overhead.

### 🧠 AlphaZero Pipeline
- **Zero-Knowledge Philosophy:** The engine provides no heuristic evaluation; the model learns purely from board geometry and game outcomes.
- **MCTS (Monte Carlo Tree Search):** A purely sequential and optimized MCTS implementation in Python (using PyTorch) for decision-making during self-play and evaluation.
- **Model Architecture:** A deep Residual Convolutional Neural Network (ResNet) with Policy and Value heads.

### 📊 Evaluation & Tournament System
- **WHR (Whole History Rating):** Instead of a simple Elo, the project uses a WHR system to track the relative strength evolution of different model iterations.
- **Dynamic Tournament:** A script manages matches between bots. New models are automatically challenged by the current "Champion" to ensure accurate ranking.

### 🖥 GUI & Tools
- **Custom GUI:** A Pygame-based interface to play against your trained models in real-time.
- **Dataset Pipeline:** Tools to extract, clean, and shard Lichess/GM data into a binary format for high-speed training.

## 📂 Project Structure

### C++ Source (`/src`)
- `chessboard.cpp/hpp`: Core board representation and move validation.
- `pgn_parser.cpp/hpp`: High-speed PGN/SAN string processing.
- `bindings.cpp`: Pybind11 bridge definitions.
- `piece.cpp`, `square.cpp`, `move.cpp`: Atomic chess entities.

### Python Source (`/python_src`)
- `mcts.py`: Logic for the tree search.
- `model.py`: PyTorch implementation of the ResNet.
- `train_supervised.py`: Script for the initial imitation learning phase.
- `train_self_play.py`: The RL loop (multi-processed on CPU for game generation, GPU for training).
- `evaluate_elo.py`: Tournament manager using the WHR algorithm.
- `play_alphazero_bot.py`: Visual GUI for human-vs-bot matches.
- `lib.py`: Common utilities for move decoding and model loading.

## 📈 Performance & Technical Notes

- **Independent Logic:** This project does **not** rely on `python-chess` for game simulation. All chess logic is handled by the custom C++ core.
- **Resource Optimization:** Game generation is parallelized across CPU cores using Python's `multiprocessing` to saturate the hardware during the Self-Play phase, while the GPU is reserved for neural network backpropagation.

## 🛠 Installation & Build

### Prerequisites
- CMake (>= 3.14)
- C++17 Compiler
- Python 3.11+
- PyTorch & CUDA

### Build the C++ Engine
```bash
mkdir build
cd build
cmake ..
cmake --build . --config Release
```

This will generate the chess_engine shared library in the python_src folder.

### 🎮 Usage
- Train Supervised: python python_src/train_supervised.py

- Start Self-Play: python python_src/train_self_play.py

- Run Tournament: python python_src/evaluate_elo.py

- Play against Bot: python python_src/play_alphazero_bot.py
cmake_minimum_required(VERSION 3.5)
project(Chess)


set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(${PROJECT_NAME} main.cpp chessboard.cpp square.cpp piece.cpp move.cpp pgn_parser)
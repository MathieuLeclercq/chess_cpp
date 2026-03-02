cmake_minimum_required(VERSION 3.14)
project(Chess)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 1. Création d'une librairie core avec la logique métier
# On ajoute le préfixe src/ devant chaque fichier source
add_library(chess_core STATIC 
    src/chessboard.cpp 
    src/square.cpp 
    src/piece.cpp 
    src/move.cpp 
    src/pgn_parser.cpp
)

# On indique au compilateur où chercher les fichiers d'en-tête (.hpp)
target_include_directories(chess_core PUBLIC src)

# 2. Exécutable de test (C++ pur)
add_executable(chess_tests src/main.cpp)
target_link_libraries(chess_tests PRIVATE chess_core)

# 3. Récupération de pybind11
include(FetchContent)
FetchContent_Declare(
  pybind11
  GIT_REPOSITORY https://github.com/pybind/pybind11.git
  GIT_TAG        v2.11.1
)
FetchContent_MakeAvailable(pybind11)

# 4. Création du module Python
pybind11_add_module(chess_engine src/bindings.cpp)
target_link_libraries(chess_engine PRIVATE chess_core)

# Force CMake à exporter le module compilé dans le dossier gui/
set_target_properties(chess_engine PROPERTIES LIBRARY_OUTPUT_DIRECTORY ${CMAKE_SOURCE_DIR}/gui)
set_target_properties(chess_engine PROPERTIES LIBRARY_OUTPUT_DIRECTORY_RELEASE ${CMAKE_SOURCE_DIR}/gui)
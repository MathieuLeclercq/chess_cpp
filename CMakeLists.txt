cmake_minimum_required(VERSION 3.14)
project(Chess)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ==========================================
# RÉCUPÉRATION DE ONNX RUNTIME (C++)
# ==========================================
set(ONNXRUNTIME_VERSION "1.24.3")
set(ONNXRUNTIME_URL "https://github.com/microsoft/onnxruntime/releases/download/v${ONNXRUNTIME_VERSION}/onnxruntime-win-x64-${ONNXRUNTIME_VERSION}.zip")

include(FetchContent)
FetchContent_Declare(
  onnxruntime
  URL ${ONNXRUNTIME_URL}
)
FetchContent_MakeAvailable(onnxruntime)

# Extraction des chemins vers les dossiers de l'archive téléchargée
FetchContent_GetProperties(onnxruntime SOURCE_DIR onnxruntime_src)
set(ONNXRUNTIME_INCLUDE_DIR "${onnxruntime_src}/include")
set(ONNXRUNTIME_LIB "${onnxruntime_src}/lib/onnxruntime.lib")
set(ONNXRUNTIME_DLL "${onnxruntime_src}/lib/onnxruntime.dll")

# ==========================================
# 1. Création de la librairie core
# ==========================================
add_library(chess_core STATIC 
    src/chessboard.cpp 
    src/square.cpp 
    src/piece.cpp 
    src/move.cpp 
    src/pgn_parser.cpp
    src/mcts.cpp )

# On indique au compilateur où chercher les headers locaux ET ceux de ONNX Runtime
target_include_directories(chess_core PUBLIC src ${ONNXRUNTIME_INCLUDE_DIR})
# On lie la librairie ONNX Runtime
target_link_libraries(chess_core PUBLIC ${ONNXRUNTIME_LIB})

# ==========================================
# 2. Exécutable de test (C++ pur)
# ==========================================
add_executable(chess_tests src/main.cpp "src/mcts.cpp")
target_link_libraries(chess_tests PRIVATE chess_core)

# ==========================================
# 3. Configuration Python & Pybind11
# ==========================================
set(PYTHON_EXECUTABLE "C:/Users/M47h1/.conda/envs/xrayto3d_311/python.exe" CACHE FILEPATH "Chemin vers Python Conda" FORCE)
set(PYBIND11_PYTHON_VERSION "3.11" CACHE STRING "Version Python pour pybind11" FORCE)

FetchContent_Declare(
  pybind11
  GIT_REPOSITORY https://github.com/pybind/pybind11.git
  GIT_TAG        v2.11.1
)
FetchContent_MakeAvailable(pybind11)

# ==========================================
# 4. Création du module Python
# ==========================================
pybind11_add_module(chess_engine src/bindings.cpp)
target_link_libraries(chess_engine PRIVATE chess_core)

# Post-build : Génération des stubs ET copie de la DLL ONNX
add_custom_command(TARGET chess_engine POST_BUILD
    # Copie de la DLL nécessaire à l'exécution
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        ${ONNXRUNTIME_DLL}
        ${CMAKE_SOURCE_DIR}/python_src/onnxruntime.dll
        
    # Génération des stubs (.pyi)
    COMMAND ${CMAKE_COMMAND} -E env "PYTHONPATH=${CMAKE_SOURCE_DIR}/python_src" 
            ${PYTHON_EXECUTABLE} -m pybind11_stubgen chess_engine 
            --enum-class-locations "PieceType:chess_engine"
            --output-dir "${CMAKE_SOURCE_DIR}/python_src"
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}/python_src"
    COMMENT "Copie de onnxruntime.dll et génération des stubs..."
)

# Force CMake à exporter le module compilé dans le dossier python_src/
set_target_properties(chess_engine PROPERTIES LIBRARY_OUTPUT_DIRECTORY ${CMAKE_SOURCE_DIR}/python_src)
set_target_properties(chess_engine PROPERTIES LIBRARY_OUTPUT_DIRECTORY_RELEASE ${CMAKE_SOURCE_DIR}/python_src)

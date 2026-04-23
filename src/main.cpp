#include <iostream>
#include <filesystem>
#include <vector>
#include <chrono>
#include <string>
#include <fstream> // NOUVEAU: Nécessaire pour lire tactics.txt
#include "chessboard.hpp"
#include "pgn_parser.hpp"

namespace fs = std::filesystem;

// Fonction utilitaire pour le stress test des FENs
void test_fen_loading(const std::string& fen_filepath) {
    std::cout << "========================================" << std::endl;
    std::cout << "Debut du stress test FEN sur : " << fen_filepath << std::endl;

    std::ifstream file(fen_filepath);
    if (!file.is_open()) {
        std::cerr << "Erreur : Impossible d'ouvrir le fichier " << fen_filepath << std::endl;
        return;
    }

    std::string fen;
    int success_count = 0;
    Chessboard board; // On réutilise le même plateau pour tester la robustesse de clear()

    auto t_start = std::chrono::high_resolution_clock::now();

    // On lit le fichier ligne par ligne
    while (std::getline(file, fen)) {
        if (fen.empty()) continue;

        // Si loadFEN contient un bug critique (accès hors limite, stoi sans try/catch),
        // le programme crashera ici. S'il passe, c'est que le code est robuste.
        board.loadFEN(fen);
        success_count++;

        // Petit affichage pour montrer que le programme ne freeze pas
        if (success_count % 20000 == 0) {
            std::cout << "-> " << success_count << " FENs charges..." << std::endl;
        }
    }

    auto t_end = std::chrono::high_resolution_clock::now();
    double elapsed_time_ms = std::chrono::duration<double, std::milli>(t_end - t_start).count();

    std::cout << "-> Succes total ! " << success_count << " positions chargees sans crash." << std::endl;
    std::cout << "-> Temps total d'execution FEN : " << elapsed_time_ms << " ms" << std::endl;

    if (success_count > 0) {
        std::cout << "-> Vitesse moyenne : " << (elapsed_time_ms / success_count) << " ms par FEN ("
            << (int)(1000.0 / (elapsed_time_ms / success_count)) << " FENs/sec)" << std::endl;
    }
    std::cout << "========================================\n" << std::endl;
}


int main() {
    // ---------------------------------------------------------
    // 1. TEST DE CHARGE FEN (Puzzles)
    // ---------------------------------------------------------
    // Remplace par le bon chemin vers ton fichier tactics.txt généré par Python
    std::string fen_file_path = "C:/Users/M47h1/Documents/chess_cpp/training_data/tactics.txt";
    test_fen_loading(fen_file_path);


    // ---------------------------------------------------------
    // 2. TEST DE LECTURE PGN (Simulation de parties)
    // ---------------------------------------------------------
    std::string folder_path = "C:/Users/M47h1/Documents/chess_cpp/docs/PGN";

    int success_count = 0;
    int error_count = 0;
    int total_plies = 0;
    std::vector<std::string> failed_files;

    auto t_start = std::chrono::high_resolution_clock::now();

    if (!fs::exists(folder_path) || !fs::is_directory(folder_path)) {
        std::cerr << "Erreur : Le dossier " << folder_path << " n'existe pas." << std::endl;
        return 1;
    }

    std::cout << "Debut des tests PGN sur le dossier : " << folder_path << "\n" << std::endl;

    for (const auto& entry : fs::directory_iterator(folder_path)) {
        if (entry.is_regular_file() && entry.path().extension() == ".pgn") {
            std::string current_file = entry.path().filename().string();
            std::cout << "--- Test du fichier : " << current_file << " ---" << std::endl;

            Chessboard chessboard;
            chessboard.setStartupPieces();
            PgnParser pgnParser;

            if (!pgnParser.parseFiles(entry.path().string())) {
                std::cerr << "-> Echec de la lecture du fichier." << std::endl;
                error_count++;
                failed_files.push_back(current_file);
                continue;
            }

            std::vector<std::string> moves = pgnParser.extractMoves();
            bool game_success = true;

            for (size_t i = 0; i < moves.size(); i++) {
                if (!chessboard.movePieceSAN(moves[i])) {
                    std::cerr << "-> Erreur critique au ply " << i + 1 << " (coup lu : " << moves[i] << ")." << std::endl;
                    game_success = false;
                    break;
                }
                total_plies++;
            }

            if (game_success) {
                std::cout << "-> Succes : " << moves.size() << " demi-coups simules." << std::endl;
                success_count++;
            }
            else {
                error_count++;
                failed_files.push_back(current_file);
            }
            std::cout << std::endl;
        }
    }

    auto t_end = std::chrono::high_resolution_clock::now();
    double elapsed_time_ms = std::chrono::duration<double, std::milli>(t_end - t_start).count();

    std::cout << "========================================" << std::endl;
    std::cout << "Bilan des simulations PGN :" << std::endl;
    std::cout << "Parties reussies : " << success_count << std::endl;
    std::cout << "Parties echouees : " << error_count << std::endl;
    std::cout << "Nombre total de ply simules : " << total_plies << std::endl;
    std::cout << "Temps total d'execution PGN : " << elapsed_time_ms << " ms" << std::endl;

    if (total_plies > 0) {
        double avg_time_per_ply = elapsed_time_ms / total_plies;
        std::cout << "Temps moyen par ply : " << avg_time_per_ply << " ms" << std::endl;
    }

    if (!failed_files.empty()) {
        std::cout << "----------------------------------------" << std::endl;
        std::cout << "Fichiers ayant echoue :" << std::endl;
        for (const std::string& file : failed_files) {
            std::cout << "- " << file << std::endl;
        }
    }
    std::cout << "========================================" << std::endl;

    return 0;
}
#include <iostream>
#include <filesystem>
#include <vector>
#include <chrono>
#include <string>
#include "chessboard.hpp"
#include "pgn_parser.hpp"

namespace fs = std::filesystem;

int main()
{
    std::string folder_path = "C:/Users/M47h1/Documents/chess_cpp/docs/PGN";
    //std::string folder_path = "C:/Users/M47h1/Documents/chess_cpp/docs/PGN";

    int success_count = 0;
    int error_count = 0;
    int total_plies = 0; // Ajout du compteur total
    std::vector<std::string> failed_files;

    auto t_start = std::chrono::high_resolution_clock::now();

    if (!fs::exists(folder_path) || !fs::is_directory(folder_path))
    {
        std::cerr << "Erreur : Le dossier " << folder_path << " n'existe pas." << std::endl;
        return 1;
    }

    std::cout << "Debut des tests sur le dossier : " << folder_path << "\n" << std::endl;

    for (const auto& entry : fs::directory_iterator(folder_path))
    {
        if (entry.is_regular_file() && entry.path().extension() == ".pgn")
        {
            std::string current_file = entry.path().filename().string();
            std::cout << "--- Test du fichier : " << current_file << " ---" << std::endl;

            Chessboard chessboard;
            chessboard.setStartupPieces();
            PgnParser pgnParser;

            if (!pgnParser.parseFiles(entry.path().string()))
            {
                std::cerr << "-> Echec de la lecture du fichier." << std::endl;
                error_count++;
                failed_files.push_back(current_file);
                continue;
            }

            std::vector<std::string> moves = pgnParser.extractMoves();
            bool game_success = true;

            for (size_t i = 0; i < moves.size(); i++)
            {
                if (!chessboard.movePieceSAN(moves[i]))
                {
                    std::cerr << "-> Erreur critique au ply " << i + 1 << " (coup lu : " << moves[i] << ")." << std::endl;
                    game_success = false;
                    break;
                }
                total_plies++;
            }

            if (game_success)
            {
                std::cout << "-> Succes : " << moves.size() << " demi-coups simules." << std::endl;
                success_count++;
            }
            else
            {
                error_count++;
                failed_files.push_back(current_file);
            }
            std::cout << std::endl;
        }
    }

    auto t_end = std::chrono::high_resolution_clock::now();
    double elapsed_time_ms = std::chrono::duration<double, std::milli>(t_end - t_start).count();

    std::cout << "========================================" << std::endl;
    std::cout << "Bilan des simulations :" << std::endl;
    std::cout << "Parties reussies : " << success_count << std::endl;
    std::cout << "Parties echouees : " << error_count << std::endl;
    std::cout << "Nombre total de ply simules : " << total_plies << std::endl; // Affichage du total
    std::cout << "Temps total d'execution : " << elapsed_time_ms << " ms" << std::endl;

    // Affichage de la moyenne par ply (avec protection contre la division par zéro)
    if (total_plies > 0)
    {
        double avg_time_per_ply = elapsed_time_ms / total_plies;
        std::cout << "Temps moyen par ply : " << avg_time_per_ply << " ms" << std::endl;
    }

    if (!failed_files.empty())
    {
        std::cout << "----------------------------------------" << std::endl;
        std::cout << "Fichiers ayant echoue :" << std::endl;
        for (const std::string& file : failed_files)
        {
            std::cout << "- " << file << std::endl;
        }
    }
    std::cout << "========================================" << std::endl;

    return 0;
}
# Suite de validation perft, phase 1 : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Doter le moteur d'une suite perft capable de répondre par oui ou non à « le générateur de coups est-il correct ? », et de localiser précisément chaque bug trouvé.

**Architecture:** Une bibliothèque C++ `perft` sans dépendance externe, exposée par un exécutable `chess_perft` qui compare les comptes de nœuds à des références en dur. Un outil de diagnostic Python séparé utilise `python-chess` comme oracle pour le fuzzing et la bisection automatique, sans jamais conditionner le résultat de la validation.

**Tech Stack:** C++17, CMake, MSVC. Python 3.13 avec `python-chess` pour la couche de diagnostic uniquement.

**Spec de référence:** `docs/superpowers/specs/2026-08-07-perft-design.md`

## Global Constraints

- La couche de validation C++ n'a **aucune dépendance externe**. `python-chess` ne doit jamais apparaître dans le chemin qui décide pass/fail.
- Le code de diagnostic Python vit dans `python_src/dev_tools/` et nulle part ailleurs.
- C++17, `set(CMAKE_CXX_STANDARD 17)` déjà en place dans `CMakeLists.txt`.
- Les FEN et les comptes de référence sont vérifiés contre <https://www.chessprogramming.org/Perft_Results> avant usage. Aucune valeur écrite de mémoire n'est réputée fiable.
- Pas de table de hachage dans le perft : un outil de validation ne doit pas pouvoir masquer un bug.
- Pas de parallélisation en phase 1 : le déterminisme prime.
- Pas de framework de test (Catch2, GoogleTest). Le test est l'exécutable lui-même et son code de sortie.
- Messages de commit sans ligne `Co-Authored-By`.
- Aucun tiret cadratin dans le code, les commentaires ou la documentation.
- Les commentaires du projet sont en français, comme le reste du code. Suivre cette convention.

## Commandes de build

Le projet n'a pas de dossier `build` versionné. Configuration initiale (une fois, télécharge ONNX Runtime et pybind11, comptez plusieurs minutes) :

```bash
cmake -S . -B build
```

Construction de la cible perft uniquement, à relancer après chaque modification C++ :

```bash
cmake --build build --config Release --target chess_perft
```

L'exécutable est produit dans `build/Release/chess_perft.exe`.

## Structure des fichiers

| Fichier | Responsabilité |
|---|---|
| `src/perft.hpp` (créé) | Interface de la bibliothèque perft : types de rapport, options, signatures |
| `src/perft.cpp` (créé) | Parcours récursif make/unmake, contrôles stricts, divide |
| `src/perft_main.cpp` (créé) | CLI, table des positions de référence, formatage des sorties |
| `src/chessboard.hpp` / `.cpp` (modifiés) | Ajout de `toFEN()` |
| `src/bindings.cpp` (modifié) | Exposition de `get_all_legal_moves()` et `to_fen()` pour l'outil de diagnostic |
| `CMakeLists.txt` (modifié) | Ajout de `src/perft.cpp` à `chess_core`, nouvelle cible `chess_perft` |
| `python_src/dev_tools/fuzz_movegen.py` (créé) | Oracle différentiel : fuzzing et bisection |

---

### Task 1 : Noyau perft et commande `divide`

**Files:**
- Create: `src/perft.hpp`
- Create: `src/perft.cpp`
- Create: `src/perft_main.cpp`
- Modify: `CMakeLists.txt:32-41` (ajout de `src/perft.cpp` à `chess_core`), `CMakeLists.txt:52-53` (nouvelle cible)

**Interfaces:**
- Consumes: `Chessboard::getAllLegalMoves()`, `Chessboard::movePiece(int,int,int,int,PieceType,bool)`, `Chessboard::undoMove()`, `Chessboard::loadFEN(const std::string&)`, `Move::getOrigSquare()`, `Move::getDestSquare()`, `Move::getPromotion()`, `Square::getFile()`, `Square::getRank()`
- Produces: `struct PerftOptions {bool strict; bool check_fen;}`, `struct PerftReport {uint64_t nodes; uint64_t violations; std::vector<std::string> messages;}`, `PerftReport perft(Chessboard&, int, const PerftOptions&)`, `std::vector<std::pair<std::string,uint64_t>> perft_divide(Chessboard&, int, const PerftOptions&)`, `std::string move_to_uci(const Move&)`

- [ ] **Step 1 : Écrire l'en-tête de la bibliothèque**

Créer `src/perft.hpp` :

```cpp
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

#include "chessboard.hpp"

// Options de controle activables pendant le parcours.
// Elles n'affectent pas le comptage de noeuds, seulement les verifications.
struct PerftOptions {
    bool strict = false;    // trous 1 et 3 : encodage et hasAnyLegalMove
    bool check_fen = false; // aller-retour toFEN / loadFEN (couteux, faible profondeur)
};

struct PerftReport {
    uint64_t nodes = 0;
    uint64_t violations = 0;
    std::vector<std::string> messages; // tronque a MAX_PERFT_MESSAGES
};

// Nombre maximum de messages conserves, pour eviter de noyer la sortie
// quand un bug se declenche sur des millions de positions.
constexpr size_t MAX_PERFT_MESSAGES = 20;

// Compte les feuilles de l'arbre des coups legaux a la profondeur donnee.
PerftReport perft(Chessboard& board, int depth, const PerftOptions& opts = {});

// Compte les feuilles par coup racine. Le premier membre de chaque paire
// est le coup en notation UCI (ex: "e2e4", "a7a8q").
std::vector<std::pair<std::string, uint64_t>> perft_divide(
    Chessboard& board, int depth, const PerftOptions& opts = {});

std::string move_to_uci(const Move& move);
```

- [ ] **Step 2 : Écrire l'implémentation du noyau**

Créer `src/perft.cpp` :

```cpp
#include "perft.hpp"

#include <string>
#include <unordered_set>

namespace {

void report_violation(PerftReport& report, const std::string& message) {
    report.violations++;
    if (report.messages.size() < MAX_PERFT_MESSAGES) {
        report.messages.push_back(message);
    }
}

// Les contröles stricts sont implementes en Task 3.
void run_strict_checks(Chessboard& board,
                       const std::vector<Move>& moves,
                       PerftReport& report) {
    (void)board;
    (void)moves;
    (void)report;
}

// Le contröle FEN est implemente en Task 4.
void run_fen_check(Chessboard& board, PerftReport& report) {
    (void)board;
    (void)report;
}

uint64_t perft_rec(Chessboard& board, int depth,
                   const PerftOptions& opts, PerftReport& report) {
    if (depth == 0) return 1;

    std::vector<Move> moves = board.getAllLegalMoves();

    if (opts.strict)    run_strict_checks(board, moves, report);
    if (opts.check_fen) run_fen_check(board, report);

    uint64_t nodes = 0;
    for (const Move& move : moves) {
        const int orig_f = move.getOrigSquare().getFile();
        const int orig_r = move.getOrigSquare().getRank();
        const int dest_f = move.getDestSquare().getFile();
        const int dest_r = move.getDestSquare().getRank();

        // Un refus ici signifie que movePiece rejette un coup que le moteur
        // vient lui-meme de generer : c'est un bug, pas un cas normal.
        if (!board.movePiece(orig_f, orig_r, dest_f, dest_r, move.getPromotion(), false)) {
            report_violation(report,
                "movePiece a refuse un coup genere : " + move_to_uci(move));
            continue;
        }

        nodes += perft_rec(board, depth - 1, opts, report);
        board.undoMove();
    }
    return nodes;
}

} // namespace

std::string move_to_uci(const Move& move) {
    std::string uci;
    uci += static_cast<char>('a' + move.getOrigSquare().getFile());
    uci += static_cast<char>('1' + move.getOrigSquare().getRank());
    uci += static_cast<char>('a' + move.getDestSquare().getFile());
    uci += static_cast<char>('1' + move.getDestSquare().getRank());

    switch (move.getPromotion()) {
    case QUEEN:  uci += 'q'; break;
    case ROOK:   uci += 'r'; break;
    case BISHOP: uci += 'b'; break;
    case KNIGHT: uci += 'n'; break;
    default: break;
    }
    return uci;
}

PerftReport perft(Chessboard& board, int depth, const PerftOptions& opts) {
    PerftReport report;
    report.nodes = perft_rec(board, depth, opts, report);
    return report;
}

std::vector<std::pair<std::string, uint64_t>> perft_divide(
    Chessboard& board, int depth, const PerftOptions& opts) {

    std::vector<std::pair<std::string, uint64_t>> result;
    if (depth <= 0) return result;

    PerftReport scratch;
    std::vector<Move> moves = board.getAllLegalMoves();
    result.reserve(moves.size());

    for (const Move& move : moves) {
        const int orig_f = move.getOrigSquare().getFile();
        const int orig_r = move.getOrigSquare().getRank();
        const int dest_f = move.getDestSquare().getFile();
        const int dest_r = move.getDestSquare().getRank();

        if (!board.movePiece(orig_f, orig_r, dest_f, dest_r, move.getPromotion(), false)) {
            result.emplace_back(move_to_uci(move), 0);
            continue;
        }

        result.emplace_back(move_to_uci(move), perft_rec(board, depth - 1, opts, scratch));
        board.undoMove();
    }
    return result;
}
```

Note volontaire : on ne court-circuite pas la profondeur 1 par `return moves.size()`.
L'optimisation classique economiserait environ la moitie du temps, mais elle
n'exercerait plus `movePiece` et `undoMove` sur le dernier ply. Pour un outil de
validation, la couverture prime. L'optimisation reste disponible en phase 2 si le
budget de 60 secondes l'exige.

- [ ] **Step 3 : Écrire la CLI avec la seule commande `divide`**

Créer `src/perft_main.cpp` :

```cpp
#include <chrono>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

#include "chessboard.hpp"
#include "perft.hpp"

namespace {

const char* STARTPOS_FEN =
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

void load_position(Chessboard& board, const std::string& fen) {
    board.loadFEN(fen == "startpos" ? STARTPOS_FEN : fen);
}

void print_messages(const PerftReport& report) {
    for (const std::string& message : report.messages) {
        std::cout << "    [VIOLATION] " << message << "\n";
    }
    if (report.violations > report.messages.size()) {
        std::cout << "    [VIOLATION] ... et "
                  << (report.violations - report.messages.size())
                  << " autre(s), non affichee(s).\n";
    }
}

int cmd_divide(const std::string& fen, int depth, const PerftOptions& opts) {
    Chessboard board;
    load_position(board, fen);

    const auto start = std::chrono::steady_clock::now();
    const auto entries = perft_divide(board, depth, opts);
    const double seconds =
        std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();

    uint64_t total = 0;
    for (const auto& entry : entries) {
        std::cout << entry.first << ": " << entry.second << "\n";
        total += entry.second;
    }

    std::cout << "\nCoups racine : " << entries.size() << "\n";
    std::cout << "Total        : " << total << "\n";
    std::cout << "Temps        : " << std::fixed << std::setprecision(2) << seconds << " s\n";
    if (seconds > 0.0) {
        std::cout << "Vitesse      : "
                  << static_cast<uint64_t>(total / seconds) << " noeuds/s\n";
    }
    return 0;
}

void print_usage() {
    std::cout <<
        "Usage :\n"
        "  chess_perft divide <fen|startpos> <profondeur> [--strict] [--check-fen]\n";
}

} // namespace

int main(int argc, char** argv) {
    std::vector<std::string> args(argv + 1, argv + argc);

    PerftOptions opts;
    std::vector<std::string> positional;
    for (const std::string& arg : args) {
        if (arg == "--strict")         opts.strict = true;
        else if (arg == "--check-fen") opts.check_fen = true;
        else                           positional.push_back(arg);
    }

    if (positional.empty()) {
        print_usage();
        return 2;
    }

    const std::string& command = positional[0];

    if (command == "divide") {
        if (positional.size() < 3) {
            print_usage();
            return 2;
        }
        return cmd_divide(positional[1], std::stoi(positional[2]), opts);
    }

    print_usage();
    return 2;
}
```

- [ ] **Step 4 : Brancher sur CMake**

Dans `CMakeLists.txt`, ajouter `src/perft.cpp` à la liste des sources de `chess_core` :

```cmake
add_library(chess_core STATIC 
    src/chessboard.cpp 
    src/square.cpp 
    src/piece.cpp 
    src/move.cpp 
    src/pgn_parser.cpp
    src/mcts.cpp 
    src/zobrist.cpp
    src/onnx_evaluator.cpp
    src/selfplay_manager.cpp
    src/perft.cpp)
```

Puis, juste après la cible `chess_tests` (ligne 53), ajouter :

```cmake
# ==========================================
# 2 bis. Executable de validation perft
# ==========================================
add_executable(chess_perft src/perft_main.cpp)
target_link_libraries(chess_perft PRIVATE chess_core)
```

- [ ] **Step 5 : Construire et vérifier que la commande répond**

```bash
cmake -S . -B build && cmake --build build --config Release --target chess_perft
```

Attendu : compilation sans erreur, `build/Release/chess_perft.exe` créé.

- [ ] **Step 6 : Vérifier le premier compte, contrôlable à l'œil**

```bash
./build/Release/chess_perft.exe divide startpos 1
```

Attendu : 20 lignes, chacune à `1`, puis `Coups racine : 20` et `Total : 20`.
Les 20 coups doivent être les 16 poussées de pion (`a2a3`, `a2a4`, ... `h2h3`, `h2h4`)
et les 4 sauts de cavalier (`b1a3`, `b1c3`, `g1f3`, `g1h3`). Vérifier visuellement
cette liste : c'est le seul contrôle du plan qui ne dépend d'aucune source externe.

- [ ] **Step 7 : Vérifier la profondeur 2**

```bash
./build/Release/chess_perft.exe divide startpos 2
```

Attendu : `Coups racine : 20` et `Total : 400`. Chaque coup racine doit valoir exactement
`20`, puisque les Noirs disposent des mêmes 20 réponses quelle que soit la première
poussée blanche.

- [ ] **Step 8 : Vérifier que `startpos` et `setStartupPieces()` coïncident**

Ce contrôle valide que la FEN de départ est bien transcrite. Ajouter temporairement dans
`cmd_divide`, juste après `load_position` :

```cpp
    Chessboard reference;
    reference.setStartupPieces();
    if (fen == "startpos" && board.getZobristHash() != reference.getZobristHash()) {
        std::cout << "[ERREUR] loadFEN(STARTPOS_FEN) ne coincide pas avec setStartupPieces()\n";
        return 1;
    }
```

Reconstruire, relancer `divide startpos 1`, confirmer l'absence du message d'erreur,
puis **retirer ce bloc temporaire** et reconstruire.

- [ ] **Step 9 : Commit**

```bash
git add src/perft.hpp src/perft.cpp src/perft_main.cpp CMakeLists.txt
git commit -F - <<'EOF'
Ajoute le noyau perft et la commande divide

Bibliotheque de parcours make/unmake sur getAllLegalMoves, avec
decomposition par coup racine. Nouvelle cible chess_perft.

Les contröles stricts et le contröle FEN sont declares mais vides,
ils sont remplis par les taches suivantes.
EOF
```

---

### Task 2 : Positions de référence et commandes `bench` / `deep`

**Files:**
- Modify: `src/perft_main.cpp`

**Interfaces:**
- Consumes: `perft(Chessboard&, int, const PerftOptions&)` de la Task 1
- Produces: `struct RefPosition {const char* name; const char* fen; std::vector<uint64_t> counts;}`, `const std::vector<RefPosition>& reference_positions()`, commandes `bench` et `deep`

- [ ] **Step 1 : Vérifier les données de référence contre la source**

**Cette étape est obligatoire et ne doit pas être sautée.** Ouvrir
<https://www.chessprogramming.org/Perft_Results> et comparer caractère par caractère
les six FEN et tous les comptes du tableau ci-dessous. Une donnée fausse envoie chasser
un bug inexistant, ce qui est le pire mode de défaillance possible pour cet outil.

Les valeurs ci-dessous sont fournies pour que le plan soit exécutable, mais elles n'ont
pas été vérifiées contre la source. Corriger toute divergence avant de continuer.

| # | Nom | FEN | d1 | d2 | d3 | d4 | d5 | d6 |
|---|---|---|---|---|---|---|---|---|
| 1 | Depart | `rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1` | 20 | 400 | 8902 | 197281 | 4865609 | 119060324 |
| 2 | Kiwipete | `r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1` | 48 | 2039 | 97862 | 4085603 | 193690690 | |
| 3 | Finale | `8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1` | 14 | 191 | 2812 | 43238 | 674624 | 11030083 |
| 4 | Promotions | `r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1` | 6 | 264 | 9467 | 422333 | 15833292 | |
| 5 | Talkchess | `rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8` | 44 | 1486 | 62379 | 2103487 | 89941194 | |
| 6 | Edwards | `r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10` | 46 | 2079 | 89890 | 3894594 | 164075551 | |

- [ ] **Step 2 : Ajouter la table de référence**

Dans `src/perft_main.cpp`, à l'intérieur du `namespace { ... }` anonyme, après
`STARTPOS_FEN` :

```cpp
struct RefPosition {
    const char* name;
    const char* fen;
    std::vector<uint64_t> counts; // counts[i] = perft(i + 1)
};

// Valeurs verifiees contre https://www.chessprogramming.org/Perft_Results
const std::vector<RefPosition>& reference_positions() {
    static const std::vector<RefPosition> positions = {
        {"1. Depart", STARTPOS_FEN,
         {20, 400, 8902, 197281, 4865609, 119060324}},
        {"2. Kiwipete",
         "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
         {48, 2039, 97862, 4085603, 193690690}},
        {"3. Finale",
         "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
         {14, 191, 2812, 43238, 674624, 11030083}},
        {"4. Promotions",
         "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
         {6, 264, 9467, 422333, 15833292}},
        {"5. Talkchess",
         "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
         {44, 1486, 62379, 2103487, 89941194}},
        {"6. Edwards",
         "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10",
         {46, 2079, 89890, 3894594, 164075551}},
    };
    return positions;
}
```

- [ ] **Step 3 : Ajouter la fonction de campagne partagée par `bench` et `deep`**

Toujours dans le namespace anonyme, avant `print_usage` :

```cpp
// Execute chaque position de reference jusqu'a max_depth (bornee par les
// donnees disponibles) et compare aux valeurs attendues.
// Retourne 0 si tout concorde, 1 sinon.
int run_campaign(int max_depth, const PerftOptions& opts, const char* label) {
    std::cout << "=== " << label << " ===\n\n";

    bool all_ok = true;
    uint64_t grand_total = 0;
    const auto campaign_start = std::chrono::steady_clock::now();

    for (const RefPosition& position : reference_positions()) {
        std::cout << position.name << "\n";

        const int depth_limit =
            std::min(max_depth, static_cast<int>(position.counts.size()));

        for (int depth = 1; depth <= depth_limit; ++depth) {
            Chessboard board;
            board.loadFEN(position.fen);

            const auto start = std::chrono::steady_clock::now();
            const PerftReport report = perft(board, depth, opts);
            const double seconds =
                std::chrono::duration<double>(
                    std::chrono::steady_clock::now() - start).count();

            const uint64_t expected = position.counts[depth - 1];
            const bool ok = (report.nodes == expected) && (report.violations == 0);
            if (!ok) all_ok = false;
            grand_total += report.nodes;

            std::cout << "  d" << depth
                      << "  attendu " << std::setw(12) << expected
                      << "  obtenu " << std::setw(12) << report.nodes
                      << "  " << (ok ? "OK" : "ECHEC")
                      << "  (" << std::fixed << std::setprecision(2) << seconds << " s";
            if (seconds > 0.01) {
                std::cout << ", " << static_cast<uint64_t>(report.nodes / seconds)
                          << " n/s";
            }
            std::cout << ")\n";

            if (report.nodes != expected) {
                const int64_t delta =
                    static_cast<int64_t>(report.nodes) - static_cast<int64_t>(expected);
                std::cout << "    [ECART] " << (delta > 0 ? "+" : "") << delta
                          << " noeud(s). FEN : " << position.fen << "\n";
            }
            print_messages(report);
        }
        std::cout << "\n";
    }

    const double total_seconds =
        std::chrono::duration<double>(
            std::chrono::steady_clock::now() - campaign_start).count();

    std::cout << "Total noeuds : " << grand_total << "\n";
    std::cout << "Temps total  : " << std::fixed << std::setprecision(2)
              << total_seconds << " s\n";
    if (total_seconds > 0.0) {
        std::cout << "Vitesse      : "
                  << static_cast<uint64_t>(grand_total / total_seconds) << " noeuds/s\n";
    }
    std::cout << "\nResultat : " << (all_ok ? "SUCCES" : "ECHEC") << "\n";
    return all_ok ? 0 : 1;
}
```

Ajouter `#include <algorithm>` en tête du fichier pour `std::min`.

- [ ] **Step 4 : Brancher les deux commandes**

Remplacer le corps de `print_usage` :

```cpp
void print_usage() {
    std::cout <<
        "Usage :\n"
        "  chess_perft bench  [--strict]              profondeur 1 a 3, rapide\n"
        "  chess_perft deep   [--strict]              profondeur maximale publiee\n"
        "  chess_perft divide <fen|startpos> <n> [--strict] [--check-fen]\n";
}
```

Et dans `main`, avant le `if (command == "divide")` :

```cpp
    if (command == "bench") {
        return run_campaign(3, opts, "Palier rapide (profondeur 1 a 3)");
    }
    if (command == "deep") {
        return run_campaign(6, opts, "Palier profond");
    }
```

- [ ] **Step 5 : Construire**

```bash
cmake --build build --config Release --target chess_perft
```

Attendu : compilation sans erreur.

- [ ] **Step 6 : Lancer le palier rapide**

```bash
./build/Release/chess_perft.exe bench
```

Attendu : 6 blocs, chacun avec `d1`, `d2`, `d3` marqués `OK`, et `Resultat : SUCCES`.
Durée : moins d'une seconde.

Si une ligne affiche `ECHEC`, **ne pas corriger le moteur maintenant**. Noter la position
et la profondeur, terminer les tâches 3 et 4 (les contrôles supplémentaires donneront des
informations utiles), puis traiter le bug dans un cycle séparé comme le prévoit la spec.

Cas particulier : si `d1` échoue sur une position, c'est presque certainement une FEN mal
transcrite, pas un bug du moteur. Revenir à l'étape 1.

- [ ] **Step 7 : Mesurer la vitesse pour la calibration**

```bash
./build/Release/chess_perft.exe divide startpos 5
```

Attendu : `Total : 4865609`. Relever la valeur `noeuds/s` affichée et la noter, elle
servira à fixer les profondeurs du palier rapide en phase 2.

- [ ] **Step 8 : Commit**

```bash
git add src/perft_main.cpp
git commit -F - <<'EOF'
Ajoute les positions de reference et les commandes bench et deep

Six positions standard du Chess Programming Wiki avec leurs comptes
attendus, verifies contre la source. Le palier bench couvre les
profondeurs 1 a 3 en moins d'une seconde, deep va jusqu'a la profondeur
maximale publiee pour chaque position.
EOF
```

---

### Task 3 : Contrôles stricts, trous 1 et 3

**Files:**
- Modify: `src/perft.cpp` (fonction `run_strict_checks`)

**Interfaces:**
- Consumes: `Chessboard::hasAnyLegalMove()`, `Chessboard::getLegalMoveIndices()`
- Produces: aucune nouvelle signature publique, `run_strict_checks` reste interne

- [ ] **Step 1 : Constater que les contrôles ne détectent rien pour l'instant**

```bash
./build/Release/chess_perft.exe bench --strict
```

Attendu : identique à `bench` sans l'option, aucune ligne `[VIOLATION]`. C'est normal, la
fonction est vide. Ce point de départ permet de vérifier à l'étape 4 que les contrôles
s'exécutent réellement.

- [ ] **Step 2 : Implémenter les contrôles**

Dans `src/perft.cpp`, remplacer intégralement la fonction `run_strict_checks` du
namespace anonyme :

```cpp
void run_strict_checks(Chessboard& board,
                       const std::vector<Move>& moves,
                       PerftReport& report) {
    // Trou 3 : hasAnyLegalMove duplique la boucle interne de
    // getLegalMovesForSquare. On confronte la copie a son original.
    const bool has_any = board.hasAnyLegalMove();
    if (has_any != !moves.empty()) {
        report_violation(report,
            "hasAnyLegalMove=" + std::string(has_any ? "true" : "false")
            + " mais getAllLegalMoves en renvoie " + std::to_string(moves.size()));
    }

    // Trou 1 : la couche d'encodage.
    const std::vector<int> indices = board.getLegalMoveIndices();

    if (indices.size() != moves.size()) {
        report_violation(report,
            "encodeMove : " + std::to_string(indices.size()) + " indice(s) pour "
            + std::to_string(moves.size()) + " coup(s) legaux");
    }

    std::unordered_set<int> seen;
    seen.reserve(indices.size() * 2);
    for (int index : indices) {
        if (index < 0 || index > 4671) {
            report_violation(report,
                "indice hors bornes [0, 4671] : " + std::to_string(index));
        }
        if (!seen.insert(index).second) {
            report_violation(report,
                "indice duplique, deux coups encodes pareil : " + std::to_string(index));
        }
    }
}
```

Note : le contrôle de duplication est le plus important des trois. C'est le seul qui
attraperait le scénario décrit dans la spec, où une sous-promotion aberrante produirait
un indice valide tombant dans la plage des plans de cavalier.

Note : les contrôles ne s'exécutent pas sur les feuilles (profondeur 0), où
`perft_rec` retourne immédiatement. C'est délibéré, les feuilles représentent la
quasi-totalité des nœuds et les contrôler multiplierait le coût. Les nœuds internes
suffisent largement, ils se comptent déjà en millions.

- [ ] **Step 3 : Construire**

```bash
cmake --build build --config Release --target chess_perft
```

Attendu : compilation sans erreur.

- [ ] **Step 4 : Prouver que les contrôles s'exécutent réellement**

Un contrôle qui ne se déclenche jamais et un contrôle qui n'existe pas produisent la même
sortie. Il faut donc provoquer une violation volontaire.

Modifier temporairement `run_strict_checks` en remplaçant la première condition par :

```cpp
    if (has_any == !moves.empty()) {  // TEMPORAIRE : condition inversee
```

Reconstruire, puis :

```bash
./build/Release/chess_perft.exe bench --strict
```

Attendu : de très nombreuses lignes `[VIOLATION] hasAnyLegalMove=...` et
`Resultat : ECHEC`. Cela confirme que le contrôle est bien appelé sur chaque nœud interne.

**Rétablir la condition d'origine** (`if (has_any != !moves.empty())`) et reconstruire.

- [ ] **Step 5 : Lancer le palier rapide en mode strict**

```bash
./build/Release/chess_perft.exe bench --strict
```

Attendu : `Resultat : SUCCES`, aucune ligne `[VIOLATION]`.

Toute violation ici est un résultat de première importance. La noter avec la position et
ne pas corriger dans cette tâche.

- [ ] **Step 6 : Mesurer le coût des contrôles**

```bash
./build/Release/chess_perft.exe divide startpos 5
./build/Release/chess_perft.exe divide startpos 5 --strict
```

Comparer les deux valeurs `noeuds/s`. Noter le ratio, il informera la décision de phase 2
sur l'activation par défaut ou non de `--strict` dans le palier rapide.

- [ ] **Step 7 : Commit**

```bash
git add src/perft.cpp
git commit -F - <<'EOF'
Ajoute les contröles stricts sur l'encodage et hasAnyLegalMove

Trois verifications executees sur chaque noeud interne :
- hasAnyLegalMove coincide avec getAllLegalMoves (le copier-coller est
  confronte a son original)
- getLegalMoveIndices ne perd aucun coup
- les indices restent dans [0, 4671] et sont deux a deux distincts

Le contröle de duplication est le seul capable d'attraper une
sous-promotion aberrante aliasant sur un plan de cavalier.
EOF
```

---

### Task 4 : `toFEN()` et contrôle d'aller-retour

**Files:**
- Modify: `src/chessboard.hpp:104` (déclaration, à côté de `loadFEN`)
- Modify: `src/chessboard.cpp` (implémentation, juste après `loadFEN`, vers la ligne 786)
- Modify: `src/perft.cpp` (fonction `run_fen_check`)

**Interfaces:**
- Consumes: membres privés `m_board`, `m_turn`, `m_short_castle_white`, `m_long_castle_white`, `m_short_castle_black`, `m_long_castle_black`, `m_en_passant`, `m_en_passant_file`, `m_half_move_clock`, `m_boardHistory`, `m_initial_ply_offset`
- Produces: `std::string Chessboard::toFEN() const`

- [ ] **Step 1 : Déclarer la méthode**

Dans `src/chessboard.hpp`, juste après la ligne `void loadFEN(const std::string& fen);` :

```cpp
        std::string toFEN() const;
```

- [ ] **Step 2 : Implémenter**

Dans `src/chessboard.cpp`, juste après la fin de `loadFEN` (avant `setKiwipete`) :

```cpp
std::string Chessboard::toFEN() const {
    std::string fen;

    // --- CHAMP 1 : Placement des pieces, de la rangee 8 vers la rangee 1 ---
    for (int rank = 7; rank >= 0; --rank) {
        int empty_run = 0;
        for (int file = 0; file < 8; ++file) {
            const Piece& p = m_board[rank * 8 + file].getPiece();
            if (p.getType() == NONE) {
                ++empty_run;
                continue;
            }
            if (empty_run > 0) {
                fen += std::to_string(empty_run);
                empty_run = 0;
            }
            char c = '?';
            switch (p.getType()) {
            case PAWN:   c = 'p'; break;
            case KNIGHT: c = 'n'; break;
            case BISHOP: c = 'b'; break;
            case ROOK:   c = 'r'; break;
            case QUEEN:  c = 'q'; break;
            case KING:   c = 'k'; break;
            default: break;
            }
            fen += (p.getColor() == WHITE)
                ? static_cast<char>(std::toupper(static_cast<unsigned char>(c)))
                : c;
        }
        if (empty_run > 0) fen += std::to_string(empty_run);
        if (rank > 0) fen += '/';
    }

    // --- CHAMP 2 : Trait ---
    fen += (m_turn == WHITE) ? " w " : " b ";

    // --- CHAMP 3 : Droits de roque ---
    std::string castling;
    if (m_short_castle_white) castling += 'K';
    if (m_long_castle_white)  castling += 'Q';
    if (m_short_castle_black) castling += 'k';
    if (m_long_castle_black)  castling += 'q';
    fen += castling.empty() ? "-" : castling;

    // --- CHAMP 4 : Case en passant ---
    // La FEN attend la case TRAVERSEE par le pion, pas sa case d'arrivee.
    // Si les Blancs ont le trait, les Noirs viennent de pousser de 7 vers 5,
    // la case traversee est donc sur la rangee 6. Symetriquement rangee 3.
    if (m_en_passant && m_en_passant_file >= 0 && m_en_passant_file < 8) {
        fen += ' ';
        fen += static_cast<char>('a' + m_en_passant_file);
        fen += (m_turn == WHITE) ? '6' : '3';
    }
    else {
        fen += " -";
    }

    // --- CHAMP 5 : Compteur de la regle des 50 coups ---
    fen += ' ';
    fen += std::to_string(m_half_move_clock);

    // --- CHAMP 6 : Numero de coup complet ---
    const int plies_played = m_boardHistory.empty()
        ? 0
        : static_cast<int>(m_boardHistory.size()) - 1;
    const int total_ply = m_initial_ply_offset + plies_played;
    fen += ' ';
    fen += std::to_string(total_ply / 2 + 1);

    return fen;
}
```

- [ ] **Step 3 : Implémenter le contrôle d'aller-retour**

Dans `src/perft.cpp`, remplacer la fonction `run_fen_check` du namespace anonyme :

```cpp
void run_fen_check(Chessboard& board, PerftReport& report) {
    const std::string fen = board.toFEN();

    Chessboard probe;
    probe.loadFEN(fen);

    if (probe.getZobristHash() != board.getZobristHash()) {
        report_violation(report, "toFEN/loadFEN incoherent, hash different : " + fen);
    }
}
```

Note : le contrôle instancie un `Chessboard` par nœud, ce qui est coûteux. Il est réservé
aux faibles profondeurs, d'où l'option séparée `--check-fen` plutôt qu'une inclusion dans
`--strict`.

- [ ] **Step 4 : Construire**

```bash
cmake --build build --config Release --target chess_perft
```

Attendu : compilation sans erreur.

- [ ] **Step 5 : Vérifier `toFEN` à l'œil sur la position de départ**

Ajouter temporairement dans `cmd_divide`, juste après `load_position` :

```cpp
    std::cout << "FEN : " << board.toFEN() << "\n\n";
```

Reconstruire, puis :

```bash
./build/Release/chess_perft.exe divide startpos 1
```

Attendu, exactement :
`FEN : rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1`

Vérifier ensuite une position avec droits de roque partiels et compteur non nul :

```bash
./build/Release/chess_perft.exe divide "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8" 1
```

Attendu : la FEN affichée doit être identique à celle passée en argument.

**Retirer le bloc temporaire** et reconstruire.

- [ ] **Step 6 : Prouver que le contrôle se déclenche**

Modifier temporairement `run_fen_check` en inversant la comparaison :

```cpp
    if (probe.getZobristHash() == board.getZobristHash()) {  // TEMPORAIRE
```

Reconstruire, puis :

```bash
./build/Release/chess_perft.exe divide startpos 3 --check-fen
```

Attendu : des lignes `[VIOLATION] toFEN/loadFEN incoherent`.

**Rétablir la comparaison d'origine** (`!=`) et reconstruire.

- [ ] **Step 7 : Lancer le contrôle sur les six positions**

```bash
./build/Release/chess_perft.exe bench --strict --check-fen
```

Attendu : `Resultat : SUCCES`, aucune ligne `[VIOLATION]`.

Rappel de la spec : si une violation apparaît, vérifier d'abord le champ en passant. Le
moteur positionne le drapeau sur toute poussée double, y compris quand aucune capture
n'est possible, ce qui est une divergence de convention connue et non un bug de
génération. Le contrôle Zobrist ne devrait cependant pas en souffrir, puisqu'il compare le
moteur à lui-même avec la même convention des deux côtés.

- [ ] **Step 8 : Commit**

```bash
git add src/chessboard.hpp src/chessboard.cpp src/perft.cpp
git commit -F - <<'EOF'
Ajoute Chessboard::toFEN et son contröle d'aller-retour

Serialisation de la position courante au format FEN standard, inverse
de loadFEN. Necessaire pour que l'outil de diagnostic puisse rapporter
une position exploitable, et utile hors test pour les logs UCI.

Le contröle --check-fen verifie que loadFEN(toFEN(b)) redonne le meme
hash Zobrist que b, sur chaque noeud interne.
EOF
```

---

### Task 5 : Bindings et fuzzer différentiel

**Files:**
- Modify: `src/bindings.cpp:103` (après `move_piece_san`)
- Create: `python_src/dev_tools/fuzz_movegen.py`

**Interfaces:**
- Consumes: `Chessboard::getAllLegalMoves()`, `Chessboard::toFEN()` de la Task 4
- Produces: méthodes Python `Chessboard.get_all_legal_moves()` et `Chessboard.to_fen()`

- [ ] **Step 1 : Exposer les deux méthodes**

Dans `src/bindings.cpp`, dans le bloc `py::class_<Chessboard>`, juste après la ligne
`.def("move_piece_san", &Chessboard::movePieceSAN)` :

```cpp
        .def("get_all_legal_moves", &Chessboard::getAllLegalMoves)
        .def("to_fen", &Chessboard::toFEN)
```

- [ ] **Step 2 : Reconstruire le module Python**

```bash
cmake --build build --config Release --target chess_engine
```

Attendu : compilation sans erreur, `python_src/chess_engine*.pyd` mis à jour.

- [ ] **Step 3 : Vérifier les bindings**

```bash
cd python_src && python -c "import chess_engine; b = chess_engine.Chessboard(); b.set_startup_pieces(); print(b.to_fen()); print(len(b.get_all_legal_moves()))"
```

Attendu :
```
rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1
20
```

- [ ] **Step 4 : Installer la dépendance de diagnostic si nécessaire**

```bash
python -c "import chess; print(chess.__version__)"
```

Si le module est absent : `pip install chess`.

- [ ] **Step 5 : Écrire le fuzzer**

Créer `python_src/dev_tools/fuzz_movegen.py` :

```python
"""
Oracle differentiel pour le generateur de coups.

OUTIL DE DIAGNOSTIC UNIQUEMENT. Ce script depend de python-chess et ne fait
pas partie de la validation du moteur : celle-ci est assuree exclusivement par
chess_perft, qui n'a aucune dependance externe. Voir
docs/superpowers/specs/2026-08-07-perft-design.md, section Architecture.

Usage :
    python dev_tools/fuzz_movegen.py [--positions 100000] [--seed 42]
"""

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess
import chess_engine

STARTPOS_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

REFERENCE_FENS = [
    STARTPOS_FEN,
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
    "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
    "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10",
]

TACTICS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "training_data", "tactics.txt")

PROMO_TO_CHAR = {
    chess_engine.PieceType.QUEEN: "q",
    chess_engine.PieceType.ROOK: "r",
    chess_engine.PieceType.BISHOP: "b",
    chess_engine.PieceType.KNIGHT: "n",
}

REF_PROMO_TO_CHAR = {
    chess.QUEEN: "q",
    chess.ROOK: "r",
    chess.BISHOP: "b",
    chess.KNIGHT: "n",
}

CHAR_TO_PROMO = {
    "q": chess_engine.PieceType.QUEEN,
    "r": chess_engine.PieceType.ROOK,
    "b": chess_engine.PieceType.BISHOP,
    "n": chess_engine.PieceType.KNIGHT,
    "": chess_engine.PieceType.NONE,
}


def engine_moves(board):
    """Ensemble des coups legaux du moteur C++, sous forme (of, orr, df, dr, promo)."""
    result = set()
    for move in board.get_all_legal_moves():
        orig, dest = move.get_orig_square(), move.get_dest_square()
        result.add((
            orig.get_file(), orig.get_rank(),
            dest.get_file(), dest.get_rank(),
            PROMO_TO_CHAR.get(move.get_promotion(), ""),
        ))
    return result


def reference_moves(fen):
    """Meme chose depuis python-chess, avec la meme convention de coordonnees."""
    ref = chess.Board(fen)
    result = set()
    for move in ref.legal_moves:
        result.add((
            move.from_square % 8, move.from_square // 8,
            move.to_square % 8, move.to_square // 8,
            REF_PROMO_TO_CHAR.get(move.promotion, ""),
        ))
    return result


def describe(move_tuple):
    files = "abcdefgh"
    of, orr, df, dr, promo = move_tuple
    return f"{files[of]}{orr + 1}{files[df]}{dr + 1}{promo}"


def is_castle(board, move_tuple):
    of, orr, df, _, _ = move_tuple
    piece = board.get_square(of, orr).get_piece()
    return piece.get_type() == chess_engine.PieceType.KING and abs(of - df) == 2


def pick_move(board, moves, rng, bias=0.35):
    """Selection aleatoire, biaisee vers les roques et les promotions.

    Le biais ne fausse pas le test, qui compare deux generateurs sur une meme
    position. Il concentre l'echantillonnage la ou les bugs se cachent :
    des parties purement aleatoires ne roquent quasiment jamais et
    n'atteignent presque jamais de promotion.
    """
    interesting = [m for m in moves if m[4] or is_castle(board, m)]
    if interesting and rng.random() < bias:
        return rng.choice(interesting)
    return rng.choice(sorted(moves))


def load_start_positions():
    positions = list(REFERENCE_FENS)
    if os.path.exists(TACTICS_PATH):
        with open(TACTICS_PATH, "r", encoding="utf-8") as handle:
            tactics = [line.strip() for line in handle if line.strip()]
        positions.extend(tactics)
        print(f"Charge {len(tactics)} FEN tactiques depuis {TACTICS_PATH}")
    else:
        print(f"Pas de fichier tactique a {TACTICS_PATH}, on continue sans.")
    return positions


def run(target_positions, seed):
    rng = random.Random(seed)
    start_positions = load_start_positions()

    checked = 0
    castles_seen = 0
    promotions_seen = 0
    games = 0

    while checked < target_positions:
        games += 1
        board = chess_engine.Chessboard()
        # 70 % de parties completes depuis le depart, 30 % depuis une FEN tiree
        if rng.random() < 0.7:
            board.load_fen(STARTPOS_FEN)
        else:
            board.load_fen(rng.choice(start_positions))

        for _ in range(300):
            if checked >= target_positions:
                break

            fen = board.to_fen()
            mine = engine_moves(board)
            theirs = reference_moves(fen)
            checked += 1

            if mine != theirs:
                print("\n*** DIVERGENCE ***")
                print(f"FEN : {fen}")
                extra = sorted(describe(m) for m in mine - theirs)
                missing = sorted(describe(m) for m in theirs - mine)
                print(f"Generes en trop par le moteur : {extra}")
                print(f"Manquants dans le moteur      : {missing}")
                return 1

            if not mine:
                break

            move = pick_move(board, mine, rng)
            if move[4]:
                promotions_seen += 1
            elif is_castle(board, move):
                castles_seen += 1

            of, orr, df, dr, promo = move
            if not board.move_piece(of, orr, df, dr, CHAR_TO_PROMO[promo], True):
                print("\n*** REFUS ***")
                print(f"FEN : {fen}")
                print(f"move_piece a refuse un coup qu'il a genere : {describe(move)}")
                return 1

            if board.game_state != chess_engine.GameState.ONGOING:
                break

            if checked % 5000 == 0:
                print(f"  {checked} positions verifiees "
                      f"({castles_seen} roques, {promotions_seen} promotions)",
                      flush=True)

    print(f"\nAucune divergence sur {checked} positions, {games} parties.")
    print(f"Roques joues      : {castles_seen}")
    print(f"Promotions jouees : {promotions_seen}")
    if castles_seen < 1000 or promotions_seen < 1000:
        print("\nATTENTION : moins de 1000 roques ou promotions echantillonnes.")
        print("Le critere de succes de la phase 1 n'est pas atteint, relancer")
        print("avec --positions plus eleve.")
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    sys.exit(run(args.positions, args.seed))


if __name__ == "__main__":
    main()
```

- [ ] **Step 6 : Vérifier que le fuzzer détecte bien une divergence**

Un fuzzer qui ne trouve jamais rien et un fuzzer cassé se ressemblent. Modifier
temporairement `engine_moves` pour retirer un coup au hasard :

```python
def engine_moves(board):
    result = set()
    for move in board.get_all_legal_moves():
        orig, dest = move.get_orig_square(), move.get_dest_square()
        result.add((
            orig.get_file(), orig.get_rank(),
            dest.get_file(), dest.get_rank(),
            PROMO_TO_CHAR.get(move.get_promotion(), ""),
        ))
    if len(result) > 1:                       # TEMPORAIRE
        result.pop()                          # TEMPORAIRE
    return result
```

Puis :

```bash
cd python_src && python dev_tools/fuzz_movegen.py --positions 100
```

Attendu : `*** DIVERGENCE ***` dès la première position, avec une liste non vide dans
`Manquants dans le moteur`.

**Retirer les deux lignes temporaires.**

- [ ] **Step 7 : Lancer une passe courte**

```bash
cd python_src && python dev_tools/fuzz_movegen.py --positions 5000
```

Attendu : `Aucune divergence sur 5000 positions`. Le message d'avertissement sur les 1000
roques est normal à ce volume.

- [ ] **Step 8 : Lancer la passe complète**

```bash
cd python_src && python dev_tools/fuzz_movegen.py --positions 100000
```

Attendu : `Aucune divergence sur 100000 positions`, avec au moins 1000 roques et 1000
promotions. Compter plusieurs minutes.

Si le seuil de 1000 n'est pas atteint, relancer avec `--positions 300000`. Si le biais
reste insuffisant, augmenter la valeur par défaut de `bias` dans `pick_move`.

En cas de divergence : c'est le résultat attendu de la phase 1. Noter la FEN, elle est
directement exploitable par `chess_perft divide` et par la bisection de la Task 6.

- [ ] **Step 9 : Commit**

```bash
git add src/bindings.cpp python_src/dev_tools/fuzz_movegen.py
git commit -F - <<'EOF'
Ajoute le fuzzer differentiel de generation de coups

Compare les ensembles de coups legaux du moteur a ceux de python-chess,
position par position, sur des parties aleatoires biaisees vers les
roques et les promotions que le hasard pur n'atteint presque jamais.

Outil de diagnostic uniquement : la validation reste assuree par
chess_perft, sans dependance externe.

Expose get_all_legal_moves et to_fen dans les bindings.
EOF
```

---

### Task 6 : Bisection automatique

**Files:**
- Modify: `python_src/dev_tools/fuzz_movegen.py`

**Interfaces:**
- Consumes: `engine_moves`, `describe`, `PROMO_TO_CHAR` de la Task 5
- Produces: fonctions `engine_perft`, `engine_divide`, `bisect`, option CLI `--bisect FEN DEPTH`

- [ ] **Step 1 : Ajouter le perft Python et la bisection**

Dans `python_src/dev_tools/fuzz_movegen.py`, avant la fonction `main`, ajouter :

`CHAR_TO_PROMO` est déjà défini au niveau module par la Task 5, ne pas le redéfinir.

```python
def engine_perft(board, depth):
    """Perft de reference cote moteur C++, pilote depuis Python.

    Lent, mais la bisection ne l'appelle qu'a faible profondeur et seulement
    sur la branche fautive.
    """
    if depth == 0:
        return 1
    total = 0
    for move in sorted(engine_moves(board)):
        of, orr, df, dr, promo = move
        board.move_piece(of, orr, df, dr, CHAR_TO_PROMO[promo], False)
        total += engine_perft(board, depth - 1)
        board.undo_move()
    return total


def engine_divide(board, depth):
    """Sous-totaux par coup racine, cote moteur."""
    result = {}
    for move in sorted(engine_moves(board)):
        of, orr, df, dr, promo = move
        board.move_piece(of, orr, df, dr, CHAR_TO_PROMO[promo], False)
        result[describe(move)] = engine_perft(board, depth - 1)
        board.undo_move()
    return result


def reference_divide(fen, depth):
    """Sous-totaux par coup racine, cote python-chess."""
    ref = chess.Board(fen)
    result = {}
    for move in ref.legal_moves:
        ref.push(move)
        result[move.uci()] = reference_perft(ref, depth - 1)
        ref.pop()
    return result


def reference_perft(ref, depth):
    if depth == 0:
        return 1
    total = 0
    for move in ref.legal_moves:
        ref.push(move)
        total += reference_perft(ref, depth - 1)
        ref.pop()
    return total


def bisect(fen, depth):
    """Descend jusqu'a la position et au coup exacts ou les deux moteurs divergent."""
    board = chess_engine.Chessboard()
    board.load_fen(fen)
    path = []

    while depth > 0:
        current_fen = board.to_fen()
        print(f"\nProfondeur {depth} : {current_fen}")

        mine = engine_moves(board)
        theirs = reference_moves(current_fen)
        if mine != theirs:
            print("\n*** DIVERGENCE SUR LA LISTE DE COUPS ***")
            print(f"FEN     : {current_fen}")
            print(f"Chemin  : {' '.join(path) if path else '(racine)'}")
            print(f"En trop : {sorted(describe(m) for m in mine - theirs)}")
            print(f"Manquant: {sorted(describe(m) for m in theirs - mine)}")
            return 1

        if depth == 1:
            print("\nListes identiques a la profondeur 1, aucune divergence trouvee.")
            return 0

        mine_div = engine_divide(board, depth)
        theirs_div = reference_divide(current_fen, depth)

        culprit = None
        for uci, count in sorted(mine_div.items()):
            if theirs_div.get(uci) != count:
                culprit = uci
                print(f"  coup fautif : {uci}, "
                      f"moteur {count}, reference {theirs_div.get(uci)}")
                break

        if culprit is None:
            print("\nAucun ecart a cette profondeur, la divergence a disparu.")
            print("Verifier que la FEN et la profondeur de depart sont correctes.")
            return 0

        of = ord(culprit[0]) - ord("a")
        orr = int(culprit[1]) - 1
        df = ord(culprit[2]) - ord("a")
        dr = int(culprit[3]) - 1
        promo = culprit[4] if len(culprit) == 5 else ""
        board.move_piece(of, orr, df, dr, CHAR_TO_PROMO[promo], False)
        path.append(culprit)
        depth -= 1

    return 0
```

- [ ] **Step 2 : Brancher l'option CLI**

Remplacer la fonction `main` :

```python
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--bisect", nargs=2, metavar=("FEN", "DEPTH"),
                        help="localise la divergence sous cette position")
    args = parser.parse_args()

    if args.bisect:
        sys.exit(bisect(args.bisect[0], int(args.bisect[1])))
    sys.exit(run(args.positions, args.seed))
```

- [ ] **Step 3 : Vérifier sur une position saine**

```bash
cd python_src && python dev_tools/fuzz_movegen.py --bisect "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1" 3
```

Attendu : descente jusqu'à la profondeur 1 puis
`Listes identiques a la profondeur 1, aucune divergence trouvee.`, code de sortie 0.

- [ ] **Step 4 : Vérifier que la bisection localise une divergence réelle**

Réintroduire temporairement le bug artificiel de la Task 5 dans `engine_moves` (les deux
lignes `if len(result) > 1: result.pop()`), puis :

```bash
cd python_src && python dev_tools/fuzz_movegen.py --bisect "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1" 3
```

Attendu : `*** DIVERGENCE SUR LA LISTE DE COUPS ***` avec une FEN, un chemin et une liste
`Manquant` non vide.

**Retirer les deux lignes temporaires.**

- [ ] **Step 5 : Commit**

```bash
git add python_src/dev_tools/fuzz_movegen.py
git commit -F - <<'EOF'
Ajoute la bisection automatique au fuzzer

Quand un compte perft diverge, --bisect descend jusqu'a la position et
au coup exacts en utilisant python-chess comme reference a chaque
niveau. Transforme un ecart de quelques noeuds sur plusieurs millions
en une FEN et un coup precis.
EOF
```

---

### Task 7 : Campagne complète et rapport

**Files:**
- Create: `docs/superpowers/specs/2026-08-07-perft-resultats.md`

**Interfaces:**
- Consumes: toutes les commandes des tâches précédentes
- Produces: le document de résultats qui conditionne la phase 2

- [ ] **Step 1 : Lancer la campagne profonde en mode strict**

```bash
./build/Release/chess_perft.exe deep --strict
```

Compter plusieurs minutes, potentiellement plus de trente selon la vitesse mesurée en
Task 2. Conserver la sortie complète.

- [ ] **Step 2 : Lancer le contrôle FEN à faible profondeur**

```bash
./build/Release/chess_perft.exe bench --strict --check-fen
```

Attendu : `Resultat : SUCCES`.

- [ ] **Step 3 : Relancer le fuzzer avec une graine différente**

```bash
cd python_src && python dev_tools/fuzz_movegen.py --positions 100000 --seed 1337
```

Une seconde graine réduit le risque qu'un échantillonnage particulier ait manqué une
zone. Attendu : aucune divergence, au moins 1000 roques et 1000 promotions.

- [ ] **Step 4 : Rédiger le rapport**

Créer `docs/superpowers/specs/2026-08-07-perft-resultats.md` avec ce squelette, en
remplaçant chaque valeur entre chevrons par la mesure réelle :

```markdown
# Résultats de la campagne perft, phase 1

Date d'exécution : <date>
Commit du moteur : <sortie de git rev-parse --short HEAD>
Machine : <processeur, build Release>

## Vitesse mesurée

| Configuration | Nœuds par seconde |
|---|---|
| perft simple | <valeur> |
| perft --strict | <valeur> |

Ratio du surcoût strict : <valeur>

## Campagne `deep --strict`

| Position | Profondeur | Attendu | Obtenu | Verdict |
|---|---|---|---|---|
| ... | ... | ... | ... | ... |

## Fuzzer différentiel

| Graine | Positions | Roques | Promotions | Divergences |
|---|---|---|---|---|
| 42 | <n> | <n> | <n> | <n> |
| 1337 | <n> | <n> | <n> | <n> |

## Bugs trouvés

<Un paragraphe par bug : FEN, coup, comportement du moteur, comportement attendu.
Écrire "Aucun" si la campagne est intégralement verte.>

## Profondeurs recommandées pour le palier rapide de phase 2

Calculées pour tenir sous 60 secondes à la vitesse mesurée ci-dessus.

| Position | Profondeur | Nœuds | Temps estimé |
|---|---|---|---|
| ... | ... | ... | ... |

Total estimé : <valeur> secondes
```

- [ ] **Step 5 : Commit**

```bash
git add docs/superpowers/specs/2026-08-07-perft-resultats.md
git commit -F - <<'EOF'
Ajoute le rapport de la campagne perft de phase 1

Vitesse mesuree, resultats des six positions de reference en mode
strict, deux passes de fuzzing, et profondeurs recommandees pour le
palier rapide de la phase 2.
EOF
```

- [ ] **Step 6 : Faire le point avant la phase 2**

Présenter le rapport. Deux suites possibles :

- **Campagne verte.** Le générateur est validé. La phase 2 peut démarrer : figeage des
  profondeurs calibrées, intégration CTest, déplacement de `apply_move_by_index` vers
  `Chessboard::decodeMoveIndex` avec la commande `roundtrip`, nettoyage des chemins en dur
  de `src/main.cpp`.
- **Bugs trouvés.** Chacun fait l'objet d'un cycle séparé, comme le prévoit la spec. La
  phase 2 attend que la campagne soit verte, sans quoi le harnais permanent figerait un
  état cassé.

---

## Ce que la phase 1 ne fait pas

Rappel de la spec, pour éviter tout glissement de périmètre pendant l'exécution :

- Pas de correction des bugs trouvés. Ils sont documentés, pas réparés.
- Pas d'intégration CTest, pas de figeage des profondeurs. C'est la phase 2.
- Pas de déplacement de `apply_move_by_index`. C'est la phase 2, et ce déplacement doit
  être validé par une campagne perft déjà verte.
- Pas de table de hachage, pas de parallélisation, pas de framework de test.
- Pas de nettoyage de `src/main.cpp`.

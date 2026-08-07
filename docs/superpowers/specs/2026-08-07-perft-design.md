# Suite de validation perft pour le moteur LapZero-Chess

Date : 2026-08-07
Statut : design validé, en attente du plan d'implémentation

## Problème

Le générateur de coups de `Chessboard` est écrit à la main et n'a aucun test automatisé.
La seule validation existante est le rejeu de PGN via `movePieceSAN` dans `src/main.cpp`,
qui souffre de deux limites structurelles :

1. **Aveugle à la sur-génération.** Rejouer un PGN demande au moteur de retrouver
   l'origine d'un coup connu. Un coup illégal généré en trop n'est jamais sollicité,
   donc jamais détecté, sauf dans le cas particulier où il crée une ambiguïté SAN
   (même type de pièce, même case d'arrivée).
2. **Aveugle aux coups rares omis.** Un coup légal que le moteur ne génère pas ne sera
   signalé que si un joueur du dataset l'a effectivement joué. Les cas critiques
   (prise en passant découvrant le roi, droits de roque perdus par capture de tour lors
   d'une promotion) n'apparaissent quasiment jamais dans des parties de GM.

Le self-play n'apporte pas non plus de garantie : un coup illégal proposé au MCTS est
joué sans erreur ni avertissement, produisant silencieusement une partie fausse dans
le dataset d'entraînement.

Ce trou de validation devient bloquant maintenant, car les optimisations envisagées
(allègement de `Square` / `Piece` / `Move`, remplacement de `m_boardHistory` par un
ring buffer) touchent toutes le cœur du générateur.

## Objectif

Deux livrables, en deux phases :

- **Phase 1, diagnostic.** Répondre par oui ou non à « le générateur est-il correct ? »,
  et si non, localiser précisément chaque bug.
- **Phase 2, harnais.** Un palier de validation rapide (moins d'une minute) relançable
  à chaque modification du moteur.

## Contrainte d'architecture : indépendance de la validation

Le README affirme que le projet ne dépend d'aucune bibliothèque d'échecs externe.
Cette propriété doit rester vraie **y compris pour ses tests**. Le design impose donc
deux couches étanches :

| Couche | Langage | Dépendances | Rôle | Décide pass/fail |
|---|---|---|---|---|
| Validation | C++ | aucune | valeurs de référence en dur, comparaison | **oui** |
| Diagnostic | Python | `python-chess` | oracle, bisection, fuzzing | non |

La couche de diagnostic vit dans `python_src/dev_tools/`. Elle n'est jamais invoquée par
la validation. Sa suppression n'affecte pas le fonctionnement de la couche de validation.

## Architecture

### Composant 1 : `src/perft.hpp` / `src/perft.cpp`

Bibliothèque pure, sans I/O, ajoutée à la cible `chess_core`.

```cpp
uint64_t perft(Chessboard& board, int depth);
std::vector<std::pair<std::string, uint64_t>> perft_divide(Chessboard& board, int depth);
```

Contraintes d'implémentation :

- Appeler `movePiece(..., check_game_end = false)`. Sans ça, chaque nœud paie un
  `hasAnyLegalMove()` complet, ce qui fausse la mesure et multiplie le coût.
- Vérifier la valeur de retour de `movePiece`. Un `false` signifie que le moteur refuse
  de jouer un coup qu'il vient de générer : c'est un bug en soi, à signaler avec la FEN.
- Ne pas utiliser de table de hachage (voir « Hors périmètre »).

Note de performance acceptée : `movePiece` regénère les coups de la case d'origine pour
valider le coup (`chessboard.cpp:1070`). Le perft fait donc la génération deux fois par
nœud, soit environ 2x plus lent qu'un perft optimisé. C'est un échange volontaire :
le chemin de validation de `movePiece` est testé en prime.

### Composant 2 : `Chessboard::toFEN()`

Environ 40 lignes, actuellement absent du moteur (`loadFEN` existe, pas son inverse).

Nécessaire parce que sans lui, ni la bisection ni le fuzzer ne peuvent rapporter une
position exploitable, et une position fautive ne peut pas être collée dans une GUI pour
inspection. Utile hors test : logs UCI, débogage de parties.

Doit produire les six champs standard. Le champ demi-coups vient de `m_half_move_clock`,
le champ coup complet se dérive de `m_boardHistory.size()` et `m_initial_ply_offset`.

Test associé, **en phase 1** : `loadFEN(toFEN(b))` doit produire le même hash Zobrist
que `b`, pour toutes les positions visitées par un perft de faible profondeur. Ce
contrôle est nécessaire dès la phase 1 parce que le fuzzer rapporte ses diagnostics sous
forme de FEN : un `toFEN` fautif rendrait tous ses rapports inexploitables. Il est
implémenté comme une option `--check-fen` de `chess_perft divide`, pas comme la commande
`roundtrip` complète, qui reste en phase 2 car elle dépend de `decodeMoveIndex`.

Réserve connue : `toFEN` ne peut pas restituer le champ en passant à l'identique dans
tous les cas, puisque `checkEnPassant()` positionne le drapeau sur toute poussée double
même quand aucune capture n'est possible (`chessboard.cpp:546`). Le test Zobrist reste
valide car il compare le hash du moteur à lui-même, avec la même convention des deux
côtés. En revanche, une FEN exportée puis comparée à celle de `python-chess` peut
différer sur ce champ. Le fuzzer doit ignorer le champ en passant lors des comparaisons
de FEN, et comparer les ensembles de coups légaux, qui sont la vraie question.

### Composant 3 : `Chessboard::decodeMoveIndex()`

Déplacement de la logique de `MCTS::apply_move_by_index` (`mcts.cpp:290`) vers
`Chessboard`, à côté de son inverse `encodeMove` (`chessboard.cpp:462`).

Justification :

- Rend le round-trip encodage/décodage testable sans instancier un `MCTS`
  (donc sans charger un modèle ONNX).
- Supprime la duplication des tables de directions, aujourd'hui présentes à l'identique
  dans `encodeMove` et `apply_move_by_index`.
- Place les deux fonctions réciproques côte à côte, où une divergence future est visible.

Procédure imposée pour limiter le risque :

1. Ce composant est réalisé **après** que le perft soit en place et passe. Le refactor
   est ainsi validé par un outil déjà éprouvé.
2. Le corps de la fonction est déplacé verbatim. Aucune table de directions n'est retapée.
3. `MCTS::apply_move_by_index` reste en place comme forwarder d'une ligne. Les deux
   appelants existants (`mcts.cpp:134`, `selfplay_manager.cpp:169`) ne sont pas modifiés.
4. Si le refactor déborde de ce cadre, il est abandonné. Le perft garde toute sa valeur
   sans lui.

### Composant 4 : `src/perft_main.cpp`, cible `chess_perft`

Nouvelle cible CMake, liée à `chess_core`, indépendante de `chess_tests`.

| Commande | Rôle |
|---|---|
| `chess_perft bench` | palier rapide, 6 positions standard, profondeurs calibrées, code de sortie 0 ou 1 |
| `chess_perft deep` | palier profond : la profondeur maximale publiée pour chaque position (départ d6, kiwipete d5, position 3 d6, positions 4 à 6 d5) |
| `chess_perft divide "<fen>" <depth>` | décomposition par coup racine |
| `chess_perft roundtrip "<fen>" <depth>` | validation encodage / décodage / `toFEN` |

`startpos` est accepté comme alias de FEN pour toutes les commandes.

### Composant 5 : `python_src/dev_tools/fuzz_movegen.py`

Oracle différentiel, exécution manuelle uniquement.

**Mode fuzzing (défaut).** Joue des coups au hasard avec le moteur C++. À chaque ply,
compare l'ensemble `{(from, to, promo)}` produit par le moteur à celui de `python-chess`.
Comparaison de listes par position, pas de comptage d'arbre, donc plusieurs milliers de
positions par seconde. À la première divergence : affiche la FEN, la différence
symétrique dans les deux sens, et s'arrête. Sur fin de partie, redémarre.

Ce mode est le seul à couvrir un volume de positions arbitraire, là où le perft est
borné à six positions.

**Choix des positions de départ.** Des parties strictement aléatoires depuis la position
initiale échantillonnent mal deux des zones les plus à risque : le roque, presque jamais
joué au hasard parce qu'il exige que quatre conditions coïncident, et la promotion, qui
demande qu'un pion traverse le plateau sans être capturé. Le fuzzer tire donc sa position
de départ dans un mélange :

- position initiale (parties complètes, couvre l'ouverture et le milieu de jeu)
- les six positions de référence (denses en roques, promotions et clouages)
- `training_data/tactics.txt`, déjà présent dans le projet, quelques dizaines de milliers
  de FEN réelles issues des puzzles Lichess

Un biais de sélection supplémentaire est appliqué pendant le jeu : quand un roque ou une
promotion figure parmi les coups légaux, il est choisi avec une probabilité relevée.
Cela ne biaise pas le test, qui compare deux générateurs sur la même position, et
concentre l'échantillonnage là où les bugs se cachent.

**Mode bisection (`--bisect "<fen>" <depth>`).** Quand un perft standard diverge :
compare les sous-totaux par coup racine avec `python-chess`, identifie le coup divergent,
le joue, recommence à profondeur `depth - 1`. Sortie finale : une FEN, un coup, et la
liste des coups générés par chaque moteur depuis cette position.

Prérequis binding : exposer `getAllLegalMoves()` et `toFEN()` dans `bindings.cpp`.
`get_legal_moves(file, rank)` existe déjà mais impose une boucle sur 64 cases.

## Couverture

### Le graphe d'appels réel du générateur

```
getNaiveLegalMoves(f,r)            pseudo-légaux d'une case
        │
        ▼
getLegalMovesForSquare(f,r,…)      + isMoveSafe + isCastlePossible
        │                    │
        ▼                    └─────────► movePiece()   (validation du coup demandé)
getAllLegalMoves()
        │
        ▼
getLegalMoveIndices()              + encodeMove  → indices 0..4671
        │
        ▼
MCTS::expand_node_single (mcts.cpp:168), MCTS::expand_and_backup (mcts.cpp:471)
```

Le MCTS utilise donc `getAllLegalMoves`, transitivement. Il n'existe pas de générateur de
coups parallèle dans le projet, et `getAllLegalMoves` ne doit pas être supprimé : c'est le
tronc commun. La couche `getLegalMoveIndices` existe parce que le MCTS a besoin d'indices
pour adresser le vecteur de policy à 4672 dimensions, pas d'objets `Move`.

Conséquence importante : **un perft écrit sur `getAllLegalMoves` couvre exactement le
générateur utilisé en production.** Trois trous subsistent, décrits ci-dessous.

### Trou 1 : la couche d'encodage (phase 1)

`getLegalMoveIndices` fait `if (idx != -1) indices.push_back(idx)` (`chessboard.cpp:539`).
Si `encodeMove` échouait sur un coup légal, ce coup disparaîtrait de la recherche sans
aucun signal. Deux vérifications, réalisables dès la phase 1 car elles ne dépendent que de
code existant :

- `getLegalMoveIndices().size() == getAllLegalMoves().size()` (aucun coup perdu)
- les indices d'une position sont deux à deux distincts (injectivité de `encodeMove`)

### Trou 2 : le décodage (phase 2)

Le retour de l'index vers des coordonnées, aujourd'hui dans `MCTS::apply_move_by_index`
(`mcts.cpp:290`). Vérification : rejouer via l'index produit le même hash Zobrist que
jouer le `Move` directement. Exige le déplacement décrit au composant 3, donc phase 2.

### Trou 3 : `hasAnyLegalMove` (phase 1)

`hasAnyLegalMove()` (`chessboard.cpp:424`) réimplémente mot pour mot la boucle interne de
`getLegalMovesForSquare` (`chessboard.cpp:382`) : même test de roque, même détection de
prise en passant, même appel à `isMoveSafe`, avec `return true` au lieu d'un `push_back`.
C'est un copier-coller assumé pour l'early exit, et l'intention est légitime :
`evaluateGameState` n'a besoin que d'un booléen, construire un vecteur de `Move` pour
l'obtenir serait du gaspillage.

Le risque est la divergence, une correction appliquée à une copie et pas à l'autre. Et
l'enjeu n'est pas mineur : `hasAnyLegalMove` décide des mats et des pats, donc des
**cibles de value du dataset** (`selfplay_manager.cpp:284`). Un bug à cet endroit
empoisonne l'entraînement sans produire la moindre erreur visible.

Vérification, coût d'un `if` par nœud :

```
hasAnyLegalMove() == !getAllLegalMoves().empty()
```

Ce contrôle compare la copie à son original sur des dizaines de millions de positions.
C'est le meilleur rapport valeur sur effort de toute la suite.

### Récapitulatif

| Chemin de code | Testé par | Phase |
|---|---|---|
| `getNaiveLegalMoves` / `isMoveSafe` / `isCastlePossible` | perft | 1 |
| `getAllLegalMoves` | perft | 1 |
| `movePiece` (validation + application) | perft, assert sur la valeur de retour | 1 |
| `undoMove` et pile de snapshots | perft, implicitement : un undo fautif fausse tous les comptes en aval | 1 |
| `encodeMove` / `getLegalMoveIndices` | perft, trou 1 | 1 |
| `hasAnyLegalMove` | perft, trou 3 | 1 |
| `toFEN` / `loadFEN` | `divide --check-fen` | 1 |
| couverture large de positions | fuzzer | 1 |
| `decodeMoveIndex` | `roundtrip`, trou 2 | 2 |

L'essentiel de la valeur tombe donc en phase 1, sans toucher au MCTS. C'est une raison
supplémentaire de ne pas précipiter le composant 3.

### Doublons identifiés et non traités ici

Pour mémoire, hors périmètre de cette spec :

- Les tables de directions existent à l'identique dans `encodeMove` (`chessboard.cpp:504`),
  `apply_move_by_index` (`mcts.cpp:303`) et `lib.py` (`lib.py:44`, `lib.py:69`). Les tables
  de cavalier sont en cinq exemplaires si l'on compte `isInCheck` (`chessboard.cpp:297`).
  Le composant 3 résorbe la duplication côté C++ ; la copie Python subsiste.
- `hasAnyLegalMove` pourrait être réécrit en termes de `getLegalMovesForSquare` pour un
  coût négligeable, puisqu'il s'arrête à la première case produisant un coup. Non traité
  ici : le contrôle croisé du trou 3 rend la duplication sûre, ce qui est suffisant pour
  l'instant.

## Positions de référence

Les six positions standard du Chess Programming Wiki, chargées par `loadFEN` pour
l'uniformité.

| # | Position | FEN |
|---|---|---|
| 1 | Départ | `rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1` |
| 2 | Kiwipete | `r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1` |
| 3 | Finale | `8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1` |
| 4 | Promotions | `r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1` |
| 5 | Talkchess | `rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8` |
| 6 | Steven Edwards | `r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10` |

**Règle impérative sur les données de référence.** Les comptes attendus **et les FEN
ci-dessus** seront transcrits depuis le Chess Programming Wiki au moment de
l'implémentation, et vérifiés caractère par caractère. Rien ne sera écrit de mémoire :
les FEN du tableau sont indicatives et doivent être re-vérifiées au même titre que les
comptes. Une donnée de référence fausse, FEN ou compte, est le pire mode de défaillance
possible de cet outil : elle envoie chasser un bug inexistant et détruit la confiance
dans l'ensemble de la suite.

Garde-fou peu coûteux : pour chaque position, le compte à profondeur 1 est le nombre de
coups légaux, trivialement vérifiable à l'œil sur un diagramme. Si `perft(1)` est juste
sur les six positions, la FEN est presque certainement correctement transcrite.

La position 2 correspond exactement à `Chessboard::setKiwipete()` (vérifié case par case).
`setKiwipete()` n'est pas supprimé.

## Calibration des paliers

Les profondeurs du palier rapide ne peuvent pas être fixées avant de connaître la vitesse
du moteur en nœuds par seconde. Procédure :

1. Implémenter le perft.
2. Mesurer sur la position de départ à profondeur 5 (4 865 609 nœuds).
3. Choisir les profondeurs du palier `bench` pour tenir sous 60 secondes.
4. Figer les valeurs dans le code avec un commentaire indiquant la vitesse mesurée.

Hypothèse de départ, à ajuster : startpos d5, kiwipete d4, position 3 d6, position 4 d5,
position 5 d4, position 6 d4, soit environ 20 millions de nœuds.

Si la mesure révèle une vitesse trop faible pour ce budget, deux leviers : réduire les
profondeurs, ou paralléliser à la racine (voir « Hors périmètre »).

## Boucle de diagnostic

Séquence type en cas d'échec :

1. `chess_perft bench` signale un écart sur une position et une profondeur.
2. `chess_perft divide "<fen>" <depth>` liste les sous-totaux par coup racine.
3. `python dev_tools/fuzz_movegen.py --bisect "<fen>" <depth>` automatise la descente
   jusqu'à la position et au coup fautifs.
4. Correction, puis relance de `bench` et de `deep`.

## Hors périmètre

- **Table de hachage dans le perft.** Accélère beaucoup mais peut masquer un bug et ajoute
  un suspect en cas de divergence. Un outil de validation doit rester bête.
- **Parallélisation.** Le perft se parallélise trivialement à la racine et OpenMP est déjà
  une dépendance, mais le déterminisme prime en phase 1. À reconsidérer en phase 2 si le
  palier profond est douloureux.
- **Framework de test (Catch2, GoogleTest).** Ajouter une dépendance FetchContent pour
  porter six assertions numériques n'est pas justifié. À reconsidérer si la suite grossit.
- **Comptage détaillé** (captures, prises en passant, roques, promotions par profondeur).
  Utile au diagnostic, mais le fuzzer différentiel rend le même service en mieux.
- **Correction des bugs trouvés.** Hors périmètre de cette spec. Chaque bug découvert fera
  l'objet de son propre cycle.

## Phasage

**Phase 1, diagnostic.** Composants 1, 2, 4 (commandes `bench`, `deep`, `divide`), 5, plus
les contrôles des trous 1 et 3 intégrés au parcours perft (activables par une option
`--strict`, désactivés pour les mesures de vitesse pures). Calibration. Exécution. À
l'issue de cette phase : soit une liste de bugs localisés, soit une preuve chiffrée que le
générateur est correct.

**Phase 2, harnais.** Composant 3 (le refactor `decodeMoveIndex`), commande `roundtrip`,
figeage des profondeurs calibrées, intégration CTest, et nettoyage des chemins en dur
`C:/Users/M47h1/...` de `src/main.cpp` (passage en arguments CLI).

Phase 2 dépend des mesures de la phase 1 et sera détaillée après.

## Critères de succès

Phase 1 :

- `chess_perft deep` retourne 0 sur les six positions.
- `chess_perft deep --strict` ne signale aucune divergence sur les trous 1 et 3
  (`encodeMove` ne perd aucun coup, indices injectifs, `hasAnyLegalMove` cohérent avec
  `getAllLegalMoves`).
- `chess_perft divide --check-fen` ne signale aucune divergence Zobrist sur `toFEN`.
- Le fuzzer tourne sur au moins 100 000 positions sans divergence, en ayant visité au
  moins 1 000 roques et 1 000 promotions (compteurs affichés en fin d'exécution, pour
  éviter de conclure sur un échantillon qui n'a jamais atteint ces cas).
- La vitesse en nœuds par seconde est mesurée et consignée.
- La couche de validation C++ ne dépend d'aucune bibliothèque externe.

Si l'un de ces critères échoue à cause d'un bug du moteur, la phase 1 est malgré tout
réussie : son objectif est de localiser, pas de garantir que tout passe du premier coup.
La correction fait l'objet d'un cycle séparé.

Phase 2 :

- `chess_perft bench` s'exécute en moins de 60 secondes et retourne 0.
- `chess_perft roundtrip` retourne 0 sur les six positions de référence.
- Les deux appelants de `apply_move_by_index` sont inchangés après le refactor.
- `ctest` exécute le palier rapide.

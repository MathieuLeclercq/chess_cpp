# Résultats de la campagne perft, phase 1

Date d'exécution : 2026-08-07
Commit du moteur : `d7b9ed0` (branche `perft`)
Machine : Intel Core Ultra 7 255H, 16 coeurs, build MSVC 19.51 en Release
Environnement : Python 3.13.15 (venv dédié), python-chess 1.11.2

## Vitesse mesurée

Mesure sur la position de départ à profondeur 5 (4 865 609 noeuds).

| Configuration | Temps | Noeuds par seconde |
|---|---|---|
| perft simple | 1,88 s | 2 585 740 |
| perft `--strict` | 2,57 s | 1 891 480 |

Surcoût des contrôles stricts : **1,37x**, soit 37 % de temps supplémentaire.

C'est assez faible pour envisager d'activer `--strict` par défaut dans le palier
rapide de la phase 2.

## Campagne `deep --strict`

**Résultat : SUCCES.** 32 contrôles, tous conformes. Code de sortie 0.
610 195 852 noeuds en 344,34 s, soit 1 772 052 noeuds/s moyens.

Aucune violation des contrôles stricts sur l'ensemble de la campagne : `encodeMove`
n'a perdu aucun coup, tous les indices sont restés dans `[0, 4671]` et deux à deux
distincts, et `hasAnyLegalMove` a systématiquement coïncidé avec
`getAllLegalMoves`.

| Position | Profondeur | Attendu | Obtenu | Temps | Verdict |
|---|---|---|---|---|---|
| 1. Depart | 4 | 197 281 | 197 281 | 0,12 s | OK |
| 1. Depart | 5 | 4 865 609 | 4 865 609 | 2,62 s | OK |
| 1. Depart | 6 | 119 060 324 | 119 060 324 | 63,02 s | OK |
| 2. Kiwipete | 3 | 97 862 | 97 862 | 0,06 s | OK |
| 2. Kiwipete | 4 | 4 085 603 | 4 085 603 | 2,33 s | OK |
| 2. Kiwipete | 5 | 193 690 690 | 193 690 690 | 113,68 s | OK |
| 3. Finale | 4 | 43 238 | 43 238 | 0,03 s | OK |
| 3. Finale | 5 | 674 624 | 674 624 | 0,46 s | OK |
| 3. Finale | 6 | 11 030 083 | 11 030 083 | 7,85 s | OK |
| 4. Promotions | 4 | 422 333 | 422 333 | 0,26 s | OK |
| 4. Promotions | 5 | 15 833 292 | 15 833 292 | 9,23 s | OK |
| 5. Talkchess | 4 | 2 103 487 | 2 103 487 | 1,29 s | OK |
| 5. Talkchess | 5 | 89 941 194 | 89 941 194 | 55,26 s | OK |
| 6. Edwards | 4 | 3 894 594 | 3 894 594 | 2,12 s | OK |
| 6. Edwards | 5 | 164 075 551 | 164 075 551 | 85,92 s | OK |

Les profondeurs 1 à 3 de chaque position sont également conformes et omises du
tableau pour la lisibilité (temps inférieur au centième de seconde).

## Contrôle `toFEN` / `loadFEN`

`chess_perft bench --strict --check-fen` : **SUCCES**, code de sortie 0, aucune
violation sur les six positions aux profondeurs 1 à 3.

Vérification visuelle complémentaire, `toFEN` reproduit au caractère près :

- `rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1`
- `rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8` (roque partiel, compteur non nul, coup 8)
- `r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1` (roque partiel côté Noirs)

Le champ en passant a également été observé correct en cours de partie
(`... w KQkq g6 0 2` après g7g5, case traversée sur la rangée 6).

## Fuzzer différentiel

| Graine | Positions | Parties | Roques | Promotions | Divergences |
|---|---|---|---|---|---|
| 42 | 200 000 | 2 612 | 1 421 | 1 722 | 0 |
| 1337 | 200 000 | 2 593 | 1 367 | 1 731 | 0 |

Total : **400 000 positions comparées coup par coup à python-chess, aucune divergence.**

Le critère de 1 000 roques et 1 000 promotions est atteint sur les deux graines.

Note de méthode : le biais de sélection vers les roques ne suffisait pas. Le roque
étant plafonné à deux par partie, le nombre échantillonné dépend du nombre de
parties et non du nombre de positions. Les parties ont donc été écourtées à
80 plies et la part de la position initiale ramenée à 30 %, ce qui a quadruplé le
taux de roques observé (de 0,18 % à 0,71 % des positions).

## Bugs trouvés dans le moteur

**Aucun.**

Le générateur de coups est validé. Récapitulatif de ce qui a été exercé :

- 610 195 852 noeuds comptés sur les six positions de référence, tous conformes
  aux valeurs du Chess Programming Wiki. Cela couvre `getNaiveLegalMoves`,
  `isMoveSafe`, `isCastleSafe`, `getAllLegalMoves`, la validation de `movePiece`,
  et `undoMove` avec sa pile de snapshots (un `undoMove` fautif faussant tous les
  comptes en aval).
- Les trois contrôles stricts sur ces mêmes 610 M noeuds, sans violation :
  `encodeMove` ne perd aucun coup, indices dans les bornes et injectifs,
  `hasAnyLegalMove` cohérent avec `getAllLegalMoves`. Ce dernier point confronte
  le copier-coller de `hasAnyLegalMove` à son original sur des dizaines de
  millions de positions.
- 400 000 positions comparées coup par coup à python-chess sur deux graines,
  incluant 2 788 roques et 3 453 promotions, sans divergence.
- `toFEN` / `loadFEN` cohérents sur toutes les positions du palier rapide.

Le pronostic initial (25 à 40 % de chances de trouver un bug) était pessimiste.
L'intuition de stabilité était la bonne, elle est maintenant chiffrée.

Ce qui reste non couvert et attend la phase 2 : le décodage
`apply_move_by_index`, seul des trois trous identifiés dans la spec à ne pas
avoir été traité, faute du refactor `decodeMoveIndex` volontairement reporté.

## Défauts trouvés hors moteur

Deux problèmes découverts pendant l'implémentation, sans rapport avec le
générateur de coups.

**Dans le code de perft lui-même (corrigé).** `perft_divide` accumulait ses
violations dans un `PerftReport` local qu'il jetait, et `cmd_divide` n'en
affichait aucune : toute violation détectée via `divide` était perdue
silencieusement. Trouvé par l'étape de preuve de déclenchement, pas par
relecture. Corrigé au commit `3a415bc`.

**Dans la configuration du projet.** Un audit des imports a révélé deux
dépendances réellement absentes de `python_src/requirements.txt` : `onnx`
(importé par `lib.py`) et `whr` (importé par `tournament_elo.py`). Par ailleurs
`torch~=2.4.0` n'a aucune wheel pour Python 3.13, alors que `CMakeLists.txt`
exige `find_package(Python3 3.13 ...)` : les deux fichiers de configuration
étaient mutuellement incompatibles. Traité séparément par le passage à uv
(`pyproject.toml` + `uv.lock`, torch 2.13.0+cu126).

Rectification d'une version antérieure de ce rapport : elle affirmait que
`pybind11-stubgen` et `numpy` manquaient à `requirements.txt`. C'était faux, ils
y figuraient tous les deux. L'erreur venait d'un `Select-String -SimpleMatch`
appliqué à un motif à alternance, qui cherchait la chaîne littérale
`stubgen|pybind`. Ce qui manquait était dans un venv créé à la main sans
installer le fichier de dépendances.

Deux constats de propreté du dépôt, également hors périmètre :
`chess_engine.pdb` (45 Mo), `chess_engine.cp313-win_amd64.pyd` et
`onnxruntime.dll` (14 Mo) sont suivis par git. La règle `*.dll` du `.gitignore`
ne s'applique pas aux fichiers déjà indexés.

## Profondeurs recommandées pour le palier rapide de phase 2

Calculées pour tenir largement sous 60 secondes à 1,89 M noeuds/s, soit la
vitesse mesurée avec `--strict` actif.

| Position | Profondeur | Noeuds au sommet |
|---|---|---|
| 1. Depart | 5 | 4 865 609 |
| 2. Kiwipete | 4 | 4 085 603 |
| 3. Finale | 6 | 11 030 083 |
| 4. Promotions | 5 | 15 833 292 |
| 5. Talkchess | 4 | 2 103 487 |
| 6. Edwards | 4 | 3 894 594 |

Total au sommet : 41 812 668 noeuds. En incluant les profondeurs inférieures que
`run_campaign` parcourt aussi, environ 43,5 M noeuds.

**Temps estimé avec `--strict` : environ 23 secondes.** Il reste donc de la marge
sous le budget de 60 s.

Le palier suivant serait la position 5 à profondeur 5 (89,9 M noeuds à elle
seule), ce qui porterait le total à environ 70 secondes et dépasserait le budget.
Les profondeurs ci-dessus sont donc le bon point d'arrêt.

## Suite

Voir la section « Phasage » de `2026-08-07-perft-design.md`. La phase 2 comprend
le figeage de ces profondeurs, l'intégration CTest, le déplacement de
`apply_move_by_index` vers `Chessboard::decodeMoveIndex` avec la commande
`roundtrip`, et le nettoyage des chemins en dur de `src/main.cpp`.

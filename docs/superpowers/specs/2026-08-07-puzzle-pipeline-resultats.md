# Résultats du pipeline de puzzles

Date d'exécution : 2026-08-08
Commit : `f3139ea` (branche `puzzle-pipeline`)
Source : `lichess_db_puzzle.csv`, 1,08 Go

## Sélection

| Ensemble | Lignes écrites | Taille |
|---|---|---|
| Entraînement (1300-2600) | 100 000 | 40,2 Mo |
| Banc, tranche 1000-1449 | 1 250 | |
| Banc, tranche 1450-1899 | 1 250 | |
| Banc, tranche 1900-2349 | 1 250 | |
| Banc, tranche 2350-2800 | 1 250 | |
| **Banc, total** | **5 000** | **2,0 Mo** |

Les quatre tranches du banc sont exactement remplies. Plage de rating effective de
l'ensemble d'entraînement : 1300 à 2600, conforme.

## Rejets

| Cause | Nombre | Part |
|---|---|---|
| `no_match` | 0 | 0,00 % |
| `ambiguous` | 0 | 0,00 % |
| `game_missing` | 0 | 0,00 % |
| `unreadable` | 0 | 0,00 % |
| **Total** | **0** | **0,00 %** |

Seuil d'alerte de 5 % : très loin d'être atteint. **Aucun puzzle écarté sur 105 000.**

Deux facteurs expliquent ce résultat. D'abord, **100 % des `GameUrl` du CSV portent une
ancre de ply**, donc la règle de lever d'ambiguïté sur les répétitions était toujours
applicable et aucun puzzle n'a eu à être écarté pour ce motif. Ensuite, l'API d'export a
répondu pour la totalité des parties demandées, aucune n'étant supprimée ou privée dans
cet échantillon.

## Historique disponible

| | |
|---|---|
| Longueur minimale | 6 coups |
| Longueur maximale | 232 coups |
| Moyenne | 54,8 coups |
| Moins de 8 plies | 15 puzzles, soit 0,01 % |

Seuls 15 puzzles sur 100 000 disposent de moins de 8 plies d'historique, donc restent
partiellement hors distribution. Ils viennent de débuts de partie, rarement tactiques.

La moyenne de 54,8 coups est très au-delà des 8 dont le tenseur a besoin. Le format
stockant la liste complète, il restera valable si la profondeur de représentation change.

## Téléchargement

| | |
|---|---|
| Parties distinctes | 105 000 |
| Requêtes API | 349 lots de 300 |
| Réponses 429 | **0** |
| Cache disque | `training_data/lichess_games_cache`, 105 000 fichiers |

Aucune limite de débit atteinte, et ce **sans jeton d'API** : les limites anonymes ont
suffi. Le cache rend toute relance quasi gratuite.

## Contrôles

| Contrôle | Résultat |
|---|---|
| Rejeu par le moteur C++, échantillon entraînement | **500/500** sans erreur |
| Rejeu par le moteur C++, échantillon banc | **200/200** sans erreur |
| Pile d'historique après rejeu | 54,6 entrées en moyenne |
| Chevauchement de lignes train / banc | **0** |
| Disjonction des `PuzzleId` | garantie par hachage, couverte par test unitaire |
| Perft après modifications C++ | `bench --strict --check-fen` en **SUCCES** |
| Suite de tests Python | 31 verts, prouvés sans réseau |

Le rejeu de 700 parties complètes par le moteur C++, soit environ 38 000 coups réels,
constitue une validation croisée supplémentaire du générateur de coups contre
`python-chess`, en plus des 610 millions de nœuds du perft et des 400 000 positions du
fuzzer différentiel.

## Écart avec la spec

La spec estimait le fichier du banc à environ 400 Ko. Il fait 2,0 Mo, parce que je
n'avais pas anticipé des historiques de 55 coups en moyenne. Sans conséquence : le
fichier reste largement raisonnable à versionner.

## Suite

Les données d'entraînement sont corrigées : les positions de puzzles portent désormais
l'historique réel de leur partie d'origine et sont structurellement indiscernables des
positions de partie. Le confondant qui empêchait le transfert de l'apprentissage
tactique est supprimé à la source.

Deux étapes restent avant de pouvoir mesurer le gain :

1. **Le banc de puzzles**, qui consommera `data/puzzles_bench.txt` et fera l'objet de son
   propre cycle brainstorming, spec, plan. Il doit mesurer le modèle actuel comme
   référence avant tout réentraînement.
2. **La reprise du self-play** sur les données corrigées.

Point à revoir après la première campagne du banc : la plage de rating d'entraînement de
1300 à 2600 est provisoire par construction. La bande vraiment utile est celle où le
modèle échoue tout juste, et le banc la révélera en rapportant le taux de résolution par
tranche.

Le banc permettra aussi de valider le taux du mode amnésie, ramené de 5 % à 1 % sans
mesure, en évaluant les mêmes positions avec et sans historique.

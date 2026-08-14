# Banc de puzzles : resultats

Modele : `2026_04_23_23h25_iter316_unsupervised.onnx`, iteration 316, global_step 19415
Banc : `..\data\puzzles_bench.txt`, bras avec historique
Recherche : 800 simulations, c_puct 1.4, 16 travailleurs
Duree : 59.2 min

La colonne reseau seul est une inference sans aucune recherche : c'est
la policy brute, la grandeur qui s'effondrait sur les puzzles prives
d'historique. La colonne recherche est le meme reseau avec le MCTS.

Reserve sur la duree, et sur elle seule : un essai de self-play et une
compilation ont tourne en parallele pendant la campagne. Les 59,2 min ne sont
donc pas une mesure de debit propre. Les taux, eux, ne dependent pas de la
charge de la machine.

## Global

| | n | Reseau seul % | Recherche % | Ligne complete % | p med. du bon coup | part de visites med. |
|---|---|---|---|---|---|---|
| global | 5000 | 46.4 (45.1 a 47.8) | 77.3 (76.1 a 78.5) | 68.6 (67.3 a 69.9) | 0.288 | 0.961 |

## Par tranche de rating

| | n | Reseau seul % | Recherche % | Ligne complete % | p med. du bon coup | part de visites med. |
|---|---|---|---|---|---|---|
| 1000-1449 | 1250 | 61.1 (58.4 a 63.8) | 91.4 (89.7 a 92.8) | 89.9 (88.1 a 91.5) | 0.448 | 0.979 |
| 1450-1899 | 1250 | 45.6 (42.9 a 48.4) | 80.0 (77.7 a 82.1) | 77.0 (74.6 a 79.3) | 0.282 | 0.967 |
| 1900-2349 | 1250 | 39.5 (36.8 a 42.3) | 72.1 (69.5 a 74.5) | 65.2 (62.5 a 67.8) | 0.209 | 0.942 |
| 2350-2800 | 1250 | 39.5 (36.8 a 42.3) | 65.8 (63.2 a 68.4) | 42.2 (39.5 a 44.9) | 0.207 | 0.875 |

## Par theme tactique

Un puzzle portant plusieurs themes compte dans chacun : la ventilation
est multi-etiquettes et ne somme pas au total.

| | n | Reseau seul % | Recherche % | Ligne complete % | p med. du bon coup | part de visites med. |
|---|---|---|---|---|---|---|
| fork | 1122 | 44.7 (41.8 a 47.6) | 81.9 (79.5 a 84.0) | 74.3 (71.7 a 76.8) | 0.275 | 0.965 |
| sacrifice | 1067 | 23.0 (20.5 a 25.6) | 48.2 (45.2 a 51.2) | 38.0 (35.1 a 40.9) | 0.061 | 0.329 |
| pin | 884 | 38.1 (35.0 a 41.4) | 69.9 (66.8 a 72.8) | 58.8 (55.5 a 62.0) | 0.195 | 0.934 |
| mateIn2 | 582 | 55.5 (51.4 a 59.5) | 87.5 (84.5 a 89.9) | 85.1 (81.9 a 87.7) | 0.394 | 0.979 |
| discoveredAttack | 558 | 38.0 (34.1 a 42.1) | 70.1 (66.1 a 73.7) | 58.4 (54.3 a 62.4) | 0.169 | 0.931 |
| deflection | 527 | 42.5 (38.4 a 46.8) | 71.5 (67.5 a 75.2) | 60.5 (56.3 a 64.6) | 0.264 | 0.940 |
| attraction | 501 | 30.1 (26.3 a 34.3) | 56.1 (51.7 a 60.4) | 44.1 (39.8 a 48.5) | 0.092 | 0.724 |
| mateIn1 | 396 | 66.9 (62.1 a 71.4) | 96.0 (93.5 a 97.5) | 96.0 (93.5 a 97.5) | 0.544 | 0.981 |
| hangingPiece | 334 | 79.6 (75.0 a 83.6) | 95.8 (93.1 a 97.5) | 80.8 (76.3 a 84.7) | 0.730 | 0.988 |
| mateIn3 | 230 | 40.9 (34.7 a 47.3) | 67.8 (61.5 a 73.5) | 60.4 (54.0 a 66.5) | 0.194 | 0.955 |
| skewer | 192 | 45.3 (38.4 a 52.4) | 77.6 (71.2 a 82.9) | 71.4 (64.6 a 77.3) | 0.284 | 0.963 |
| trappedPiece | 122 | 49.2 (40.5 a 57.9) | 82.8 (75.1 a 88.5) | 73.8 (65.3 a 80.8) | 0.269 | 0.963 |
| capturingDefender | 101 | 37.6 (28.8 a 47.4) | 77.2 (68.1 a 84.3) | 72.3 (62.9 a 80.1) | 0.175 | 0.931 |
| doubleCheck | 57 | 38.6 (27.1 a 51.6) | 70.2 (57.3 a 80.5) | 64.9 (51.9 a 76.0) | 0.176 | 0.966 |
| interference | 55 | 47.3 (34.7 a 60.2) | 87.3 (76.0 a 93.7) | 70.9 (57.9 a 81.2) | 0.344 | 0.966 |
| xRayAttack | 37 | 21.6 (11.4 a 37.2) | 67.6 (51.5 a 80.4) | 56.8 (40.9 a 71.3) | 0.146 | 0.916 |

## Reseau seul contre recherche, comparaison appariee

Les deux colonnes portent sur les memes puzzles, donc McNemar
s'applique. La case qui compte est la premiere : si elle est grosse, la
recherche detruit des tactiques que la policy voyait deja, ce qui est un
diagnostic tout autre qu'un reseau faible.

- Reseau bon, recherche mauvaise : **97**
- Reseau mauvais, recherche bonne : **1641**
- McNemar : chi2 = 1369.88, p = 7.38e-300

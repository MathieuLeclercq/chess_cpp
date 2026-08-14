# Banc de puzzles : resultats

Modele : `2026_04_23_23h25_iter316_unsupervised.onnx`, iteration 316, global_step 19415
Banc : `..\data\puzzles_bench.txt`, bras avec historique
Recherche : 700 simulations, c_puct 1.4, 16 travailleurs
Duree : 11.0 min

Seul le PREMIER coup est score, celui ou il y a une tactique a trouver.
C'est aussi le seul coup que le self-play traite specialement, donc le
banc mesure ce que l'entrainement optimise.

La colonne reseau seul est une inference sans aucune recherche : c'est la
policy brute, la grandeur qui s'effondrait sur les puzzles prives
d'historique. La colonne recherche est le meme reseau avec le MCTS.

## Global

| | n | Reseau seul % | Recherche % | p med. du bon coup | part de visites med. |
|---|---|---|---|---|---|
| global | 2500 | 45.7 (43.7 a 47.6) | 76.7 (75.0 a 78.3) | 0.286 | 0.959 |

## Par tranche de rating

| | n | Reseau seul % | Recherche % | p med. du bon coup | part de visites med. |
|---|---|---|---|---|---|
| 1000-1449 | 625 | 60.0 (56.1 a 63.8) | 90.7 (88.2 a 92.8) | 0.439 | 0.977 |
| 1450-1899 | 625 | 45.1 (41.3 a 49.0) | 78.7 (75.3 a 81.7) | 0.271 | 0.964 |
| 1900-2349 | 625 | 38.4 (34.7 a 42.3) | 71.8 (68.2 a 75.2) | 0.221 | 0.940 |
| 2350-2800 | 625 | 39.2 (35.4 a 43.1) | 65.4 (61.6 a 69.1) | 0.206 | 0.873 |

## Par theme tactique

Un puzzle portant plusieurs themes compte dans chacun : la ventilation
est multi-etiquettes et ne somme pas au total.

| | n | Reseau seul % | Recherche % | p med. du bon coup | part de visites med. |
|---|---|---|---|---|---|
| fork | 574 | 45.3 (41.3 a 49.4) | 81.4 (78.0 a 84.3) | 0.274 | 0.961 |
| sacrifice | 523 | 21.6 (18.3 a 25.3) | 47.6 (43.4 a 51.9) | 0.063 | 0.313 |
| pin | 438 | 37.2 (32.8 a 41.8) | 70.5 (66.1 a 74.6) | 0.202 | 0.929 |
| mateIn2 | 288 | 53.8 (48.0 a 59.5) | 85.8 (81.3 a 89.3) | 0.389 | 0.976 |
| deflection | 273 | 39.6 (33.9 a 45.5) | 72.5 (66.9 a 77.5) | 0.248 | 0.936 |
| discoveredAttack | 270 | 37.4 (31.9 a 43.3) | 70.4 (64.7 a 75.5) | 0.170 | 0.929 |
| attraction | 246 | 28.9 (23.6 a 34.8) | 55.7 (49.4 a 61.8) | 0.094 | 0.704 |
| mateIn1 | 200 | 67.0 (60.2 a 73.1) | 95.0 (91.0 a 97.3) | 0.548 | 0.981 |
| hangingPiece | 167 | 80.8 (74.2 a 86.1) | 94.6 (90.1 a 97.1) | 0.731 | 0.986 |
| mateIn3 | 112 | 41.1 (32.4 a 50.3) | 60.7 (51.5 a 69.3) | 0.144 | 0.913 |
| skewer | 86 | 41.9 (32.0 a 52.4) | 74.4 (64.3 a 82.5) | 0.228 | 0.962 |
| trappedPiece | 58 | 56.9 (44.1 a 68.8) | 84.5 (73.1 a 91.6) | 0.337 | 0.963 |
| capturingDefender | 57 | 31.6 (21.0 a 44.5) | 77.2 (64.8 a 86.2) | 0.159 | 0.920 |
| doubleCheck | 26 | 34.6 (19.4 a 53.8) | 61.5 (42.5 a 77.6) | 0.146 | 0.947 |
| interference | 22 | 59.1 (38.7 a 76.7) | 90.9 (72.2 a 97.5) | 0.426 | 0.976 |
| xRayAttack | 21 | 28.6 (13.8 a 50.0) | 66.7 (45.4 a 82.8) | 0.226 | 0.959 |

## Reseau seul contre recherche, comparaison appariee

Les deux colonnes portent sur les memes puzzles, donc McNemar
s'applique. La case qui compte est la premiere : si elle est grosse, la
recherche detruit des tactiques que la policy voyait deja, ce qui est un
diagnostic tout autre qu'un reseau faible.

- Reseau bon, recherche mauvaise : **48**
- Reseau mauvais, recherche bonne : **823**
- McNemar : chi2 = 687.80, p = 1.34e-151

## Comparaison avec le batch de test a 800 simulations

Section ajoutee a la main, elle ne fait pas partie du rapport genere.

Le premier passage, commite dans l'historique, portait sur les 5000 puzzles a 800
simulations et scorait aussi la ligne complete. En le restreignant aux memes 2500 lignes,
la comparaison est appariee.

| | 800 simulations | 700 simulations |
|---|---|---|
| Recherche, premier coup | 77,4 % | 76,7 % |

- 800 bon et 700 mauvais : **21**
- 800 mauvais et 700 bon : **2**
- McNemar : chi2 = 14,09, p = 0,0002

Deux enseignements.

L'ecart de 0,7 point est reel et significatif, mais minuscule, et il n'est detectable que
parce que la comparaison est appariee. Il n'affecte aucun des deux usages du banc, la
recherche contre la policy brute et une iteration contre la precedente, tous deux a budget
fixe. La seule regle qui en decoule : ne jamais melanger des resultats a 700 et a 800.

L'asymetrie 21 contre 2 montre que la recherche gagnait encore entre 700 et 800
simulations, donc qu'elle n'est pas saturee. Plus de simulations par seconde continueraient
d'apporter de la force, ce qui appuie le chantier du batching UCI.

Enfin, un controle de reproductibilite : la colonne reseau seul est identique au bit pres
entre les deux passages, zero desaccord sur 2500 puzzles et un ecart maximal nul sur
p_correct_reseau. Le chemin policy est donc parfaitement deterministe d'un passage a
l'autre.

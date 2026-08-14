# Banc de puzzles Lichess : conception

Date : 2026-08-14
Statut : spec validée, prête pour le plan d'implémentation

Mesurer la force tactique d'un modèle sur les 5 000 puzzles de `data/puzzles_bench.txt`,
disjoints des 100 000 puzzles d'entraînement par répartition de hachage.

Ce document remplace, sur les points où ils divergent, les notes préparatoires
`2026-08-08-puzzle-bench-notes.md`. Les corrections apportées à ces notes sont listées en
fin de document.

## 1. Ce qui a été mesuré avant de concevoir

Trois chiffres obtenus sur la machine, avec le checkpoint
`2026_04_23_23h25_iter316_unsupervised.pt` exporté en ONNX, et non estimés.

| Mesure | Valeur |
|---|---|
| `mcts_search`, 400 simulations, un seul processus, GPU | 376 sims/s |
| `mcts_search`, 400 simulations, un seul processus, CPU | 373 sims/s |
| Débit agrégé, 16 processus, CPU, `OMP_NUM_THREADS=1` | 2 282 sims/s |
| Débit agrégé, 8 processus, GPU | 352 sims/s |

Deux conclusions structurent tout le reste.

**Le GPU n'apporte rien.** À batch 1 le coût est la latence de lancement des noyaux, environ
2,7 ms par simulation, et le calcul n'est pas le facteur limitant. Cela confirme
quantitativement le diagnostic de `2026-08-08-uci-batching-notes.md`, et explique que le
bot atteigne son niveau actuel avec `uci.py:28` qui instancie `ONNXEvaluator(MODEL_PATH)`
sans demander le GPU. Le banc tourne donc sur CPU, ce qui supprime aussi le besoin de
réparer le chargement du provider CUDA (`onnxruntime_providers_cuda.dll` réclame
`cublasLt64_12.dll`, absente de la machine).

**Le parallélisme par processus, lui, monte à l'échelle**, précisément parce qu'on est
limité par la latence. C'est ce qui rend le banc complet abordable.

## 2. Préalable : un défaut de données corrigé

Le pipeline de la session précédente écrivait un historique s'arrêtant **sur** la position
du puzzle, c'est-à-dire celle depuis laquelle le CSV joue `Moves[0]`, la gaffe de
l'adversaire. `format_line` écrivait pourtant `row.moves[1:]` en solution, en supposant la
gaffe déjà rejouée. Elle était en réalité supprimée.

Constat vérifié contre le CSV Lichess d'origine sur 40 lignes du banc retrouvées : la
solution du banc valait bien `Moves[1:]` dans 40 cas sur 40, et rejouer `Moves[0]` rendait
`solution[0]` légal dans 40 cas sur 40. Sur 200 puzzles, `solution[0]` n'était légal nulle
part.

Corrigé par `append_blunder`, qui prolonge l'historique de la gaffe et **vérifie sa
légalité** plutôt que de la supposer, un appariement levé par `ply_hint` pouvant avoir
retenu la mauvaise occurrence de la position. Quatre tests verrouillent l'invariant, dont
un qui échoue si la correction est neutralisée. Les deux fichiers ont été régénérés.

Aucun entraînement n'avait utilisé ces fichiers, produits en fin de session précédente.

## 3. Périmètre retenu

| Décision | Choix |
|---|---|
| Bras | un seul, **avec** historique réel de partie |
| Budgets | deux colonnes, **réseau seul** et **800 simulations** |
| Critère | premier coup **et** ligne complète, comptés séparément |
| Métrique continue | probabilité de policy du bon coup, et part de visites |
| Implémentation | Python, pool de 16 processus, aucun changement C++ |

Le drapeau `--sans-historique` est implémenté et testé dès le départ, il n'est simplement pas
utilisé par cette première exécution. Il présente les mêmes puzzles avec l'historique vidé,
ce qui mesurerait le confondant repéré dans Nibbler et validerait ou non l'amnésie à 1 %. Le
prévoir maintenant évite de redessiner le banc si cette mesure devient utile.

### Dépendance ajoutée

`onnxruntime` côté Python, absent de l'environnement, est ajouté à `pyproject.toml`. Le
binding n'expose que le constructeur de `ONNXEvaluator`, pas `evaluate`, donc la colonne
réseau seul a besoin de son propre accès au modèle.

Torch aurait évité la dépendance, mais aurait fait tourner les deux colonnes sur deux
runtimes différents. Sur un quasi ex aequo, l'argmax pourrait alors basculer autrement d'un
runtime à l'autre et produire une discordance artificielle, précisément dans les cases que
McNemar examine. La version est alignée sur celle qu'utilise le C++, 1.24.3.

## 4. Architecture

Deux modules, séparés selon ce qui a besoin du moteur.

### `python_src/bench_metrics.py`

Logique pure, testable sans ONNX ni processus.

- `parse_bench_line(ligne) -> BenchPuzzle` : inverse de `build_puzzle_dataset.format_line`.
- `encode_uci_to_index(board, uci) -> int` : coup UCI vers index de policy, via
  `lib.parse_uci_to_coords` et `lib.encode_move`, avec la bascule des noirs.
- `measure_puzzle(puzzle, board, policy_fn, search_fn) -> PuzzleMeasure` : la mesure, dont
  les deux accès au réseau sont **injectés**, sur le modèle du `fetcher` de
  `lichess_games.fetch_games`. C'est ce qui rend tout le scoring testable avec des faux.
- `aggregate(mesures) -> BenchStats` : taux, intervalles de Wilson, McNemar.
- `format_report(stats, contexte) -> str` : le rapport markdown.

### `python_src/puzzle_bench.py`

Orchestration : CLI, export ONNX si besoin, session onnxruntime, pool de processus,
écriture du CSV et du rapport.

L'option `--model` accepte un `.pt` ou un `.onnx`. Sur un `.pt`, le banc exporte vers
`python_src/checkpoints_onnx/<nom>.onnx` s'il manque, ce qui supprime une étape manuelle et
le risque d'un export périmé. `iteration` et `global_step` du checkpoint sont repris dans le
rapport.

## 5. Procédure de mesure

Pour chaque puzzle, dans un processus travailleur :

1. Charger `fen_initiale`, rejouer tous les `coups_uci` côté C++. Le tenseur d'historique se
   construit ainsi tout seul, on ne le reconstruit jamais en Python.
2. **Colonne réseau seul**, sur cette position uniquement. Une inférence onnxruntime sur
   `board.get_alphazero_tensor()`, puis softmax masqué sur `board.get_legal_move_indices()`.
   On en tire l'argmax, la probabilité du bon coup, son rang, et la sortie de la tête value.
3. **Colonne recherche.** `MCTS` neuf, `mcts_search(board, 800, 1.4, add_dirichlet=False)`.
   Le vecteur renvoyé est la distribution de visites normalisée sur 4672, donc l'argmax
   donne le coup choisi et `pi[index_correct]` la part de visites du bon coup.
4. **Ligne complète.** Les coups du solveur sont aux index pairs de la solution. On cherche,
   on compare, on avance le long de la ligne officielle, et on s'arrête au premier écart en
   notant son index.

Le softmax masqué de l'étape 2 reproduit exactement le prior que la recherche utilise. Le
C++ applique un softmax sur les 4672 sorties (`onnx_evaluator.cpp:74-89`) puis renormalise
sur les coups légaux (`mcts.cpp:184-198`) ; renormaliser un softmax global sur un
sous-ensemble est identique à un softmax sur ce seul sous-ensemble. L'égalité est
mathématique, mais elle est quand même verrouillée par un test (section 7).

## 6. Données produites

Une ligne de CSV par puzzle, nombres bruts uniquement, pour que l'agrégation soit refaisable
sans relancer une heure de calcul.

| Champ | Sens |
|---|---|
| `ligne` | index dans le fichier du banc, l'identifiant déterministe faute de `PuzzleId` |
| `rating`, `themes` | reprises de la ligne du banc |
| `plies_historique` | longueur de l'historique rejoué |
| `nb_coups_legaux` | dans la position de départ |
| `coup_reseau` | argmax de la policy masquée |
| `reussi_reseau` | le premier coup de la solution est-il cet argmax |
| `p_correct_reseau` | probabilité de policy du bon coup |
| `rang_correct_reseau` | rang du bon coup parmi les coups légaux, 1 pour l'argmax |
| `value_reseau` | tête value, du point de vue du camp au trait |
| `coup_recherche` | argmax des visites à 800 simulations |
| `reussi_recherche` | premier coup correct après recherche |
| `part_visites_correct` | `pi[index_correct]` |
| `reussi_ligne` | tous les coups solveur de la ligne trouvés |
| `premier_ecart` | index du premier coup solveur erroné, -1 si aucun |
| `nb_recherches` | nombre de recherches lancées pour ce puzzle |
| `duree_s` | durée de traitement du puzzle |

Sortie du CSV dans `data/bench_results/<modele>.csv`, environ 600 Kio, commité. Le garder
permet plus tard un McNemar entre deux modèles sur exactement les mêmes puzzles, ce qui est
le vrai intérêt d'un banc permanent.

Rapport markdown dans `docs/superpowers/specs/`, comme les rapports perft et pipeline.

## 7. Agrégation

Global, puis par tranche de rating (les quatre du banc), puis par thème. Un puzzle portant
plusieurs thèmes compte dans chacun, la ventilation est multi-étiquettes et ne somme pas au
total.

Les taux sont donnés avec un intervalle de Wilson : sur une tranche de 1 250 puzzles, deux
points d'écart ne sont pas nécessairement un écart.

Réseau seul et recherche portant sur les mêmes puzzles, la comparaison est appariée et le
**test de McNemar** s'applique. Les deux cases discordantes sont rapportées séparément, et
celle qui compte est « le réseau avait trouvé, la recherche a perdu ». Si ce nombre est
important, le MCTS détruit des tactiques que la policy voyait déjà, diagnostic très
différent d'un réseau faible.

## 8. Pièges et leur traitement

**Table de transposition.** `MCTS` neuf à **chaque recherche**, pas seulement à chaque
puzzle. La TT est indexée sur le seul Zobrist, or les positions successives d'une même ligne
ont des historiques différents : un hit renverrait une value calculée sous un autre
historique. `step_analysis` est écarté, il conserve `m_analysis_root`.

**Bruit de Dirichlet** explicitement à `False`.

**Déterminisme.** `OMP_NUM_THREADS=1` par travailleur, qui est aussi la configuration la
plus rapide mesurée à 16 processus. Aucune promesse de reproductibilité au bit près, les
égalités d'argmax et l'ordre des sommations flottantes pouvant départager autrement.

**`TT_MAX_MOVES = 128`** (`mcts.hpp:34`) tronque les coups légaux au delà de 128, et ces
coups ne peuvent alors jamais être joués. Maximum rencontré sur 200 puzzles du banc : 52. Le
banc enregistre `nb_coups_legaux` et signale tout puzzle au delà de 128.

**Robustesse des données.** Si un coup d'historique est refusé par le moteur, ou si
`solution[0]` est illégal dans la position obtenue, le puzzle est compté comme erreur de
données et rapporté, sans planter. Le banc revérifie ainsi l'invariant de la section 2 sur
les 5 000 puzzles, ce qui constitue un second contrôle indépendant de la correction.

## 9. Tests

Dans `python_src/tests/test_bench_metrics.py`, avec `policy_fn` et `search_fn` factices,
donc sans ONNX, sans GPU et sans processus :

- réussite au premier coup, sur un succès et sur un échec ;
- réussite en ligne complète, et `premier_ecart` correctement situé ;
- une solution d'un seul coup, et une solution longue ;
- agrégation : taux, borne de Wilson sur un cas connu, McNemar sur une table connue ;
- lecture d'une ligne du banc, aller-retour avec `format_line`.

Deux tests couplés au moteur, qui se sautent proprement si le `.pyd` ou le modèle manquent :

- **accord du softmax** : la probabilité calculée en Python égale le `MoveStats.prior` du
  C++ pour le même `move_idx`, obtenu par `step_analysis` sur une position où ce coup est
  visité. C'est le seul vrai risque de l'approche retenue, et la comparaison porte sur la
  même grandeur, pas sur un substitut ;
- **aller-retour d'encodage** : pour tous les coups légaux de plusieurs positions, dont des
  promotions et des positions avec les noirs au trait, `encode(decode(idx)) == idx`.

## 10. Coût attendu

Environ 1,9 recherche par puzzle en moyenne, compte tenu de l'arrêt au premier écart. Soit
de l'ordre de 5 000 × 1,9 × 800 / 2 282, environ une heure. La colonne réseau seul est
négligeable, une inférence par puzzle.

## 11. Ce que le banc ne dira pas

- Rien sur le confondant historique, le bras correspondant étant inactif.
- Rien sur la force en partie réelle : un taux de résolution de puzzles n'est pas un Elo.
- Rien sur le générateur de coups, déjà couvert par la suite perft.

## 12. Corrections apportées aux notes du 2026-08-08

- La subtilité 6 proposait une colonne à 1 simulation pour mesurer le réseau seul. Une
  inférence directe avec softmax masqué est plus propre : elle donne la probabilité de
  **tous** les coups, y compris ceux qu'une recherche n'aurait jamais visités, ce qui est
  précisément le cas intéressant. `get_analysis_results` filtre sur `visit_count > 0` et ne
  convient donc pas.
- La subtilité 7 envisageait McNemar entre deux modèles. Il s'applique déjà, dès une seule
  exécution, entre réseau seul et recherche.
- La subtilité 9 estimait des heures pour 5 000 puzzles à 800 simulations. Mesure faite :
  environ une heure grâce au parallélisme par processus.
- La subtilité 4 est confirmée et renforcée : `MCTS` neuf à chaque recherche, pas seulement
  à chaque puzzle.

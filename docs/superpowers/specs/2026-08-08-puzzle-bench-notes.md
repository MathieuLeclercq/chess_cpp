# Notes de conception pour le banc de puzzles

Date : 2026-08-08
Statut : notes préparatoires, pas encore une spec validée

Ce document consigne les décisions déjà prises et les subtilités identifiées avant que le
cycle brainstorming / spec / plan du banc ne démarre. Il évite de refaire le raisonnement.

## Objectif

Mesurer la qualité recherche + évaluation à nombre de simulations fixé, sur des puzzles à
solution connue. Sert d'instrument avant/après pour tout changement de MCTS, de réseau ou
de représentation d'entrée.

Sans lui, le seul instrument disponible est le tournoi WHR, et sur 16 parties les barres
d'erreur avalent tout ce qui fait moins de 100 Elo.

## Décisions déjà arrêtées

| Décision | Choix | Motif |
|---|---|---|
| Composition | stratifié par rating, 4 tranches de 1250 | ne sature pas, donne une courbe et non un scalaire |
| Tranches | 1000-1449, 1450-1899, 1900-2349, 2350-2800 | la basse détecte les régressions, la haute garde de la marge |
| Usage | noyau réutilisable + script autonome + appel dans `train_self_play.py` | comparaisons manuelles et courbe dans le temps |
| Données | `data/puzzles_bench.txt`, committé, 5000 lignes | actif stable du dépôt, reproductible |
| Disjonction | par hachage du `PuzzleId` | déjà garantie, un banc partageant des puzzles mesurerait la mémorisation |

## Format d'entrée

`data/puzzles_bench.txt`, une ligne par puzzle :

```
<fen_initiale>|<coups_uci>|<solution_uci>|<rating>|<themes>
```

- `coups_uci` : la partie complète jusqu'à la position du puzzle **incluse**, environ 55
  coups en moyenne, 6 au minimum, 232 au maximum.
- `solution_uci` : la ligne de solution. **Le premier jeton est la réponse attendue.** Les
  jetons suivants alternent réponse forcée de l'adversaire et coup suivant du solveur.

## Subtilités identifiées

### 1. Les puzzles doivent être présentés AVEC leur historique

C'est la contrainte centrale, et elle vient du confondant décrit dans `docs/backlog.md`
§4. Un banc évaluant des FEN nues mesurerait la performance gonflée par le raccourci
« pas d'historique donc position tranchante », pas la force réelle. Il mentirait exactement
comme l'entraînement mentait.

Concrètement : charger `fen_initiale` puis rejouer **tous** les `coups_uci` via
`move_piece_uci`. Ne jamais charger la FEN de la position du puzzle directement.

### 2. Le banc doit aussi savoir présenter SANS historique

Deux mesures sur les mêmes puzzles, avec et sans historique, donnent l'écart entre les deux
régimes. C'est ce qui validera le taux du mode amnésie, ramené de 5 % à 1 % sans mesure.
Si l'écart reste grand à 1 %, remonter le taux.

Sans historique = charger `fen_initiale` et ne rejouer que les coups nécessaires pour
atteindre la position, puis... non : il faut charger la FEN de la position du puzzle
directement. Le fichier ne la contient pas, mais elle s'obtient en rejouant puis en
appelant `to_fen()`, et en rechargeant ce résultat dans un plateau neuf.

### 3. Agnostique à la représentation, par construction

Piloter le moteur par `MCTS.mcts_search(board, sims, c_puct, add_dirichlet=False)` sur un
`Chessboard`. Le nombre de plans reste alors interne au C++ et le banc survit à tout
changement de représentation. **Ne jamais reconstruire le tenseur côté Python.**

### 4. La table de transposition contamine les mesures

`TTEntry` est indexée sur le seul hash Zobrist, qui ne contient ni l'historique, ni le
compteur des 50 coups, ni le flag amnésie (voir `docs/backlog.md` §2). Un hit provenant
d'un puzzle précédent peut donc renvoyer une value calculée sous un autre contexte.

Pour un instrument de mesure c'est inacceptable. **Instancier un `MCTS` neuf par puzzle**,
ou à défaut une TT minuscule. Coût : la construction alloue `tt_size` entrées de 1040
octets, donc passer une petite valeur explicite, par exemple `tt_size=8192`.

Corollaire : ne pas utiliser `step_analysis`, qui conserve `m_analysis_root` entre les
appels. `mcts_search` crée une racine neuve à chaque appel, c'est ce qu'on veut.

### 5. Dirichlet doit être désactivé

`add_dirichlet=False`. Sinon la mesure est bruitée et non reproductible. Le paramètre
existe déjà avec ce défaut.

### 6. La colonne à 1 simulation est la plus informative

À `num_simulations=1`, la racine est développée et aucune recherche n'a lieu : le coup
choisi est celui de plus fort prior, donc la mesure porte sur **le réseau seul**. Aux
simulations élevées, elle porte sur réseau + recherche.

Les deux colonnes séparent la qualité du réseau de celle de la recherche, et la colonne à 1
simulation est celle qui mesure directement le confondant, puisque c'est le prior qui
s'effondrait quand on ajoutait l'historique dans Nibbler.

Attention : avec `mcts_search` à 1 simulation, vérifier ce que renvoie `pi`. La racine est
développée par `expand_node_single`, puis une simulation descend d'un cran. Les comptes de
visite ne refléteront pas directement le prior. Pour mesurer le prior pur, il vaut mieux
lire directement la policy du réseau, ce qui demande un binding sur `ONNXEvaluator` ou de
passer par `get_analysis_results()` qui expose `prior`.

### 7. Comparaison appariée, pas deux proportions indépendantes

Pour comparer deux modèles, les évaluer sur **les mêmes puzzles dans le même ordre**, puis
compter les paires discordantes (A résout, B échoue et l'inverse). Un test de McNemar sur
ces paires a une puissance très supérieure à la comparaison de deux taux indépendants,
parce qu'il élimine la variance due au choix des puzzles.

Concrètement : stocker un vecteur booléen par modèle, pas seulement un taux.

### 8. Le sous-échantillonnage doit être déterministe, et le fichier n'a pas de PuzzleId

Le format ne conserve pas le `PuzzleId`. Le sous-échantillonnage déterministe doit donc se
baser sur l'ordre des lignes, stable puisque le fichier est committé, ou sur un hachage de
la ligne. **Ne pas utiliser `random.sample` sans seed fixe**, sinon deux mesures ne sont
plus comparables.

Si le `PuzzleId` devient nécessaire, il faudra ajouter un champ au format et régénérer.

### 9. Le coût de la mesure est dominé par le batch de 1

C'est la contrainte pratique majeure. Le chemin `mcts_search` évalue **une position par
inférence GPU** (voir `docs/backlog.md` §1). À quelques millisecondes par inférence :

| Puzzles | Simulations | Inférences | Ordre de grandeur |
|---|---|---|---|
| 5000 | 800 | 4 000 000 | plusieurs heures |
| 500 | 800 | 400 000 | dizaines de minutes |
| 5000 | 1 | 5 000 | quelques dizaines de secondes |

Conséquences pour le design :

- Le budget de simulations et la taille de l'échantillon sont des **paramètres**, calibrés
  à la première exécution comme les profondeurs du perft.
- Prévoir deux paliers : un rapide pour la boucle d'entraînement, un complet pour les
  décisions.
- **Le banc deviendra 10 à 40 fois plus rapide une fois le batching UCI en place.** Il est
  donc raisonnable de le construire avec un budget modeste maintenant, puis de relancer
  des campagnes plus riches après.

### 10. Définition de « résolu »

Retenu : **le premier coup joué par le moteur égale le premier jeton de `solution_uci`.**
Lichess génère ses puzzles pour que le coup gagnant soit essentiellement unique, donc le
taux de faux négatifs est faible.

Palier plus strict possible plus tard : jouer toute la ligne, les réponses de l'adversaire
étant forcées par les jetons pairs de `solution_uci`. Cela mesure la profondeur de calcul
et non la seule reconnaissance de motif. À réserver aux thèmes `mateIn2` et `mateIn3`.

### 11. Ce que le banc devra révéler en priorité

- **La bande de rating réellement utile pour l'entraînement.** La plage 1300-2600 est
  provisoire par construction : la bande utile est celle où le modèle échoue tout juste, et
  le taux de résolution par tranche la révélera.
- **Si 1 % d'amnésie suffit**, via l'écart avec et sans historique.
- **Si la correction du confondant a transféré**, en comparant le modèle actuel au modèle
  réentraîné sur les données corrigées. Mesurer le modèle actuel comme référence **avant**
  tout réentraînement.

## Pièges de mise en oeuvre

- `mcts_search` relâche le GIL (`py::call_guard<py::gil_scoped_release>`), donc
  parallélisable côté Python par plusieurs processus. Attention : chaque processus alloue sa
  propre TT et son propre `ONNXEvaluator` CUDA. Regarder ce que fait
  `stockfish_player.py`, qui utilise `mp.Pool` avec `tt_size=131071`.
- `MCTS.mcts_search` renvoie un vecteur `pi` de 4672 flottants. Le coup choisi est
  `argmax(pi)`, à décoder avec `decode_move_index` de `lib.py`, puis à comparer au coup
  attendu converti en indice avec `encode_move`. Comparer des indices plutôt que des
  chaînes évite les questions de convention de promotion.
- Un puzzle dont le rejeu échoue doit être compté et écarté, jamais ignoré en silence. Sur
  les 700 puzzles testés, le rejeu C++ n'a jamais échoué, mais le compteur reste
  nécessaire.

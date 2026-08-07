# Backlog technique

Constats issus de la revue de code du 2026-08-07 et de la campagne perft, classés par
rapport gain sur effort. Rien ici n'est en cours.

## Prochaine tâche décidée

**Banc de test sur puzzles.** Mesurer la qualité recherche + évaluation à nombre de
simulations fixé, sur des puzzles à solution connue. Le perft ne valide que la
génération de coups ; sans cet instrument, aucun changement de MCTS ou de réseau n'est
mesurable autrement que par un tournoi de 16 parties, dont les barres d'erreur
avalent tout ce qui fait moins de 100 Elo.

Contrainte de conception : **les puzzles doivent être présentés avec un historique.**
Un banc sur FEN nues mesurerait la performance gonflée par le raccourci décrit plus bas,
pas la force réelle.

## 1. Batcher la recherche côté UCI

Le plus gros écart du projet. Il existe deux points d'entrée vers le GPU :

- `selfplay_manager.cpp:88` : `evaluate_batch(..., 512)`, batché
- `mcts.cpp:176` : `evaluate(...)` puis `evaluate_batch(..., 1)`, **batch de 1**

Le second est celui qu'emprunte `step_analysis`, donc le bot en partie fait une
inférence GPU par simulation. Le `BATCH_SIZE = 20` de `uci.py` n'est que la granularité
de la boucle Python, pas un batch GPU.

La machinerie existe déjà (`advance_to_leaf`, `expand_and_backup`), écrite pour le
self-play. Il manque le virtual loss pour que plusieurs descentes simultanées dans un
même arbre ne convergent pas vers la même feuille.

Gain attendu : un ordre de grandeur sur le nombre de simulations à temps constant.

## 2. Corriger la clé de la table de transposition

L'entrée du réseau contient 8 plies d'historique, les plans de répétition, le compteur
des 50 coups et le flag amnésie. Le hash Zobrist ne contient **rien de tout ça**. Un hit
peut donc renvoyer une policy et une value calculées sous un contexte différent, ce qui
est du bruit permanent sur toutes les évaluations.

Au passage, `TTEntry` réserve la place pour 128 coups (`std::array<std::pair<int,float>,
128>`), soit 1040 octets par entrée, alors qu'une position en a environ 35 d'utiles.
Avec `tt_size=4_000_000` en self-play, cela fait 4,16 Go alloués et initialisés à zéro.
En passant à `{uint16 move, uint16 prob}` et une capacité de 64, on tombe à environ
270 octets : 4 fois moins de RAM et un probe qui tient dans 4 lignes de cache au lieu
de 16.

## 3. Race dans l'UCI (une ligne)

`parse_position` (`uci.py:97`) modifie `self.board` et appelle `mcts.update_root()` sans
arrêter le thread de recherche. Pendant un ponder, `step_analysis` descend et remonte
l'arbre sur ce même plateau. Les deux opérations ne sont pas atomiques ensemble : entre
le `update_root` et le `move_piece`, une simulation peut passer et descendre dans un
arbre désynchronisé du plateau.

Candidat idéal pour un `Problème lors de l'application du coup dans select_leaf`
aléatoire ou un bestmove illégal en partie. Correctif : `self.stop_search()` en tête de
`parse_position`.

Plus mineur : `MCTS::get_root_q()` (`mcts.cpp:366`) lit l'arbre sans prendre le mutex.

## 4. Confondant historique / tactique — DÉCIDÉ : réduction à 2 positions

**Décision du 2026-08-07 : garder la position courante et la position précédente.**
**35 plans contre 119 aujourd'hui.**

Pas de plan de prise en passant : l'information est entièrement dérivable des deux
positions conservées. Le seul cas où elle manquerait est une FEN nue, traité par
reconstruction de la position précédente (voir plus bas).

Note de vocabulaire, la source de confusion pendant la discussion : on compte le nombre
total de positions dans la pile, pas le nombre de positions passées. L'état actuel est
donc « courante + 7 précédentes », et la cible « courante + 1 précédente ». Le dernier
coup joué est encodé par la différence entre les deux.

Effet mesuré par Mathieu dans Nibbler avant la décision : sur une position de puzzle
présentée sans historique, le prior de recherche du coup tactique est nettement plus
haut, donc le coup est trouvé. Avec historique, il ne l'est pas. Le raccourci est
confirmé empiriquement.

### Layout cible

| Plans | Contenu |
|---|---|
| 0-11 | pièces, position courante (P1 pion→roi 0-5, P2 6-11) |
| 12-13 | répétitions, position courante (rep==2, rep≥3) |
| 14-25 | pièces, position précédente |
| 26-27 | répétitions, position précédente |
| 28 | couleur au trait |
| 29 | nombre de coups normalisé |
| 30-33 | droits de roque (p1 K, p1 Q, p2 K, p2 Q) |
| 34 | compteur des 50 coups normalisé |

Décision mineure laissée ouverte : garder les plans de répétition sur les deux positions
(35 plans, choix fidèle au code actuel qui les calcule par instantané) ou seulement sur la
courante (33 plans). Recommandation : garder les deux, 2 plans ne pèsent rien.

### Prérequis : une constante unique

`119` apparaît dans **19 occurrences fonctionnelles réparties sur 8 fichiers**
(`bindings.cpp`, `chessboard.cpp`, `mcts.cpp`, `onnx_evaluator.cpp`,
`selfplay_manager.cpp/hpp`, `export_batch_onnx.py`, `lib.py`, `model.py`), sans aucune
définition partagée.

Une migration partielle ne produirait pas d'erreur de compilation mais un désaccord
silencieux entre `expected_elements` dans `onnx_evaluator.cpp:46` et la taille réelle du
buffer, donc ONNX Runtime lisant de la mémoire arbitraire. **Introduire la constante
unique avant de migrer**, et l'exposer par les bindings pour que `model.py` et le
constructeur de tenseur C++ ne puissent pas diverger.

### Travail induit côté puzzles

`extract_lichess_puzzle.py` écrit aujourd'hui la FEN **d'après** le coup de l'adversaire :

```python
board.push(chess.Move.from_uci(moves[0]))   # on joue la gaffe
outfile.write(board.fen() + "\n")
```

Chargée telle quelle par `loadFEN`, cette position a `m_boardHistory` de taille 1, donc
la position précédente serait vide et le confondant survivrait. Il faut écrire la FEN
d'**avant** plus le coup, et côté C++ charger puis jouer le coup pour que la pile ait
deux entrées réelles.

C'est le prix d'entrée de ce choix, et c'est aussi ce qui fait que la propriété repose sur
le pipeline plutôt que sur la structure du tenseur (voir la comparaison plus bas).

### Devient du code mort

Le mode amnésie (`setAmnesiaMode`, `m_amnesia_mode`, le tirage à 5 % dans
`roll_next_move`) n'avait pour but que de casser ce confondant. Il devient inutile et doit
être retiré.

### Coût réel : bien inférieur à un réentraînement complet

Un seul tenseur change de forme, `conv_input.weight`, de `[128, 119, 3, 3]` à
`[128, 35, 3, 3]`. Décompte sur l'architecture actuelle :

| | Paramètres | Part du modèle |
|---|---|---|
| Modèle total | ~3,71 M | 100 % |
| `conv_input` aujourd'hui | 137 088 | 3,7 % |
| Canaux repris tels quels (35 sur 119) | 40 320 | — |
| Canaux des 6 positions les plus anciennes, jetés (84) | 96 768 | 2,6 % |
| Paramètres initialisés à neuf | **0** | 0 % |

Conséquence de l'abandon du plan de prise en passant : **aucun poids n'est initialisé
aléatoirement.** La chirurgie devient une pure sélection de canaux d'entrée.

Les 10 blocs résiduels, la tête policy et la tête value se copient à l'identique.
`transfer_weights.py` doit être étendu pour **trancher** le tenseur au lieu de l'ignorer
sur non-correspondance de forme.

### Données de récupération : le replay buffer existant

Les shards stockent les états en `[N, 119, 8, 8]` avec les cibles policy et value déjà
calculées. Il suffit de les trancher vers `[N, 35, 8, 8]` pour réutiliser les 750 000
positions comme jeu de fine-tuning supervisé. Aucune partie à générer, et rien à
recalculer : les 35 canaux retenus sont un sous-ensemble exact des 119 existants.

Réserve : les ~5 % de positions enregistrées en mode amnésie ont leur position précédente
vide. Elles restent utilisables mais représentent une entrée que la nouvelle
représentation ne produira plus jamais. Les exclure du fine-tuning est plus propre.

Le buffer est récupérable depuis l'ancien PC de Mathieu.

### 2 positions contre 1 seule : l'alternative écartée

L'autre candidat sérieux était de ne garder que la position courante, 22 plans. Les deux
options suppriment le confondant, mais pas de la même façon.

| | 1 position, 22 plans | 2 positions, 35 plans (retenu) |
|---|---|---|
| Complétude informationnelle | oui, mais exige un plan de prise en passant | oui, sans plan supplémentaire |
| Indice « ce qui vient de bouger » | perdu | conservé |
| Taille des tenseurs | référence | +60 % |
| Modif du pipeline puzzles | aucune | extraction et chargement C++ |
| Confondant | **impossible** | évité, par convention de pipeline |

Les échecs sont markoviens : position, droits de roque, case de prise en passant,
compteurs de répétition et compteur des 50 coups déterminent entièrement l'état. Le
dernier coup n'ajoute donc **aucune** information sur la légalité ni sur l'issue, au mieux
un indice d'attention, « voilà ce qui vient de changer ».

L'argument en faveur d'une seule position était la dernière ligne du tableau : le drapeau
y devient non représentable, donc aucun bug de pipeline ne peut le réintroduire. Avec deux
positions il est absent parce que l'extraction fait ce qu'il faut, et une future source de
positions sans historique le ramènerait en silence. C'est précisément le mode de
défaillance qui a produit le problème initial : personne n'avait décidé que les puzzles
seraient reconnaissables, cela a émergé d'un détail de pipeline.

**Arbitrage retenu par Mathieu : deux positions.** Il juge plausible que connaître le
dernier coup de l'adversaire aide le réseau, et accepte en échange que la propriété
anti-confondant repose sur le pipeline. Conséquence à assumer : le chargement des
positions tactiques doit rester correct, et toute future source de positions sans
historique est un risque de régression silencieuse. À documenter à côté du code de
chargement, pas seulement ici.

La valeur réelle de l'indice « ce qui vient de bouger » reste inconnue et mesurable : une
fois le banc de puzzles construit, deux chirurgies et deux fine-tunings trancheraient.
Coût GPU non négligeable, à mettre en regard du gain espéré.

### Note de rectification

Une version antérieure de cette entrée écartait l'option à deux positions au motif que la
position précédente serait vide sur un puzzle. C'était faux dès lors que l'extraction
fournit le coup de l'adversaire, ce que la doc Lichess garantit. L'argument s'appliquait
en réalité à une option différente : garder les 8 plans en ne remplissant que la position
précédente, ce qui laisse les 6 plus anciennes vides et déplace le drapeau d'un cran sans
le supprimer.

### Reconstruction de la position précédente pour les FEN nues

Remplace le plan de prise en passant explicite qui figurait dans une version antérieure
de cette entrée. L'information étant dérivable des deux positions conservées, le plan
était redondant partout sauf sur une FEN nue, où la position précédente est vide.

Quand une FEN porte une case de prise en passant, la position précédente est **uniquement
déterminée** : le pion adverse était deux rangées derrière, et rien d'autre n'a changé
puisqu'une poussée double ne capture rien. Dans l'orientation du tenseur, remettre le pion
de `(f, 4)` vers `(f, 6)` et vider `(f, 5)` et `(f, 4)` reconstruit la vraie position, pas
une approximation.

À implémenter dans `loadFEN`, qui pousserait alors deux entrées dans `m_boardHistory` au
lieu d'une. Couvre du même coup tous les cas de FEN nue, y compris `position fen`
d'analyse sans liste de coups, et non seulement les puzzles.

**Piège à ne pas rater :** `m_boardHistory.size()` sert à calculer `total_moves_val` dans
le tenseur (`chessboard.cpp:1462`) et le numéro de coup complet dans `toFEN`. Ajouter une
entrée synthétique décalerait les deux de un. Compenser sur `m_initial_ply_offset`, ou
marquer l'entrée comme synthétique. C'est le seul coût réel de cette approche.

### Trou existant que la décision corrige au passage

`getAlphaZeroTensor` n'a aucun plan de prise en passant : l'information n'existe que par
comparaison de t=0 et t=1. Pour une position chargée par `loadFEN`, `m_boardHistory` ne
contient qu'une entrée, donc t=1 reste vide. **Sur toutes les positions de puzzles, une
prise en passant disponible est donc aujourd'hui invisible pour le réseau**, alors que le
moteur la connaît et la génère dans les coups légaux.

Corollaire utile : `python-chess` écrit déjà la case de prise en passant dans le champ 4
des FEN générées par `extract_lichess_puzzle.py`. Avec un plan explicite, le
`tactics.txt` existant porte donc toute l'information nécessaire, sans modifier
l'extraction.

### Risques

- Les statistiques courantes du BatchNorm suivant `conv_input` deviennent fausses, la
  distribution de sortie de cette couche changeant. Le fine-tuning les réadapte, mais
  attendre un pic de loss et une perte d'Elo temporaire.
- Le réseau utilisait réellement ces canaux ; la magnitude de la perturbation n'est pas
  prévisible sur le papier, seulement mesurable après la chirurgie.
- À décider : garder ou non les plans `total_moves` et `no_progress`. Ce sont les deux
  que le bug `astype(np.uint8)` mettait à zéro dans le dataset supervisé (voir §9), donc
  leur valeur réelle n'a jamais été éprouvée.

### Ordre d'exécution

Le banc de puzzles vient **avant**, c'est l'instrument avant/après de ce changement, et
il doit gérer les deux représentations. Sans lui, impossible de savoir si la suppression
de l'historique a réellement transféré la tactique.

### Options envisagées puis écartées

1. **Jeter les 8 premiers plies des parties issues de puzzles.** Trois lignes dans
   `selfplay_manager`. Tout ce qui entre dans le dataset serait en distribution, mais on
   perdrait la recherche à 4000 simulations sur la position de puzzle elle-même, qui est
   tout l'intérêt de l'injection.
2. **Fabriquer les positions tactiques depuis le corpus PGN existant**, en marquant avec
   Stockfish celles où le meilleur coup écrase le deuxième, pour obtenir des positions
   tranchantes avec leur historique réel. Résout le confondant sans toucher à
   l'architecture, mais demande un pipeline de préparation complet et laisse les 96 plans
   en place, donc n'apporte aucun des gains annexes (taille des tenseurs, coût de
   construction, taille de la première convolution).
3. **Historique synthétique par analyse retrograde**, ou variante plus simple répétant la
   position courante dans les huit créneaux. Les deux créent une troisième distribution,
   « historique fabriqué », et remplacent un confondant par un autre, moins visible. La
   variante répétée interfère en plus avec les plans de répétition.

### Pourquoi c'est un confondant et non un décalage de distribution

La distinction a guidé la décision. Un décalage de distribution se corrige en
élargissant la distribution, ce que fait le mode amnésie. Mais ici la **présence
d'historique est corrélée au label** : historique absent implique presque toujours
« position tranchante », historique présent implique « position ordinaire ». Le réseau
n'a donc pas besoin de comprendre la tactique, il lui suffit de lire les 96 plans comme
un drapeau.

Le mode amnésie à 5 % casse la corrélation parfaite mais pas la corrélation, et surtout
les leçons tactiques restent stockées dans une région de l'espace d'entrée que la partie
réelle ne visite jamais. C'est ça qui bloque le transfert, et c'est pourquoi entraîner
plus longtemps ne suffirait pas.

Deux façons de tuer un confondant : égaliser la covariable entre les groupes (options 1
et 2), ou supprimer la covariable (option retenue).

## 5. Alléger la représentation du plateau

`Square` stocke ses propres `file` et `rank`, redondants avec son index, et `Piece`
porte un `m_value` (matériel 1/3/5/9) inutilisé dans un moteur zero-knowledge. Un
`Square` pèse donc 20 octets pour 4 bits d'information utile, et un plateau 1280 octets.

`updateHistory` (`chessboard.cpp:864`) pousse une copie complète du plateau à chaque
coup, et `undoMove` la recopie en sens inverse. À 700 simulations et ~10 plies de
profondeur, cela fait environ 18 Mo de memcpy par coup joué, pour un historique dont
seules les 8 dernières entrées servent au tenseur.

Un `Move` contient deux `Square` complets plus un `Piece`, soit environ 64 octets pour
ce qui tient dans 16 bits. Et `movePiece` alloue deux `std::vector` sur le tas à chaque
appel, `getLegalMoveIndices` trois de plus.

**Attention à la priorisation :** ces coûts sont réels mais le CPU n'est pas le facteur
limitant. À 1,77 M nœuds/s, la génération de coups coûte environ 0,6 µs par nœud contre
plusieurs millisecondes pour une inférence. Ce chantier se justifie pour la qualité du
code et comme préalable aux bitboards, pas pour l'Elo.

## 6. Séparer validation et exécution dans movePiece

`movePiece` valide le coup en regénérant les coups légaux de la case de départ, puis
l'applique. Le MCTS l'appelle sur des coups **qu'il vient lui-même de générer**, donc
légaux par construction, et paie cette validation à chaque nœud.

Séparer un `makeMove` rapide et confiant d'un `isLegal` explicite appelé seulement par
l'UCI et la GUI supprimerait ce coût. Cela rendrait aussi le nommage évident : aucun nom
ne convient actuellement parce que la fonction fait deux choses.

## 7. Bruit de Dirichlet appliqué de façon incohérente

Trois chemins ajoutent du bruit à la racine (`selfplay_manager.cpp:81`, `:100`, `:205`)
et un chemin n'en ajoute aucun : quand `play_best_move` re-crée une racine et que
`expand_node_single` tombe sur un hit TT, la fonction retourne sans créer d'enfants,
ceux-ci sont créés paresseusement plus tard dans `select_leaf`, et le bruit n'est jamais
appliqué.

Une fraction non contrôlée des coups de self-play est donc cherchée sans exploration à
la racine, ce qui rend la distribution des données d'entraînement inhomogène.

## 8. Copies inutiles au retour du self-play

`return m_finished_games;` (`selfplay_manager.cpp:401`) copie le membre au lieu de le
déplacer. Puis pybind convertit `std::vector<GameResult>` en liste Python en recopiant
chaque `GameResult`. Puis `convert_game_results` (`lib.py:514`) construit une liste
Python d'arrays numpy par position, et `np.array([...])` recopie encore.

Avec 512 parties d'environ 700 Ko, cela fait plusieurs centaines de Mo copiés trois
fois, sur une machine qui a déjà 4 Go de table de transposition.

## 9. Divers, à faible coût

- `checkEnPassant()` (`chessboard.cpp:546`) positionne le drapeau sur toute poussée
  double, même quand aucune capture n'est possible. Deux positions identiques hashent
  donc différemment, ce qui fait rater des répétitions triples et pollue la TT.
- Le roque ne vérifie pas la présence de la tour (`chessboard.cpp:1802`), seulement le
  drapeau de droit et les cases vides. Cohérent en jeu normal, mais un `loadFEN` avec
  des droits incohérents fabriquerait une tour fantôme.
- `astype(np.uint8)` dans `convert_pgn_to_binary.py:49` tronque à zéro les plans 113
  (compteur de coups) et 118 (règle des 50 coups), qui sont des flottants dans [0,1].
  Le préentraînement supervisé a donc vu ces deux plans constants à zéro alors que le
  self-play leur envoie des valeurs réelles. À corriger si une passe supervisée est
  refaite.
- `random.shuffle(files)` dans `sharded_dataset.py:30` a lieu **avant** le découpage par
  worker, et chaque worker a une seed différente : le découpage n'est pas une partition.
  Certains shards sont lus par plusieurs workers, d'autres jamais.
- `ONNXEvaluator` (`onnx_evaluator.cpp:20`) élargit le chemin avec
  `std::wstring(s.begin(), s.end())`, ce qui casse sur tout chemin non-ASCII.
- Softmax sur les 4672 logits (`onnx_evaluator.cpp:74`) alors que seuls ~35 coups légaux
  sont ensuite renormalisés. Équivalent mathématiquement, environ 100 fois plus de
  travail que nécessaire.
- `inline int Piece::getZobristIndex()` (`piece.hpp:40`) utilise un qualificateur
  `Piece::` sur une définition interne à la classe : extension MSVC, refusée par GCC et
  Clang.
- Pas de limite mémoire sur l'arbre d'analyse. Chaque nœud étendu coûte environ 3 Ko
  (35 enfants, chacun un `make_unique` séparé), donc un `go infinite` long grossit sans
  borne. Une arène de nœuds serait un double gain, mémoire et localité.
- Garde manquante dans `play_best_move` (`selfplay_manager.cpp:150`) : si
  `children` est vide, `children.front()` est un comportement indéfini et `best_move`
  reste à -1, ce qui produit ensuite un accès `m_board[-1]`. Inatteignable aujourd'hui
  puisque les FEN de puzzles sont des mats en 1, jamais terminales.
- `TT_MAX_MOVES = 128` tronque silencieusement les positions ayant plus de coups
  légaux : les coups au-delà deviennent inatteignables dans la recherche.
- Environ 60 Mo de binaires suivis par git (`chess_engine.pdb` à 45 Mo, `onnxruntime.dll`
  à 14 Mo). La règle `*.dll` du `.gitignore` ne s'applique pas aux fichiers déjà indexés.
- `id name Lc0 Custom` dans le handshake UCI (`uci.py:64`).

## Phase 2 du perft, non faite

Voir la section « Phasage » de `superpowers/specs/2026-08-07-perft-design.md` :

- figer les profondeurs calibrées (43,5 M nœuds, environ 23 s avec `--strict`)
- intégration CTest
- déplacer `apply_move_by_index` vers `Chessboard::decodeMoveIndex` et ajouter la
  commande `roundtrip`, qui couvre le seul des trois trous identifiés resté non testé
- nettoyer les chemins en dur `C:/Users/M47h1/...` de `src/main.cpp`

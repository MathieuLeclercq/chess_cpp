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

## 4. Confondant historique / tactique — DÉCIDÉ : suppression des plans d'historique

**Décision du 2026-08-07 : passer à T=1 avec un plan de prise en passant explicite.**
Représentation cible : 12 plans de pièces + 2 plans de répétition + 1 plan de prise en
passant + 7 plans constants = 22 plans, contre 119 aujourd'hui.

Effet mesuré par Mathieu dans Nibbler avant la décision : sur une position de puzzle
présentée sans historique, le prior de recherche du coup tactique est nettement plus
haut, donc le coup est trouvé. Avec historique, il ne l'est pas. Le raccourci est
confirmé empiriquement.

### Coût réel : bien inférieur à un réentraînement complet

Un seul tenseur change de forme, `conv_input.weight`, de `[128, 119, 3, 3]` à
`[128, 22, 3, 3]`. Décompte sur l'architecture actuelle :

| | Paramètres | Part du modèle |
|---|---|---|
| Modèle total | ~3,71 M | 100 % |
| `conv_input` | 137 088 | 3,7 % |
| Canaux t=1..7 jetés | 111 744 | 3,0 % |
| Nouveau canal en passant, initialisé à zéro | 1 152 | 0,03 % |

Les 10 blocs résiduels, la tête policy et la tête value se copient à l'identique.
`transfer_weights.py` doit être étendu pour **trancher** le tenseur au lieu de l'ignorer
sur non-correspondance de forme.

### Données de récupération : le replay buffer existant

Les shards stockent les états en `[N, 119, 8, 8]` avec les cibles policy et value déjà
calculées. Il suffit de les trancher vers `[N, 22, 8, 8]` pour réutiliser les 750 000
positions comme jeu de fine-tuning supervisé. Aucune partie à générer.

La prise en passant est récupérable depuis les tenseurs stockés avant de jeter t=1 :
chercher un pion adverse présent en t=1 et absent en t=0, avec la case deux rangées plus
loin en sens inverse. Échoue pour les ~5 % de positions en mode amnésie, où t=1 est déjà
vide.

Le buffer est récupérable depuis l'ancien PC de Mathieu.

### Pourquoi pas T=2 en filet de sécurité

Garder deux pas de temps préserverait la déduction de la prise en passant pour 14 plans
seulement, mais laisserait le confondant à moitié vivant : sur une position de puzzle,
t=1 serait vide, donc le drapeau existe encore, simplement plus faible. On paierait le
réentraînement sans supprimer la cause.

L'argument vaut aussi pour l'idée de reconstruire un historique de taille 1 depuis les
puzzles. C'est faisable, la doc Lichess précise que la FEN du CSV est la position
**avant** le coup de l'adversaire et que `Moves[0]` est ce coup, et
`extract_lichess_puzzle.py` le joue déjà. Mais avec une pile de 8, remplir t=0 et t=1
laisse t=2 à t=7 vides : le drapeau se déplace de t=1 vers t=2, il ne disparaît pas.

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

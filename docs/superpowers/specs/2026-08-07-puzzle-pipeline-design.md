# Pipeline de puzzles avec historique réel

Date : 2026-08-07
Statut : design validé le 2026-08-07

## Problème

Les positions de puzzles injectées dans le self-play sont chargées depuis une FEN nue.
`m_boardHistory` ne contient donc qu'une entrée, et les 7 positions d'historique du tenseur
restent à zéro. Une position de partie, elle, les a toutes.

La présence d'historique est donc **corrélée au label** « position tranchante ». Le réseau
n'a pas besoin d'apprendre la tactique, il lui suffit de lire les 96 plans d'historique
comme un drapeau. Effet mesuré dans Nibbler : sur une position de puzzle présentée sans
historique, le prior de recherche du coup tactique est nettement plus haut, donc le coup
est trouvé ; avec historique, il ne l'est pas.

Conséquence : l'amélioration tactique obtenue par l'injection de puzzles **ne se transfère
pas en partie réelle**, où l'historique est toujours présent.

Voir `docs/backlog.md` §4 pour l'historique complet de la décision, y compris les options
écartées (réduction du nombre de plans, historique synthétique, fabrication de puzzles
maison). Le mode amnésie, lui, est conservé mais requalifié, voir plus bas.

## Objectif

Fournir aux positions de puzzles leur **historique réel**, celui de la partie Lichess dont
elles sont issues. Une position de puzzle avec 8 plies réels et une position de partie avec
8 plies réels ne présentent aucune différence de structure : le confondant disparaît sans
toucher au modèle.

Le pipeline sert deux consommateurs :

- le **self-play**, qui joue depuis ces positions pour produire des données d'entraînement
- le **banc de mesure** (cycle séparé, à venir), qui mesure le taux de résolution

## Ce qui n'est pas modifié

Les 119 plans du tenseur restent inchangés. La réduction à 35 ou 22 plans a été envisagée
puis écartée : elle répondait au même problème, mais au prix d'une chirurgie sur
`conv_input` et d'un fine-tuning, alors que corriger les données suffit. Elle reste en
réserve comme optimisation pure (`docs/backlog.md` §4).

## Entrée prérequise

`lichess_db_puzzle.csv`, téléchargé depuis <https://database.lichess.org/#puzzles> et placé
dans `training_data/`, comme le fait déjà `extract_lichess_puzzle.py`. Le pipeline ne gère
pas ce téléchargement.

Colonnes utilisées : `PuzzleId`, `FEN`, `Moves`, `Rating`, `Themes`, `GameUrl`.

## Architecture

```
lichess_db_puzzle.csv ──┐
                        ├─→ 1. filtrer (thèmes, rating)     ──→ PuzzleId + GameId
                        │
API export _ids ────────┼─→ 2. télécharger par lots de 300, cache disque par GameId
                        │
                        ├─→ 3. rejouer la partie jusqu'à correspondance avec la FEN
                        │       du puzzle ; écarter si aucun ply ne correspond
                        │
                        └─→ 4. répartir par hachage du PuzzleId
                                 ├─→ training_data/puzzles_train.txt  (gitignoré)
                                 └─→ data/puzzles_bench.txt           (committé)
```

Le rejeu des coups a lieu **côté C++ au chargement**, pas dans le pipeline. Alternative
écartée : pré-matérialiser les 8 positions d'historique en FEN. Le constructeur de tenseur
lit `m_boardHistory`, et `setBoard()` n'y pousse rien, donc il faudrait une nouvelle API
C++ de toute façon, pour un résultat moins vérifiable.

## Format de fichier

Texte délimité, une ligne par puzzle. Pas de JSON : le C++ doit le lire sans ajouter de
dépendance.

```
<fen_initiale>|<coups_uci>|<solution_uci>|<rating>|<themes>
```

| Champ | Contenu |
|---|---|
| `fen_initiale` | position de départ de la partie (Lichess autorise des parties depuis position custom) |
| `coups_uci` | coups séparés par des espaces, du début jusqu'à la position du puzzle **incluse**, donc y compris la gaffe de l'adversaire |
| `solution_uci` | la ligne de solution, `Moves[1:]` du CSV |
| `rating` | entier, pour la stratification du banc |
| `themes` | liste séparée par des espaces, telle que fournie par Lichess |

Emplacement du fichier du banc : `data/puzzles_bench.txt`, nouveau dossier à la racine.
`training_data/` étant gitignoré, il ne peut pas accueillir un fichier destiné à être
versionné. À renommer si une autre convention est préférée.

Le C++ ne lit que les deux premiers champs. Le banc lit tout.

**Choix : on stocke la liste complète des coups, pas une fenêtre de 8 plies.** C'est plus
simple, ça s'auto-valide, et ça reste valable si la profondeur de représentation change un
jour. Coût estimé : environ 30 Mo pour l'ensemble d'entraînement, dans un dossier déjà
gitignoré. L'ensemble du banc fait environ 400 Ko et se committe.

## Filtrage

### Thèmes retenus

Motifs tactiques uniquement. Sont exclus les libellés de phase (`opening`, `middlegame`,
`endgame`), de longueur (`short`, `long`, `veryLong`), d'issue (`advantage`, `crushing`,
`equality`) et de provenance (`master`, `superGM`), qui ne décrivent pas un motif.

```
mateIn1 mateIn2 mateIn3 fork pin skewer discoveredAttack doubleCheck
hangingPiece sacrifice deflection trappedPiece attraction interference
xRayAttack capturingDefender
```

Les mats nommés (`backRankMate`, `smotheredMate`, etc.) sont des sous-ensembles de
`mateInN` et sont donc déjà couverts.

### Correspondance exacte, pas par sous-chaîne

`extract_lichess_puzzle.py` fait aujourd'hui `any(theme in themes for theme in
TARGET_THEMES)`, où `themes` est la chaîne brute : une correspondance de sous-chaîne, qui
ignore les frontières de mots.

Précision, vérifiée à l'implémentation : **ce n'est pas un bug actif.** Avec la liste de
thèmes retenue, aucun jeton n'est sous-chaîne d'un autre thème Lichess, donc sur des
données réelles les deux méthodes donnent le même résultat. La fragilité est latente : elle
se déclencherait si un nom de thème court était ajouté à la liste.

Le nouveau pipeline découpe néanmoins la liste sur les espaces et compare des jetons
exacts, et un test synthétique verrouille la propriété pour qu'elle reste vraie si la liste
s'allonge.

### Plages de rating

| Ensemble | Plage | Volume | Motif |
|---|---|---|---|
| Entraînement | 1300 à 2600 | 100 000 | une cible d'entraînement doit être à portée du modèle ; au-delà, le puzzle ne produit pas un exemple mais du bruit |
| Banc | 1000 à 2800 | 5 000, réparti en 4 tranches égales | la tranche basse sert de détecteur de régression, la haute garde de la marge quand le modèle progressera |

Tranches du banc, 1250 puzzles chacune : **1000-1449, 1450-1899, 1900-2349, 2350-2800**.

**La plage d'entraînement est provisoire par construction.** La bande vraiment utile est
celle où le modèle échoue tout juste, et elle n'est pas devinable. Dès que le banc rapporte
le taux de résolution par tranche, la transition entre résoudre et échouer devient visible
et la plage doit être recentrée dessus. À revoir après la première campagne du banc.

## Appariement de position

Le point de robustesse du pipeline. **On ne se fie pas au numéro de ply du `GameUrl`.** On
rejoue les coups de la partie et on compare à la FEN du puzzle à chaque ply.

Comparaison sur les **trois premiers champs** de la FEN : placement, trait, droits de roque.

Sont exclus les compteurs de demi-coups et de coups, dont les conventions peuvent différer
entre le CSV et le PGN reconstitué, **et le champ prise en passant**, pour la même raison :
Lichess ne le renseigne que si une capture est réellement possible, `python-chess` a sa
propre règle, et une divergence de convention provoquerait un rejet à tort sur exactement
les positions les plus intéressantes.

Cas d'ambiguïté : si une partie contient une répétition, plusieurs plies peuvent partager
placement, trait et droits de roque. Règle retenue, dans l'ordre :

1. s'il n'y a qu'un ply correspondant, le prendre
2. s'il y en a plusieurs et que le `GameUrl` porte une ancre de ply, prendre le plus proche
3. sinon, **écarter le puzzle comme ambigu** plutôt que de deviner

Le puzzle est écarté si aucun ply ne correspond, avec un compteur par cause (aucune
correspondance, ambiguïté, partie indisponible). Le procédé transforme une hypothèse sur le
format des données en vérification effective.

## Téléchargement, cache et reprise

`POST https://lichess.org/api/games/export/_ids`, corps en texte brut, IDs séparés par des
virgules, **300 IDs maximum par requête** (vérifié le 2026-08-07 contre la spécification
OpenAPI de Lichess). Réponse en flux PGN.

105 000 puzzles représentent donc au plus 350 requêtes, et en pratique moins : une même
partie engendre souvent plusieurs puzzles, donc le nombre de GameId distincts est inférieur
au nombre de puzzles. Dédupliquer les GameId avant de constituer les lots.

- Chaque réponse brute est écrite dans un cache disque indexé par GameId. Une relance ne
  retélécharge que ce qui manque, donc un échec à mi-parcours ne coûte rien.
- Une requête à la fois, conformément à la consigne de Lichess. Recul exponentiel sur 429.
- Le jeton de `lichess_token.txt` est utilisé s'il existe, pour de meilleures limites de
  débit. Absence de jeton : le pipeline fonctionne, plus lentement.

## Séparation train / banc

Par **hachage du `PuzzleId`**, pas par tirage aléatoire. La répartition reste donc
identique si un CSV plus récent est téléchargé, ce qui rend toute contamination impossible
dans le temps.

Cette disjonction est une exigence, pas une commodité : un banc partageant des puzzles avec
l'entraînement mesurerait la mémorisation, pas la capacité tactique.

## Intégration C++

- `load_tactical_fens` devient un chargeur de puzzles, lisant les deux premiers champs.
- `reset_game` charge la position initiale puis rejoue les coups UCI, pour que
  `m_boardHistory` contienne les entrées attendues. Le chargement actuel par `loadFEN` n'en
  produit qu'une.
### Mode amnésie : conservé, taux abaissé à 1 %

Son but déclaré était de casser ce confondant, et ce but disparaît. Mais il a un second
effet : il entraîne le réseau à fonctionner sans historique, et ce cas subsiste après la
correction, celui de la FEN collée à la main dans une GUI sans liste de coups. C'est
d'ailleurs ainsi que le confondant a été mesuré dans Nibbler.

Le point décisif : une fois les puzzles porteurs d'un historique réel, l'amnésie **ne
corrèle plus avec la tacticité**. Elle cesse d'être un confondant et devient de
l'augmentation de données pure.

Décision : conservé, taux ramené de 5 % à 1 % (`roll_next_move`, `selfplay_manager.cpp:233`).

**Sa raison d'être doit être redocumentée dans le code.** Le commentaire actuel parle de
« shortcut learning avec l'apprentissage sur les FENs de puzzles », ce qui devient faux. Le
nouveau motif est la robustesse aux entrées sans historique. Sans cette mise à jour, un
lecteur futur retrouvera un tirage qui supprime l'historique sans en comprendre la raison.

Le taux de 1 % est une valeur de départ, non mesurée. Le banc pourra la valider : en
évaluant les mêmes puzzles avec et sans historique, il mesure directement l'écart de
performance entre les deux régimes. Si l'écart reste grand à 1 %, remonter le taux.

C'est la seule partie du chantier qui touche le moteur. Le parcours de perft n'est pas
concerné.

Effet secondaire bienvenu : les positions de puzzles auront désormais une position
précédente réelle, ce qui referme le trou de prise en passant décrit dans
`docs/backlog.md` §4 pour ce cas d'usage.

## Validation du pipeline

Le pipeline peut échouer silencieusement de quatre façons, chacune avec son contrôle.

| Défaillance | Contrôle |
|---|---|
| Appariement faux | vérifié par construction : après rejeu, la FEN atteinte doit correspondre aux trois premiers champs de celle du puzzle |
| Historique tronqué | rapporter la distribution du nombre de plies disponibles avant la position du puzzle, et la proportion en ayant moins de 8 (débuts de partie) |
| Fuite train / banc | vérifier que l'intersection des `PuzzleId` des deux fichiers est vide |
| Rejeu C++ divergent | pour un échantillon, comparer l'**ensemble des coups légaux** et les trois premiers champs de `toFEN()` entre le rejeu et un `loadFEN` direct de la FEN du puzzle |

Le dernier contrôle est le plus important : il valide que le C++ reconstruit bien la même
position que celle attendue, et non une position décalée d'un ply.

**Ne pas comparer les hash Zobrist.** `checkEnPassant()` positionne `m_en_passant` sur toute
poussée double, alors que la FEN du CSV suit la convention Lichess, qui ne renseigne la case
que si une capture est réellement possible. Après rejeu, le drapeau serait donc parfois à
vrai là où `loadFEN` le laisse à faux, et les deux hash différeraient légitimement. Le
contrôle produirait de faux échecs sur exactement les positions les plus intéressantes.

L'ensemble des coups légaux est immunisé contre cette divergence : le rejeu ne génère la
prise en passant que si un pion adverse est adjacent, ce qui est précisément la condition de
la convention Lichess. Les deux chemins concordent donc même quand les drapeaux diffèrent.
Le champ prise en passant de `toFEN()` est exclu de la comparaison pour la même raison.

## Hors périmètre

- Le banc de mesure lui-même, qui fera l'objet d'un cycle brainstorming / spec / plan
  séparé et consommera le format défini ici.
- Le fine-tuning ou le réentraînement sur les données corrigées.
- La réduction du nombre de plans du tenseur (`docs/backlog.md` §4, en réserve).
- La reconstruction de la position précédente pour les FEN nues collées à la main dans une
  GUI (`docs/backlog.md` §4, basse priorité).
- La fabrication de puzzles maison depuis le corpus PGN via Stockfish, écartée pour ce
  pipeline car elle perd le rating Lichess, mais valable pour enrichir les données
  d'entraînement plus tard.

## Critères de succès

- `puzzles_train.txt` contient environ 100 000 lignes, `puzzles_bench.txt` environ 5 000
  réparties en 4 tranches de rating.
- Intersection des `PuzzleId` entre les deux fichiers : vide.
- Proportion de puzzles écartés faute d'appariement : rapportée et inférieure à 5 %. Au-delà,
  l'hypothèse sur le format des données est à revoir avant d'aller plus loin.
- Proportion de puzzles disposant de moins de 8 plies d'historique : rapportée. Ce sont les
  seuls à rester partiellement hors distribution, et ils viennent de débuts de partie, donc
  de positions rarement tactiques.
- Sur un échantillon, le rejeu côté C++ produit le même ensemble de coups légaux et les
  mêmes trois premiers champs de `toFEN()` qu'un `loadFEN` direct de la FEN du puzzle. Les
  hash Zobrist ne sont pas comparés, pour la raison exposée en section Validation.
- Une relance du pipeline après interruption ne retélécharge rien de ce qui est déjà en
  cache.

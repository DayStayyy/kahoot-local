# CLAUDE.md — Kahoot LAN

Contexte de projet pour Claude Code. Ce fichier fait autorite : il decrit
le perimetre exact, l'architecture attendue et les standards a respecter.
Ne pas implementer de fonctionnalite absente de ce document.

---

## 1. Objectif

Jeu de quiz type Kahoot fonctionnant en **reseau local (LAN)**, sans aucun
acces internet. Un PC (l'hote) heberge un serveur web. Les joueurs se
connectent depuis le navigateur de leur telephone, sur le meme reseau WiFi,
via l'adresse IP locale du PC.

Cas d'usage : lieu a faible reseau. Le WiFi local suffit ; le debit
internet est sans importance car tout le trafic reste local.

---

## 2. Perimetre

### Dans le scope
- L'hote ouvre une page principale qui **liste les quiz** disponibles
  (scan du dossier `quizzes/`, un seul `.json` au depart) et en **lance un**.
- Une **seule session active** a la fois (mono-salle).
- Les joueurs ouvrent une page de jeu, saisissent un **pseudo**, et sont
  **rattaches automatiquement** a la session en cours.
- Un joueur peut **rejoindre en cours de partie** (lobby non verrouille).
- Deroule des questions avec **minuteur**, **scores** et **points
  degressifs selon la vitesse**.
- L'hote **avance manuellement** (bouton « Question suivante »).

### Hors scope (ne pas implementer)
- Aucune creation / edition de quiz dans l'application (les quiz sont des
  fichiers JSON prepares a la main).
- Aucune base de donnees ni persistance : etat 100 % en memoire, remis a
  zero au redemarrage du serveur.
- Aucune reconnexion / reprise de score : un joueur qui perd le reseau et
  revient **repart de zero**.
- Aucune authentification, aucun compte, aucune gestion multi-salles.

---

## 3. Stack technique

- **Python 3.11+**
- **FastAPI** pour les routes HTTP et les WebSockets.
- **Uvicorn** (`uvicorn[standard]`) comme serveur ASGI (fournit le support
  WebSocket).
- **Jinja2** pour le rendu des pages.
- **Vanilla JS + CSS** cote client : aucun build, pas de `npm`, pas de
  bundler. Objectif : legerete et fiabilite sur machine modeste.

`requirements.txt` :
```
fastapi
uvicorn[standard]
jinja2
```

---

## 4. Architecture et arborescence

```
kahoot-lan/
  main.py              # App FastAPI : routes HTTP + endpoints WebSocket
  game.py              # Logique de jeu et etat de session (POO)
  models.py            # Modeles de donnees (Pydantic / dataclasses)
  quizzes/
    demo.json          # Quiz d'exemple
  templates/
    host.html          # Page hote (choix + deroule du quiz)
    play.html          # Page joueur (pseudo + boutons)
  static/
    host.js
    play.js
    style.css
  requirements.txt
  CLAUDE.md
```

Separation des responsabilites :
- `models.py` : structures (Quiz, Question, Player, session).
- `game.py` : machine a etats de la session, calcul des scores, transitions.
- `main.py` : exposition HTTP/WebSocket, orchestration, diffusion des
  messages. Ne contient pas de logique metier.

### Etats de session
`LOBBY` -> `QUESTION` -> `INTERMISSION` -> (`QUESTION` ...) -> `FINISHED`

- `LOBBY` : les joueurs rejoignent et saisissent un pseudo.
- `QUESTION` : question active, minuteur en cours, reponses acceptees.
- `INTERMISSION` : entre deux questions ; le telephone affiche « la
  prochaine question arrive », l'hote voit un mini-classement.
- `FINISHED` : classement final.

### Communication temps reel
- L'hote et chaque joueur ouvrent un WebSocket.
- Le serveur **pousse** les transitions d'etat (nouvelle question, fin de
  minuteur, intermission, classement).
- Les joueurs **envoient** leur reponse (index du bouton tape).
- Le serveur ne transmet **jamais** l'enonce ni le texte des reponses aux
  telephones : ils ne recoivent que le **nombre de boutons** a afficher.

---

## 5. Modele de donnees (schema JSON des quiz)

Le minuteur est **global** : une seule valeur `time_limit` (secondes)
s'applique a **toutes** les questions.

Le nombre de reponses est **variable, 4 maximum**. Le nombre de bonnes
reponses est **variable** (une ou plusieurs) : `correct_indices` est une
liste d'index.

```json
{
  "title": "Quiz de demonstration",
  "time_limit": 20,
  "questions": [
    {
      "question": "Quelle est la capitale de la France ?",
      "answers": ["Paris", "Lyon", "Marseille", "Bordeaux"],
      "correct_indices": [0]
    },
    {
      "question": "Lesquels sont des langages de programmation ?",
      "answers": ["Python", "HTML", "Rust"],
      "correct_indices": [0, 2]
    }
  ]
}
```

Regles de validation au chargement :
- `answers` : entre 2 et 4 elements.
- `correct_indices` : non vide, chaque index valide dans `answers`.
- `time_limit` : entier strictement positif.
- Un fichier invalide leve une exception claire et n'est pas propose au
  lancement.

---

## 6. Regles de jeu

### Reponse du joueur
Le telephone n'affiche **que des boutons colores** (pas de texte). Mapping
fixe par position :
- index 0 : triangle rouge
- index 1 : losange bleu
- index 2 : rond jaune
- index 3 : carre vert

Le joueur **tape un seul bouton**. La reponse est **correcte** si l'index
tape appartient a `correct_indices`. Un seul envoi de reponse par question ;
les envois suivants sont ignores.

### Bareme (points degressifs selon la vitesse)
Pour une bonne reponse :
```
points = round(1000 * (1 - (temps_reponse / time_limit) / 2))
```
- `temps_reponse` : secondes ecoulees depuis l'affichage de la question.
- Reponse quasi instantanee -> ~1000 pts.
- Reponse au dernier moment -> ~500 pts.

Mauvaise reponse ou absence de reponse : **0 point**.

### Ecran hote (page principale)
- Avant lancement : liste des quiz, bouton de lancement.
- Pendant une question : **enonce + texte des reponses** + minuteur +
  nombre de joueurs ayant repondu.
- En intermission : mini-classement + bouton « Question suivante ».
- A la fin : classement final.

### Ecran joueur (page de jeu)
- Saisie du pseudo, puis attente.
- Pendant une question : les N boutons colores.
- En intermission : « la prochaine question arrive ».
- A la fin : score / rang du joueur.

---

## 7. Standards de code Python

- **PEP 8** strict :
  - Indentation 4 espaces, pas de tabulations.
  - `snake_case` pour variables et fonctions.
  - Lignes <= 79 caracteres (<= 72 pour docstrings et commentaires).
  - Espaces autour des operateurs et apres les virgules.
- **Type hints** obligatoires sur toutes les signatures.
- **Docstrings Google Style** obligatoires pour chaque fonction et methode
  (but, Args, Returns, Raises le cas echeant).
- **Programmation orientee objet** : la session de jeu, les joueurs et le
  quiz sont modelises par des classes.
- **Gestion des erreurs explicite** : exceptions typees, messages clairs et
  utiles au debogage.
- **Pas d'emojis, pas de langage informel, pas de commentaires redondants.**
- Rester **strictement dans le perimetre** ; en cas d'ambiguite, demander
  validation avant de coder.

---

## 8. Lancement sous Windows

### Installation
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Demarrage du serveur
Ecouter sur toutes les interfaces pour etre joignable depuis les
telephones du reseau (et pas seulement en localhost) :
```bat
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Trouver l'IP locale du PC
```bat
ipconfig
```
Reperer l'« Adresse IPv4 » de l'interface WiFi (ex. `192.168.x.x`).
- Hote : `http://localhost:8000/`
- Joueurs : `http://192.168.x.x:8000/play`

### Pare-feu (point de blocage frequent)
Le pare-feu Windows Defender peut bloquer les connexions entrantes sur le
port 8000. Si les telephones n'arrivent pas a se connecter, autoriser
Python / le port 8000 en entree, ou desactiver temporairement le pare-feu
sur le reseau prive.

### Reseau : mise en place du point d'acces
Un PC **sans internet peut heberger le serveur** ; creer un point d'acces
et partager internet sont deux choses distinctes.

- **Option A (recommandee, la plus fiable)** : un telephone active son
  partage de connexion (hotspot), meme donnees mobiles coupees. Le PC
  **rejoint** ce WiFi puis lance le serveur. Les joueurs rejoignent le meme
  hotspot. Rejoindre un WiFi ne reclame jamais internet et echoue rarement.
- **Option B (PC en point d'acces)** : « Point d'acces mobile » de Windows.
  Attention : selon la version et le pilote WiFi, Windows peut refuser de
  l'activer s'il n'y a aucune connexion a partager. A tester en amont ;
  sinon se rabattre sur l'option A.

---

## 9. Hypotheses a confirmer

- Modele de reponse a choix unique (un tap), correct si l'index est dans
  `correct_indices`. Si un jour un vrai multi-selection est souhaite, ce
  point devra etre revu.
- Une seule session simultanee.
- Pas de son, pas d'animations complexes : priorite a la robustesse.

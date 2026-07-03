# Kahoot LAN

Jeu de quiz type Kahoot fonctionnant en **réseau local (LAN)**, sans accès
internet. Un PC héberge le serveur ; les joueurs se connectent depuis le
navigateur de leur téléphone, sur le même WiFi, via l'IP locale du PC.

## Fonctionnalités

- L'hôte liste les quiz du dossier `quizzes/` et en lance un.
- Une seule session active à la fois (mono-salle).
- Les joueurs rejoignent avec un pseudo, même en cours de partie.
- Questions avec minuteur, scores et points dégressifs selon la vitesse.
- L'hôte avance manuellement (bouton « Question suivante »).
- Les téléphones n'affichent que des boutons colorés (aucun texte de
  réponse envoyé au client).

## Stack

- Python 3.11+, FastAPI, Uvicorn (WebSockets), Jinja2.
- Côté client : Vanilla JS + CSS, sans build ni npm.

## Installation (Windows)

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Démarrage

Écouter sur toutes les interfaces pour être joignable depuis les téléphones :

```bat
uvicorn main:app --host 0.0.0.0 --port 8000
```

Les joueurs utilisent l'adresse IP du PC **sur le réseau WiFi partagé par
tout le monde** (le hotspot du téléphone, par exemple)c pas une IP fixe du
PC. La trouver avec `ipconfig` : ligne « Adresse IPv4 » de la carte WiFi
connectée à ce réseau.

Selon le téléphone, cette IP peut être dans différentes plages privées :
`192.168.x.x`, `10.x.x.x` ou `172.20.10.x` (iPhone). Prendre celle qui
s'affiche, quelle que soit la plage.

- Hôte : `http://localhost:8000/`
- Joueurs : `http://<adresse-ipv4-du-pc>:8000/play`
  (par exemple `http://10.47.102.215:8000/play`)

> Le pare-feu Windows peut bloquer le port 8000. Autoriser Python / le port
> 8000 en entrée si les téléphones n'arrivent pas à se connecter.

## Structure

```
main.py         Routes HTTP et endpoints WebSocket
game.py         Logique de jeu et état de session
models.py       Modèles de données (Quiz, Question, Player, session)
quizzes/        Quiz au format JSON
templates/      Pages hôte et joueur (host.html, play.html)
static/         host.js, play.js, style.css, images/
```

## Format d'un quiz

Le minuteur `time_limit` (secondes) est global à toutes les questions.
Chaque question a de 2 à 4 réponses et une liste `correct_indices` non vide.

```json
{
  "title": "Quiz de démonstration",
  "time_limit": 20,
  "questions": [
    {
      "question": "Quelle est la capitale de la France ?",
      "answers": ["Paris", "Lyon", "Marseille", "Bordeaux"],
      "correct_indices": [0]
    }
  ]
}
```

## Barème

Pour une bonne réponse :

```
points = round(1000 * (1 - (temps_reponse / time_limit) / 2))
```

Réponse quasi instantanée ~1000 pts, au dernier moment ~500 pts. Mauvaise
réponse ou absence de réponse : 0 point.

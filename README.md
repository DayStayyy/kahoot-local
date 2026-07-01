python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000

- Hôte : http://localhost:8000/
- Joueurs : http://<ton-ip-locale>:8000/play

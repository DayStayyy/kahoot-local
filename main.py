"""FastAPI application: HTTP routes, WebSocket endpoints, broadcasting."""

from __future__ import annotations

import asyncio
import json
import socket
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from starlette.responses import HTMLResponse

from game import GameSession
from models import Player, SessionState, load_quiz

QUIZZES_DIR = Path("quizzes")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ---------------------------------------------------------------------------
# Global state (single session, resets on restart)
# ---------------------------------------------------------------------------

game_session: Optional[GameSession] = None
host_ws: Optional[WebSocket] = None
player_connections: Dict[str, WebSocket] = {}
pending_players: Dict[str, str] = {}  # player_id -> name, before quiz starts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_local_ips() -> List[str]:
    """Return all non-loopback IPv4 addresses of this machine.

    Returns:
        Deduplicated list of local IPv4 address strings.
    """
    seen: dict[str, None] = {}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            if ":" not in ip and ip != "127.0.0.1":
                seen[ip] = None
    except Exception:
        pass
    return list(seen)


def scan_quizzes() -> list[dict[str, str]]:
    """Scan the quizzes directory and return valid quiz descriptors.

    Returns:
        List of dicts with 'filename' and 'title' for each valid quiz.
    """
    result = []
    for path in sorted(QUIZZES_DIR.glob("*.json")):
        try:
            quiz = load_quiz(path)
            result.append({"filename": path.name, "title": quiz.title})
        except Exception:
            pass
    return result


async def send_json(ws: WebSocket, data: Dict[str, Any]) -> None:
    """Send a JSON message to a WebSocket, ignoring send errors.

    Args:
        ws: The target WebSocket.
        data: The message payload.
    """
    try:
        await ws.send_text(json.dumps(data))
    except Exception:
        pass


async def broadcast_host(data: Dict[str, Any]) -> None:
    """Send a message to the host WebSocket if connected.

    Args:
        data: The message payload.
    """
    if host_ws is not None:
        await send_json(host_ws, data)


async def broadcast_players(data: Dict[str, Any]) -> None:
    """Send a message to all connected player WebSockets concurrently.

    Serializes once then dispatches to all players in parallel via
    asyncio.gather to avoid sequential latency with many connections.

    Args:
        data: The message payload.
    """
    if not player_connections:
        return
    text = json.dumps(data)
    await asyncio.gather(
        *(ws.send_text(text) for ws in list(player_connections.values())),
        return_exceptions=True,
    )


# ---------------------------------------------------------------------------
# Timer
# ---------------------------------------------------------------------------


async def run_question_timer(
    session: GameSession, time_limit: int
) -> None:
    """Sleep for time_limit seconds then trigger end-of-question.

    Transitions state to INTERMISSION and broadcasts results.

    Args:
        session: The active GameSession.
        time_limit: Duration in seconds.
    """
    await asyncio.sleep(time_limit)
    if session.state != SessionState.QUESTION:
        return
    session.end_question()
    question = session.current_question()
    await broadcast_host({
        "type": "intermission",
        "leaderboard": session.get_leaderboard(),
        "correct_indices": question.correct_indices,
    })
    await broadcast_players({"type": "intermission"})


def start_question_timer(session: GameSession) -> None:
    """Cancel any existing timer and start a new one for the question.

    Args:
        session: The active GameSession.
    """
    if session.timer_task and not session.timer_task.done():
        session.timer_task.cancel()
    session.timer_task = asyncio.create_task(
        run_question_timer(session, session.quiz.time_limit)
    )


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def host_page(request: Request) -> HTMLResponse:
    """Render the host page with the list of available quizzes.

    Args:
        request: The incoming HTTP request.

    Returns:
        Rendered host.html template.
    """
    quizzes = scan_quizzes()
    return templates.TemplateResponse(
        request, "host.html", {
            "quizzes": quizzes,
            "local_ips": get_local_ips(),
        }
    )


@app.get("/play", response_class=HTMLResponse)
async def player_page(request: Request) -> HTMLResponse:
    """Render the player page.

    Args:
        request: The incoming HTTP request.

    Returns:
        Rendered play.html template.
    """
    return templates.TemplateResponse(
        request, "play.html", {}
    )


# ---------------------------------------------------------------------------
# WebSocket — Host
# ---------------------------------------------------------------------------


@app.websocket("/ws/host")
async def host_websocket(websocket: WebSocket) -> None:
    """Handle the host WebSocket connection.

    Accepts one host at a time. Sends state snapshot on connect.
    Processes 'start_quiz' and 'next_question' messages.

    Args:
        websocket: The connecting WebSocket.
    """
    global host_ws

    await websocket.accept()
    host_ws = websocket

    snapshot: Dict[str, Any] = {
        "type": "state_snapshot",
        "state": "LOBBY",
    }
    if game_session is not None:
        snapshot["state"] = game_session.state.value
        snapshot["quiz_title"] = game_session.quiz.title
        snapshot["players"] = [
            {"id": p.player_id, "name": p.name, "score": p.score}
            for p in game_session.players.values()
        ]
    await send_json(websocket, snapshot)

    try:
        while True:
            raw = await websocket.receive_text()
            msg: Dict[str, Any] = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "start_quiz":
                await handle_start_quiz(msg.get("filename", ""))
            elif msg_type == "next_question":
                await handle_next_question()

    except WebSocketDisconnect:
        host_ws = None


async def handle_start_quiz(filename: str) -> None:
    """Load a quiz and start the first question.

    Args:
        filename: Base filename of the quiz JSON in quizzes/.
    """
    global game_session

    path = QUIZZES_DIR / filename
    try:
        quiz = load_quiz(path)
    except Exception as exc:
        await broadcast_host({"type": "error", "message": str(exc)})
        return

    game_session = GameSession(quiz)
    for pid, pname in list(pending_players.items()):
        game_session.players[pid] = Player(player_id=pid, name=pname)
    pending_players.clear()
    game_session.start_question()
    start_question_timer(game_session)

    question = game_session.current_question()
    await broadcast_host({
        "type": "question_start",
        "index": game_session.current_question_index,
        "total": len(quiz.questions),
        "question": question.question,
        "answers": question.answers,
        "time_limit": quiz.time_limit,
        "image": question.image,
    })
    await broadcast_players({
        "type": "question_start",
        "button_count": len(question.answers),
        "time_limit": quiz.time_limit,
    })


async def handle_next_question() -> None:
    """Advance the session to the next question or finish."""
    if game_session is None:
        return
    if game_session.state != SessionState.INTERMISSION:
        return

    has_next = game_session.next_question()

    if has_next:
        start_question_timer(game_session)
        question = game_session.current_question()
        await broadcast_host({
            "type": "question_start",
            "index": game_session.current_question_index,
            "total": len(game_session.quiz.questions),
            "question": question.question,
            "answers": question.answers,
            "time_limit": game_session.quiz.time_limit,
            "image": question.image,
        })
        await broadcast_players({
            "type": "question_start",
            "button_count": len(question.answers),
            "time_limit": game_session.quiz.time_limit,
        })
    else:
        leaderboard = game_session.get_leaderboard()
        await broadcast_host(
            {"type": "finished", "leaderboard": leaderboard}
        )
        players_list = sorted(
            game_session.players.values(),
            key=lambda p: p.score,
            reverse=True,
        )
        total = len(players_list)
        tasks = [
            send_json(ws, {
                "type": "finished",
                "score": player.score,
                "rank": rank,
                "total_players": total,
            })
            for rank, player in enumerate(players_list, start=1)
            if (ws := player_connections.get(player.player_id))
        ]
        await asyncio.gather(*tasks)


# ---------------------------------------------------------------------------
# WebSocket — Player
# ---------------------------------------------------------------------------


@app.websocket("/ws/player")
async def player_websocket(websocket: WebSocket) -> None:
    """Handle a player WebSocket connection.

    Waits for a 'join' message with a name, then processes 'answer'
    messages. Notifies host on join and disconnect.

    Args:
        websocket: The connecting WebSocket.
    """
    await websocket.accept()
    player_id: Optional[str] = None

    try:
        while True:
            raw = await websocket.receive_text()
            msg: Dict[str, Any] = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "join":
                player_id = await handle_player_join(
                    websocket, msg.get("name", "Anonyme")
                )
            elif msg_type == "answer" and player_id is not None:
                await handle_player_answer(
                    player_id, int(msg.get("index", -1))
                )

    except WebSocketDisconnect:
        if player_id is not None:
            player_connections.pop(player_id, None)
            pending_players.pop(player_id, None)
            if game_session is not None:
                game_session.remove_player(player_id)
            await broadcast_host(
                {"type": "player_left", "player_id": player_id}
            )


async def handle_player_join(
    websocket: WebSocket, name: str
) -> str:
    """Register a new player and notify the host.

    Players who join before the quiz starts are stored in pending_players
    and absorbed into the GameSession when the quiz is launched.

    Args:
        websocket: The player's WebSocket.
        name: The chosen display name.

    Returns:
        The assigned player_id.
    """
    if game_session is not None:
        player = game_session.add_player(name)
        player_id = player.player_id
    else:
        player_id = str(uuid.uuid4())
        pending_players[player_id] = name

    player_connections[player_id] = websocket
    await send_json(websocket, {"type": "joined", "player_id": player_id})
    await broadcast_host(
        {"type": "player_joined", "player_id": player_id, "name": name}
    )
    return player_id


async def handle_player_answer(
    player_id: str, answer_index: int
) -> None:
    """Record a player's answer and update the host.

    Args:
        player_id: ID of the answering player.
        answer_index: Zero-based index of the chosen button.
    """
    if game_session is None:
        return

    ws = player_connections.get(player_id)
    game_session.record_answer(player_id, answer_index)

    if ws:
        await send_json(ws, {"type": "answer_received"})

    await broadcast_host({
        "type": "answer_count",
        "count": game_session.answered_count(),
        "total_players": len(game_session.players),
    })

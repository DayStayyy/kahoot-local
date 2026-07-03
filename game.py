"""Game session logic for Kahoot LAN."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional

from models import Player, Question, Quiz, SessionState


class GameSession:
    """Manages the state machine and score tracking for one quiz session.

    Attributes:
        quiz: The loaded quiz being played.
        players: Mapping from player_id to Player.
        state: Current session state.
        current_question_index: Zero-based index of the active question.
        question_start_time: Monotonic time when the current question started.
        timer_task: Running asyncio task for the question countdown.
    """

    def __init__(self, quiz: Quiz) -> None:
        """Initialize a new session in LOBBY state.

        Args:
            quiz: The quiz to play.
        """
        self.quiz: Quiz = quiz
        self.players: Dict[str, Player] = {}
        self.state: SessionState = SessionState.LOBBY
        self.current_question_index: int = 0
        self.question_start_time: Optional[float] = None
        self.timer_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
        self._answered_count: int = 0

    def add_player(self, name: str) -> Player:
        """Create and register a new player.

        Args:
            name: Display name chosen by the player.

        Returns:
            The newly created Player.
        """
        player_id = str(uuid.uuid4())
        player = Player(player_id=player_id, name=name)
        self.players[player_id] = player
        return player

    def remove_player(self, player_id: str) -> None:
        """Unregister a player (e.g., on disconnect).

        Args:
            player_id: ID of the player to remove.
        """
        self.players.pop(player_id, None)

    def start_question(self) -> None:
        """Mark the session as QUESTION and record start time.

        Resets answered_current for all players.
        """
        self.state = SessionState.QUESTION
        self.question_start_time = time.monotonic()
        self._answered_count = 0
        for player in self.players.values():
            player.answered_current = False
            player.answered_correctly = False

    def record_answer(
        self, player_id: str, answer_index: int
    ) -> int:
        """Record a player's answer and compute their score delta.

        Ignores duplicate answers. Awards 0 for a wrong answer or
        an out-of-range index.

        Args:
            player_id: ID of the answering player.
            answer_index: Zero-based index of the chosen button.

        Returns:
            Points earned (0 if wrong, duplicate, or player unknown).
        """
        player = self.players.get(player_id)
        if player is None or player.answered_current:
            return 0
        if self.state != SessionState.QUESTION:
            return 0

        player.answered_current = True
        self._answered_count += 1
        question = self.current_question()

        if answer_index not in question.correct_indices:
            return 0

        player.answered_correctly = True
        elapsed = time.monotonic() - (self.question_start_time or 0)
        time_limit = self.quiz.time_limit
        points = round(1000 * (1 - (elapsed / time_limit) / 2))
        points = max(0, points)
        player.score += points
        return points

    def end_question(self) -> None:
        """Transition from QUESTION to INTERMISSION."""
        self.state = SessionState.INTERMISSION

    def next_question(self) -> bool:
        """Advance to the next question or finish the session.

        Returns:
            True if another question was started, False if the session
            is now FINISHED.
        """
        self.current_question_index += 1
        if self.current_question_index >= len(self.quiz.questions):
            self.state = SessionState.FINISHED
            return False
        self.start_question()
        return True

    def current_question(self) -> Question:
        """Return the currently active question.

        Returns:
            The Question at current_question_index.
        """
        return self.quiz.questions[self.current_question_index]

    def answered_count(self) -> int:
        """Return the number of players who answered the current question.

        Returns:
            Maintained counter incremented in record_answer; O(1).
        """
        return self._answered_count

    def get_leaderboard(self) -> List[Dict[str, Any]]:
        """Return players sorted by score descending.

        Returns:
            List of dicts with 'name' and 'score' keys.
        """
        sorted_players = sorted(
            self.players.values(),
            key=lambda p: p.score,
            reverse=True,
        )
        return [
            {"name": p.name, "score": p.score}
            for p in sorted_players
        ]

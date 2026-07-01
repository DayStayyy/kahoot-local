"""Data models for Kahoot LAN."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, field_validator


class SessionState(str, Enum):
    """Possible states of a game session."""

    LOBBY = "LOBBY"
    QUESTION = "QUESTION"
    INTERMISSION = "INTERMISSION"
    FINISHED = "FINISHED"


class Question(BaseModel):
    """A single quiz question with its answers and correct indices.

    Args:
        question: The question text.
        answers: Between 2 and 4 answer choices.
        correct_indices: Non-empty list of valid answer indices.
    """

    question: str
    answers: List[str]
    correct_indices: List[int]
    image: Optional[str] = None

    @field_validator("answers")
    @classmethod
    def validate_answers(cls, v: List[str]) -> List[str]:
        """Ensure between 2 and 4 answers are provided.

        Args:
            v: The list of answer strings.

        Returns:
            The validated list of answers.

        Raises:
            ValueError: If the number of answers is not between 2 and 4.
        """
        if not (2 <= len(v) <= 4):
            raise ValueError(
                f"Expected 2-4 answers, got {len(v)}."
            )
        return v

    @field_validator("correct_indices")
    @classmethod
    def validate_correct_indices(
        cls, v: List[int], info: object
    ) -> List[int]:
        """Ensure correct_indices is non-empty and all indices are valid.

        Args:
            v: The list of correct answer indices.
            info: Validation info containing other field values.

        Returns:
            The validated list of correct indices.

        Raises:
            ValueError: If indices are empty or out of range.
        """
        if not v:
            raise ValueError("correct_indices must not be empty.")
        answers = getattr(info, "data", {}).get("answers", [])
        if answers:
            for idx in v:
                if idx < 0 or idx >= len(answers):
                    raise ValueError(
                        f"Index {idx} out of range for"
                        f" {len(answers)} answers."
                    )
        return v


class Quiz(BaseModel):
    """A complete quiz loaded from a JSON file.

    Args:
        title: Display title of the quiz.
        time_limit: Seconds per question, strictly positive.
        questions: Ordered list of questions.
    """

    title: str
    time_limit: int
    questions: List[Question]

    @field_validator("time_limit")
    @classmethod
    def validate_time_limit(cls, v: int) -> int:
        """Ensure time_limit is a strictly positive integer.

        Args:
            v: The time limit in seconds.

        Returns:
            The validated time limit.

        Raises:
            ValueError: If time_limit is not strictly positive.
        """
        if v <= 0:
            raise ValueError(
                f"time_limit must be > 0, got {v}."
            )
        return v


@dataclass
class Player:
    """Represents a connected player.

    Attributes:
        player_id: Unique identifier assigned by the server.
        name: Display name chosen by the player.
        score: Accumulated points across all questions.
        answered_current: True if the player answered the current question.
    """

    player_id: str
    name: str
    score: int = 0
    answered_current: bool = False


def load_quiz(path: Path) -> Quiz:
    """Load and validate a quiz from a JSON file.

    Args:
        path: Absolute or relative path to the JSON file.

    Returns:
        A validated Quiz instance.

    Raises:
        ValueError: If the file content fails validation.
        FileNotFoundError: If the path does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    try:
        return Quiz.model_validate(raw)
    except Exception as exc:
        raise ValueError(
            f"Invalid quiz file '{path.name}': {exc}"
        ) from exc

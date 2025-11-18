"""Thread-safe session store for tracking user instructions and uploaded files."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import threading
import copy

DEFAULT_INSTRUCTION = "对比两个文件的差异"


@dataclass
class Session:
    """Stores user instruction and file paths for a comparison session."""

    instruction: str = DEFAULT_INSTRUCTION
    files: List[str] = field(default_factory=list)


class SessionStore:
    """In-memory storage for per-user sessions.

    This is intentionally simple because the project currently targets
    single-instance deployments. If multiple workers are required, this
    class can be replaced with a Redis or database-backed implementation
    without changing the calling code.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.RLock()

    def set_instruction(self, user_id: str, instruction: str) -> Session:
        """Record or update the instruction for a user."""
        clean_instruction = instruction.strip() if instruction else ""
        with self._lock:
            session = self._sessions.get(user_id, Session())
            if clean_instruction:
                session.instruction = clean_instruction
            self._sessions[user_id] = session
            return copy.deepcopy(session)

    def append_file(self, user_id: str, file_path: str) -> List[str]:
        """Append a file path to the user's session."""
        with self._lock:
            session = self._sessions.get(user_id, Session())
            session.files.append(file_path)
            self._sessions[user_id] = session
            return list(session.files)

    def snapshot(self, user_id: str) -> Optional[Session]:
        """Return a copy of the session for inspection without mutation."""
        with self._lock:
            session = self._sessions.get(user_id)
            return copy.deepcopy(session) if session else None

    def pop(self, user_id: str) -> Optional[Session]:
        """Remove and return the user's session."""
        with self._lock:
            return self._sessions.pop(user_id, None)

    def ensure(self, user_id: str) -> Session:
        """Make sure a session exists, returning a copy of the current state."""
        with self._lock:
            session = self._sessions.setdefault(user_id, Session())
            return copy.deepcopy(session)

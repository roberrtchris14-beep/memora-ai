import os
import json
import logging
from typing import List, Optional
from datetime import datetime
from .experience import Experience, experience_to_dict, dict_to_experience

logger = logging.getLogger(__name__)


class ExperienceStore:
    def __init__(self, storage_path: str = "experiences.json"):
        self.storage_path = storage_path
        self.experiences: List[Experience] = []
        self._last_mtime: Optional[float] = None
        self._sync()

    def _sync(self) -> None:
        """Check if file has changed on disk and reload if necessary."""
        if os.path.exists(self.storage_path):
            try:
                mtime = os.path.getmtime(self.storage_path)
                if self._last_mtime is None or mtime != self._last_mtime:
                    self._load()
                    self._last_mtime = mtime
            except Exception as e:
                logger.warning(f"Error checking mtime for {self.storage_path}: {e}")
        elif self._last_mtime is not None:
            self.experiences = []
            self._last_mtime = None

    def _load(self) -> None:
        """Load experiences from the JSON file."""
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    self.experiences = [dict_to_experience(item) for item in data]
                else:
                    self.experiences = []
            if os.path.exists(self.storage_path):
                self._last_mtime = os.path.getmtime(self.storage_path)
        except Exception as e:
            logger.warning(f"Error loading experiences from {self.storage_path}: {e}")
            self.experiences = []

    def _save(self) -> None:
        """Save experiences to the JSON file."""
        try:
            # Ensure parent directory exists if path contains directories
            parent_dir = os.path.dirname(self.storage_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump([experience_to_dict(exp) for exp in self.experiences], f, indent=2)
            if os.path.exists(self.storage_path):
                self._last_mtime = os.path.getmtime(self.storage_path)
        except Exception as e:
            logger.error(f"Error saving experiences to {self.storage_path}: {e}")
            raise e

    def log_experience(self, experience: Experience) -> None:
        """Append an experience and persist it to disk."""
        self._sync()
        self.experiences.append(experience)
        self._save()

    def get_all(self) -> List[Experience]:
        """Return all recorded experiences."""
        self._sync()
        return list(self.experiences)

    def get_by_session(self, session_id: str) -> List[Experience]:
        """Filter experiences by session ID."""
        self._sync()
        return [exp for exp in self.experiences if exp.session_id == session_id]

    def get_by_tool(self, tool_name: str) -> List[Experience]:
        """Filter experiences by the tool used."""
        self._sync()
        return [exp for exp in self.experiences if exp.tool_used == tool_name]

    def get_recent(self, limit: int = 100) -> List[Experience]:
        """Return the most recent N experiences, sorted by timestamp descending."""
        self._sync()
        sorted_experiences = sorted(
            self.experiences,
            key=lambda exp: exp.timestamp if isinstance(exp.timestamp, datetime) else datetime.min,
            reverse=True
        )
        return sorted_experiences[:limit]

    def get_successful_experiences(self) -> List[Experience]:
        """Return only experiences where success is True."""
        self._sync()
        return [exp for exp in self.experiences if exp.success]

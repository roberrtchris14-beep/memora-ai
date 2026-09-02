import os
import json
import logging
import re
from datetime import datetime
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from app.learning.experience import Experience

logger = logging.getLogger(__name__)


class UserModel(BaseModel):
    user_id: str
    preferences: Dict[str, Any] = Field(default_factory=dict)
    interaction_count: int = 0
    avg_confidence: float = 0.0
    last_seen: datetime = Field(default_factory=datetime.now)


def user_model_to_dict(model: UserModel) -> Dict[str, Any]:
    """Convert a UserModel to a JSON-serializable dictionary."""
    if hasattr(model, "model_dump"):
        data = model.model_dump(mode="json")
    else:
        data = model.dict()
        if isinstance(data.get("last_seen"), datetime):
            data["last_seen"] = data["last_seen"].isoformat()
    return data


def dict_to_user_model(data: Dict[str, Any]) -> UserModel:
    """Instantiate a UserModel from dictionary data."""
    if hasattr(UserModel, "model_validate"):
        return UserModel.model_validate(data)
    return UserModel.parse_obj(data)


class UserModelBuilder:
    def __init__(self, experience_store: Optional[Any] = None, storage_path: str = "user_models.json"):
        self.experience_store = experience_store
        self.storage_path = storage_path
        self.user_models: Dict[str, UserModel] = {}
        self.load_models()

    def load_models(self) -> None:
        """Load user models from JSON file."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.user_models = {
                            uid: dict_to_user_model(u_data) for uid, u_data in data.items()
                        }
                    elif isinstance(data, list):
                        self.user_models = {
                            u_data.get("user_id", f"user_{i}"): dict_to_user_model(u_data)
                            for i, u_data in enumerate(data)
                        }
            except Exception as e:
                logger.warning(f"Error loading user models from {self.storage_path}: {e}")
                self.user_models = {}
        else:
            self.user_models = {}

    def save_models(self) -> None:
        """Save user models to JSON file."""
        try:
            parent_dir = os.path.dirname(self.storage_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            with open(self.storage_path, "w", encoding="utf-8") as f:
                data = {uid: user_model_to_dict(m) for uid, m in self.user_models.items()}
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving user models to {self.storage_path}: {e}")

    def _extract_topics(self, text: str) -> List[str]:
        """Simple keyword-based topic extractor from user queries."""
        topic_keywords = {
            "math": ["calc", "math", "add", "multiply", "divide", "equation", "sqrt", "celsius", "convert"],
            "programming": ["python", "code", "json", "api", "function", "variable", "bug", "developer"],
            "search": ["who", "what", "where", "search", "lookup", "find", "news", "google"],
            "translation": ["translate", "spanish", "french", "german", "hindi", "language"],
            "formatting": ["format", "uppercase", "lowercase", "slug", "clean", "trim"],
            "weather": ["weather", "temperature", "forecast", "rain", "sunny", "climate"],
            "productivity": ["note", "save", "todo", "task", "remember", "remind"],
        }
        text_lower = text.lower()
        matched = []
        for topic, kw_list in topic_keywords.items():
            if any(kw in text_lower for kw in kw_list):
                matched.append(topic)
        return matched or ["general"]

    def _detect_language(self, text: str) -> str:
        """Basic heuristic language detection."""
        text_lower = text.lower()
        if any(w in text_lower for w in ["kya", "kaise", "bhai", "namaste", "dhanyavaad", "haan", "nahi"]):
            return "hinglish"
        if any(w in text_lower for w in ["hola", "gracias", "por favor", "amigo"]):
            return "es"
        if any(w in text_lower for w in ["bonjour", "merci", "oui"]):
            return "fr"
        return "en"

    def build_from_experiences(self, session_id: str) -> UserModel:
        """
        Build or reconstruct a UserModel from all historical experiences
        associated with a session_id.
        """
        if not self.experience_store:
            return UserModel(user_id=session_id)

        experiences = self.experience_store.get_by_session(session_id)
        if not experiences:
            # Check if model already exists in memory/disk
            return self.user_models.get(session_id, UserModel(user_id=session_id))

        tool_counts: Dict[str, int] = {}
        topics_count: Dict[str, int] = {}
        languages: Dict[str, int] = {}
        confidence_scores: List[float] = []
        latest_time = datetime.min

        for exp in experiences:
            # Tool usage
            if exp.tool_used:
                tool_counts[exp.tool_used] = tool_counts.get(exp.tool_used, 0) + 1

            # Topics
            for t in self._extract_topics(exp.user_query):
                topics_count[t] = topics_count.get(t, 0) + 1

            # Language
            lang = self._detect_language(exp.user_query)
            languages[lang] = languages.get(lang, 0) + 1

            # Confidence / success metric
            if exp.feedback_score is not None:
                confidence_scores.append(float(exp.feedback_score))
            else:
                confidence_scores.append(1.0 if exp.success else 0.4)

            # Timestamp
            exp_time = exp.timestamp if isinstance(exp.timestamp, datetime) else datetime.now()
            if exp_time > latest_time:
                latest_time = exp_time

        primary_lang = max(languages, key=languages.get) if languages else "en"
        sorted_topics = sorted(topics_count, key=topics_count.get, reverse=True)
        avg_conf = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0

        model = UserModel(
            user_id=session_id,
            preferences={
                "language": primary_lang,
                "topics": sorted_topics[:5],
                "tool_preferences": tool_counts,
                "preferred_tools": sorted(tool_counts, key=tool_counts.get, reverse=True)[:3]
            },
            interaction_count=len(experiences),
            avg_confidence=round(avg_conf, 2),
            last_seen=latest_time if latest_time != datetime.min else datetime.now()
        )

        self.user_models[session_id] = model
        self.save_models()
        return model

    def update_model(self, existing: UserModel, new_exp: Experience) -> UserModel:
        """Incrementally update an existing UserModel with a new Experience."""
        preferences = existing.preferences or {}
        tool_counts = preferences.get("tool_preferences", {})

        if new_exp.tool_used:
            tool_counts[new_exp.tool_used] = tool_counts.get(new_exp.tool_used, 0) + 1
        preferences["tool_preferences"] = tool_counts
        preferences["preferred_tools"] = sorted(tool_counts, key=tool_counts.get, reverse=True)[:3]

        # Topics
        current_topics = set(preferences.get("topics", []))
        new_topics = self._extract_topics(new_exp.user_query)
        current_topics.update(new_topics)
        preferences["topics"] = list(current_topics)[:5]

        # Language
        lang = self._detect_language(new_exp.user_query)
        if lang != "en":
            preferences["language"] = lang

        # Count & avg confidence
        old_count = existing.interaction_count
        new_count = old_count + 1
        score = new_exp.feedback_score if new_exp.feedback_score is not None else (1.0 if new_exp.success else 0.4)
        new_avg_conf = ((existing.avg_confidence * old_count) + score) / new_count

        exp_time = new_exp.timestamp if isinstance(new_exp.timestamp, datetime) else datetime.now()

        updated = UserModel(
            user_id=existing.user_id,
            preferences=preferences,
            interaction_count=new_count,
            avg_confidence=round(new_avg_conf, 2),
            last_seen=exp_time
        )

        self.user_models[existing.user_id] = updated
        self.save_models()
        return updated

    def build_all_users(self) -> Dict[str, UserModel]:
        """Build user models for all sessions currently recorded in experience store."""
        if not self.experience_store:
            return self.user_models

        sessions = set(exp.session_id for exp in self.experience_store.get_all())
        results = {}
        for sid in sessions:
            results[sid] = self.build_from_experiences(sid)
        return results

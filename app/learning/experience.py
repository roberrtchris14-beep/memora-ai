from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class Experience(BaseModel):
    session_id: str
    user_query: str
    agent_response: str
    tool_used: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_result: Optional[Dict[str, Any]] = None
    success: bool = True
    timestamp: datetime = Field(default_factory=datetime.now)
    feedback_score: Optional[float] = None


def experience_to_dict(exp: Experience) -> Dict[str, Any]:
    """Convert an Experience instance to a JSON-serializable dictionary."""
    if hasattr(exp, "model_dump"):
        data = exp.model_dump(mode="json")
    else:
        data = exp.dict()
        if isinstance(data.get("timestamp"), datetime):
            data["timestamp"] = data["timestamp"].isoformat()
    return data


def dict_to_experience(data: Dict[str, Any]) -> Experience:
    """Create an Experience instance from a dictionary."""
    if hasattr(Experience, "model_validate"):
        return Experience.model_validate(data)
    return Experience.parse_obj(data)

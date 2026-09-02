from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class MemoryCreate(BaseModel):
    text: str
    metadata: Optional[Dict[str, Any]] = None

class MemoryResponse(BaseModel):
    id: str
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str

class SkillDefinition(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)

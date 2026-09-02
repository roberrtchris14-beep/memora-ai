import json
from typing import Any, Dict
from app.skills.base import BaseSkill

class JsonParserSkill(BaseSkill):
    def __init__(self):
        super().__init__(
            name="json_parser",
            description="Parses, validates, formats, and extracts fields from JSON data strings."
        )

    def execute(self, json_string: str = "{}", **kwargs) -> Dict[str, Any]:
        try:
            parsed = json.loads(json_string)
            formatted = json.dumps(parsed, indent=2)
            return {"status": "success", "parsed": parsed, "formatted": formatted, "valid": True}
        except Exception as e:
            return {"status": "error", "error": f"Invalid JSON: {e}", "valid": False}

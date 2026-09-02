import re
from typing import Any, Dict
from app.skills.base import BaseSkill

class TextFormatterSkill(BaseSkill):
    def __init__(self):
        super().__init__(
            name="text_formatter",
            description="Formats, transforms, and normalizes text (uppercase, lowercase, title case, slugify)."
        )

    def execute(self, text: str = "", mode: str = "upper", **kwargs) -> Dict[str, Any]:
        try:
            mode = mode.lower()
            if mode == "upper":
                res = text.upper()
            elif mode == "lower":
                res = text.lower()
            elif mode == "title":
                res = text.title()
            elif mode == "slug":
                res = re.sub(r"[^\w\s-]", "", text.lower()).strip()
                res = re.sub(r"[-\s]+", "-", res)
            else:
                res = text.strip()
            return {"status": "success", "formatted_text": res, "mode": mode}
        except Exception as e:
            return {"status": "error", "error": str(e)}

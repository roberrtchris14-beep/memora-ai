import datetime
import math
from typing import Any, Dict, Optional
from app.skills.base import BaseSkill, SkillRegistry

class CalculatorSkill(BaseSkill):
    def __init__(self):
        super().__init__(
            name="calculator",
            description="Executes a mathematical expression safely. Input 'expression' as a string (e.g., '2 + 2' or 'sqrt(16)')."
        )

    def execute(self, expression: str, **kwargs) -> Any:
        try:
            # Safe math evaluation namespace
            safe_dict = {
                "__builtins__": {},
                "sin": math.sin,
                "cos": math.cos,
                "tan": math.tan,
                "sqrt": math.sqrt,
                "pi": math.pi,
                "e": math.e,
                "pow": pow,
                "abs": abs,
                "round": round
            }
            # Remove any unwanted whitespace/characters
            cleaned_expr = expression.strip()
            result = eval(cleaned_expr, safe_dict)
            return {"result": result, "status": "success"}
        except Exception as e:
            return {"error": str(e), "status": "error"}


class TimeSkill(BaseSkill):
    def __init__(self):
        super().__init__(
            name="time",
            description="Returns the current date and time."
        )

    def execute(self, **kwargs) -> Any:
        current_dt = datetime.datetime.now().isoformat()
        return {"current_time": current_dt, "status": "success"}


class WebSearchSkill(BaseSkill):
    def __init__(self):
        super().__init__(
            name="web_search",
            description="Searches the web for top query results. Input 'query' as a string."
        )

    def execute(self, query: str, **kwargs) -> Any:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=3))
            
            snippets = []
            for r in results:
                snippets.append({
                    "title": r.get("title", ""),
                    "href": r.get("href", ""),
                    "body": r.get("body", "")
                })
            return {"results": snippets, "status": "success"}
        except Exception as e:
            return {"error": str(e), "status": "error"}


class SaveNoteSkill(BaseSkill):
    def __init__(self, vector_store=None):
        super().__init__(
            name="save_note",
            description="Saves a semantic note or memory. Input 'text' as string and optional 'metadata' dict."
        )
        self.vector_store = vector_store

    def execute(self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> Any:
        try:
            if not self.vector_store:
                from app.memory.vector_store import VectorStore
                self.vector_store = VectorStore()
            
            if metadata is None:
                metadata = {}
            if "source" not in metadata:
                metadata["source"] = "save_note_skill"
                
            memory_id = self.vector_store.add_memory(text, metadata)
            return {
                "message": f"Successfully saved memory note with ID: {memory_id}",
                "id": memory_id,
                "status": "success"
            }
        except Exception as e:
            return {"error": str(e), "status": "error"}


def register_all_skills(registry: SkillRegistry, vector_store=None):
    registry.register_skill(CalculatorSkill())
    registry.register_skill(TimeSkill())
    registry.register_skill(WebSearchSkill())
    registry.register_skill(SaveNoteSkill(vector_store=vector_store))

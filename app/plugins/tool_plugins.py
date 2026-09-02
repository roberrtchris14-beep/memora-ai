import math
import datetime
import uuid
import os
import json
from typing import Optional, Dict, Any

from app.plugins.base import Plugin, PluginType


class CalculatorToolPlugin(Plugin):
    def get_name(self) -> str:
        return "calculator"

    def get_type(self) -> PluginType:
        return PluginType.TOOL

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Mathematical expression to evaluate (e.g., '2 + 2', 'sqrt(16)')"}
            },
            "required": ["expression"]
        }

    def initialize(self, config: dict) -> None:
        self.config = config

    def execute(self, input_data: dict) -> dict:
        try:
            expression = input_data.get("expression")
            if not expression:
                return {"error": "Expression is required", "status": "error"}

            # Safe environment for eval
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
            result = eval(expression.strip(), safe_dict)
            return {"result": result, "status": "success"}
        except Exception as e:
            return {"error": str(e), "status": "error"}

    def validate_config(self, config: dict) -> bool:
        return True


class TimeToolPlugin(Plugin):
    def get_name(self) -> str:
        return "time"

    def get_type(self) -> PluginType:
        return PluginType.TOOL

    def get_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    def initialize(self, config: dict) -> None:
        self.config = config

    def execute(self, input_data: dict) -> dict:
        try:
            current_time = datetime.datetime.now().isoformat()
            return {"current_time": current_time, "status": "success"}
        except Exception as e:
            return {"error": str(e), "status": "error"}

    def validate_config(self, config: dict) -> bool:
        return True


class WebSearchToolPlugin(Plugin):
    def get_name(self) -> str:
        return "web_search"

    def get_type(self) -> PluginType:
        return PluginType.TOOL

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string"}
            },
            "required": ["query"]
        }

    def initialize(self, config: dict) -> None:
        self.config = config

    def execute(self, input_data: dict) -> dict:
        try:
            query = input_data.get("query")
            if not query:
                return {"error": "Query is required", "status": "error"}

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
            except ImportError:
                return {"error": "duckduckgo-search library not installed", "status": "error"}
        except Exception as e:
            return {"error": str(e), "status": "error"}

    def validate_config(self, config: dict) -> bool:
        return True


class SaveNoteToolPlugin(Plugin):
    def get_name(self) -> str:
        return "save_note"

    def get_type(self) -> PluginType:
        return PluginType.TOOL

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Note content to save"},
                "metadata": {"type": "object", "description": "Optional metadata (source, category, etc.)"}
            },
            "required": ["text"]
        }

    def initialize(self, config: dict) -> None:
        self.config = config
        self.memory_plugin = config.get("memory_plugin")  # Reference to memory plugin

    def execute(self, input_data: dict) -> dict:
        try:
            text = input_data.get("text")
            if not text:
                return {"error": "Text is required", "status": "error"}

            metadata = input_data.get("metadata", {})
            metadata["source"] = metadata.get("source", "save_note_tool")

            if self.memory_plugin:
                result = self.memory_plugin.execute({
                    "action": "add",
                    "text": text,
                    "metadata": metadata
                })
                if result.get("status") == "success":
                    return {
                        "message": f"Successfully saved note with ID: {result.get('id')}",
                        "id": result.get("id"),
                        "status": "success"
                    }
                else:
                    return {"error": result.get("response", "Memory plugin failed"), "status": "error"}
            else:
                return {"error": "Memory plugin not configured", "status": "error"}
        except Exception as e:
            return {"error": str(e), "status": "error"}

    def validate_config(self, config: dict) -> bool:
        if not isinstance(config, dict):
            return False
        return True


class FileSystemToolPlugin(Plugin):
    def get_name(self) -> str:
        return "file_system"

    def get_type(self) -> PluginType:
        return PluginType.TOOL

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["read", "write", "list"]},
                "path": {"type": "string", "description": "File or directory path"},
                "content": {"type": "string", "description": "Content to write (only for write action)"}
            },
            "required": ["action", "path"]
        }

    def initialize(self, config: dict) -> None:
        self.config = config
        self.allowed_dirs = config.get("allowed_directories", [os.getcwd()])
        # Convert to absolute paths
        self.allowed_dirs = [os.path.abspath(d) for d in self.allowed_dirs]

    def _validate_path(self, path: str) -> str:
        """Validate path is within allowed directories."""
        abs_path = os.path.abspath(path)
        for allowed in self.allowed_dirs:
            if abs_path.startswith(allowed):
                return abs_path
        raise PermissionError(f"Path '{path}' is outside allowed directories: {self.allowed_dirs}")

    def execute(self, input_data: dict) -> dict:
        try:
            action = input_data.get("action")
            path = input_data.get("path")
            
            if not action or not path:
                return {"error": "Both action and path are required", "status": "error"}

            safe_path = self._validate_path(path)

            if action == "read":
                if not os.path.exists(safe_path):
                    return {"error": f"File not found: {safe_path}", "status": "error"}
                with open(safe_path, 'r') as f:
                    content = f.read()
                return {"content": content, "status": "success"}

            elif action == "write":
                content = input_data.get("content", "")
                # Ensure directory exists
                os.makedirs(os.path.dirname(safe_path), exist_ok=True)
                with open(safe_path, 'w') as f:
                    f.write(content)
                return {"message": f"Successfully wrote to {safe_path}", "status": "success"}

            elif action == "list":
                if not os.path.exists(safe_path):
                    return {"error": f"Directory not found: {safe_path}", "status": "error"}
                if not os.path.isdir(safe_path):
                    return {"error": f"Path is not a directory: {safe_path}", "status": "error"}
                
                items = os.listdir(safe_path)
                return {"items": items, "status": "success"}

            else:
                return {"error": f"Unknown action: {action}", "status": "error"}
        except PermissionError as e:
            return {"error": str(e), "status": "error"}
        except Exception as e:
            return {"error": str(e), "status": "error"}

    def validate_config(self, config: dict) -> bool:
        return True
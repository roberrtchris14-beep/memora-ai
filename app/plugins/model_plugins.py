import google.generativeai as genai
import requests
from typing import Optional
from app.plugins.base import Plugin, PluginType


class GeminiModelPlugin(Plugin):
    def get_name(self) -> str:
        return "gemini_model"

    def get_type(self) -> PluginType:
        return PluginType.MODEL

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The prompt or instruction to send to Gemini"},
                "model_name": {"type": "string", "description": "Optional model name override (e.g., 'gemini-1.5-flash')"},
                "temperature": {"type": "number", "description": "Optional sampling temperature between 0.0 and 2.0"}
            },
            "required": ["prompt"]
        }

    def initialize(self, config: dict) -> None:
        self.config = config
        self.api_key = config.get("api_key")
        self.model_name = config.get("model_name")
        
        if not self.api_key:
            raise ValueError("API key 'api_key' must be provided in the config.")
        if not self.model_name:
            raise ValueError("Model name 'model_name' must be provided in the config.")
            
        genai.configure(api_key=self.api_key)

    def execute(self, input_data: dict) -> dict:
        try:
            prompt = input_data.get("prompt")
            if not prompt:
                raise ValueError("Prompt 'prompt' must be provided in input_data.")
                
            model_name = input_data.get("model_name", self.model_name)
            generation_config = {}
            
            # Extract optional parameter overrides
            temperature = input_data.get("temperature") or self.config.get("temperature")
            if temperature is not None:
                generation_config["temperature"] = float(temperature)
                
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                prompt,
                generation_config=generation_config if generation_config else None
            )
            return {"response": response.text, "status": "success"}
        except Exception as e:
            return {"response": str(e), "status": "error"}

    def validate_config(self, config: dict) -> bool:
        if not isinstance(config, dict):
            return False
        return bool(config.get("api_key"))


class OllamaModelPlugin(Plugin):
    def get_name(self) -> str:
        return "ollama_model"

    def get_type(self) -> PluginType:
        return PluginType.MODEL

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The prompt or instruction to send to Ollama"},
                "model_name": {"type": "string", "description": "Model name (e.g. 'llama3.2')"},
                "base_url": {"type": "string", "description": "Base URL of Ollama server"}
            },
            "required": ["prompt"]
        }

    def initialize(self, config: dict) -> None:
        self.config = config
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.model_name = config.get("model_name", "llama3.2")

    def execute(self, input_data: dict) -> dict:
        try:
            prompt = input_data.get("prompt")
            if not prompt:
                raise ValueError("Prompt 'prompt' must be provided in input_data.")
                
            model_name = input_data.get("model_name", self.model_name)
            base_url = input_data.get("base_url", self.base_url)
            
            payload = {
                "model": model_name,
                "prompt": prompt,
                "stream": False
            }
            response = requests.post(
                f"{base_url}/api/generate",
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            res_json = response.json()
            response_text = res_json.get("response", "")
            return {"response": response_text, "status": "success"}
        except Exception as e:
            return {"response": str(e), "status": "error"}

    def validate_config(self, config: dict) -> bool:
        if not isinstance(config, dict):
            return False
        base_url = config.get("base_url", "http://localhost:11434")
        return isinstance(base_url, str) and (base_url.startswith("http://") or base_url.startswith("https://"))

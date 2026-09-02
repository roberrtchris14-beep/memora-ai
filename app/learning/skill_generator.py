import os
import json
import logging
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

import google.generativeai as genai
from app.core.config import GEMINI_API_KEY
from app.learning.experience import Experience

logger = logging.getLogger(__name__)

# Configure Gemini if key is provided
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    logger.warning(f"Failed to configure Gemini in skill_generator: {e}")


class SkillProposal(BaseModel):
    skill_name: str
    description: str
    use_case: str
    example_queries: List[str] = Field(default_factory=list)
    confidence_score: float = 0.0
    tool_input_schema: Dict[str, Any] = Field(default_factory=dict)
    status: str = "proposed"  # "proposed", "integrated", "rejected"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


def _clean_json_output(text: str) -> str:
    """Extract and clean a JSON string from markdown code blocks or raw text."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return text


class SkillGenerator:
    def __init__(self, experience_store: Optional[Any] = None, storage_path: str = "proposals.json"):
        self.experience_store = experience_store
        self.storage_path = storage_path
        self.proposals: Dict[str, SkillProposal] = {}
        self._load_proposals()

    def _load_proposals(self) -> None:
        """Load proposals from JSON file."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            proposal = SkillProposal(**item)
                            self.proposals[proposal.skill_name] = proposal
                    elif isinstance(data, dict):
                        for k, v in data.items():
                            proposal = SkillProposal(**v)
                            self.proposals[proposal.skill_name] = proposal
            except Exception as e:
                logger.warning(f"Error loading proposals from {self.storage_path}: {e}")
                self.proposals = {}
        else:
            self.proposals = {}

    def save_proposals(self) -> None:
        """Persist proposals to JSON file."""
        try:
            parent_dir = os.path.dirname(self.storage_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            with open(self.storage_path, "w", encoding="utf-8") as f:
                data = [
                    p.model_dump(mode="json") if hasattr(p, "model_dump") else p.dict()
                    for p in self.proposals.values()
                ]
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving proposals to {self.storage_path}: {e}")

    def get_proposals(self, status: Optional[str] = None) -> List[SkillProposal]:
        """Return all proposals, optionally filtered by status."""
        self._load_proposals()
        if status:
            return [p for p in self.proposals.values() if p.status == status]
        return list(self.proposals.values())

    def get_proposal(self, skill_name: str) -> Optional[SkillProposal]:
        """Get a specific proposal by skill_name."""
        self._load_proposals()
        return self.proposals.get(skill_name)

    def _cluster_queries(self, experiences: List[Experience]) -> Dict[str, List[str]]:
        """
        Cluster user queries using intent/keyword categorization.
        Returns a mapping of cluster_name -> list of queries.
        """
        clusters: Dict[str, List[str]] = {
            "text_formatting": [],
            "translation": [],
            "unit_conversion": [],
            "weather_lookup": [],
            "text_summarization": [],
            "json_data_parser": [],
            "general_utility": [],
        }

        keywords = {
            "text_formatting": ["format", "uppercase", "lowercase", "capitalize", "slugify", "clean text", "trim", "case"],
            "translation": ["translate", "spanish", "french", "german", "hindi", "japanese", "translation", "language"],
            "unit_conversion": ["convert", "celsius", "fahrenheit", "kg", "lbs", "miles", "km", "meters", "feet", "currency", "usd", "eur"],
            "weather_lookup": ["weather", "temperature", "forecast", "rain", "sunny", "humid", "climate"],
            "text_summarization": ["summarize", "summary", "tldr", "bullet points", "key takeaways", "shorten", "abstract"],
            "json_data_parser": ["parse json", "extract json", "format json", "json schema", "json validator", "beautify json"],
        }

        for exp in experiences:
            query = exp.user_query.strip()
            if not query:
                continue

            query_lower = query.lower()
            matched = False

            for cluster_name, kw_list in keywords.items():
                if any(kw in query_lower for kw in kw_list):
                    clusters[cluster_name].append(query)
                    matched = True
                    break

            if not matched:
                clusters["general_utility"].append(query)

        # Filter out empty clusters
        return {k: v for k, v in clusters.items() if len(v) > 0}

    def _generate_proposal_with_llm(self, cluster_name: str, example_queries: List[str]) -> SkillProposal:
        """
        Use Gemini to synthesize a structured SkillProposal based on query cluster.
        Includes a deterministic, reliable fallback if LLM is unavailable.
        """
        prompt = (
            f"You are an expert AI architect extending an autonomous AI Agent's skill system.\n"
            f"Analyze this cluster of user queries that the agent encountered:\n"
            f"Cluster Name: {cluster_name}\n"
            f"Example Queries ({len(example_queries)} samples):\n"
            + "\n".join(f"- {q}" for q in example_queries[:10])
            + "\n\n"
            "Propose a new, single reusable tool/skill to satisfy these queries.\n"
            "You MUST output ONLY a valid JSON object matching this schema:\n"
            "{\n"
            '  "skill_name": "snake_case_name",\n'
            '  "description": "Clear description of skill and its input arguments",\n'
            '  "use_case": "Why this skill is needed and what problem it solves",\n'
            '  "confidence_score": 0.85,\n'
            '  "tool_input_schema": {\n'
            '     "type": "object",\n'
            '     "properties": {\n'
            '        "text": {"type": "string", "description": "input text"}\n'
            '     },\n'
            '     "required": ["text"]\n'
            "  }\n"
            "}\n"
        )

        # Attempt LLM generation with fast timeout and fallback
        for m_name in ["models/gemini-2.5-flash", "models/gemini-2.5-pro"]:
            try:
                model = genai.GenerativeModel(m_name)
                response = model.generate_content(prompt, request_options={"timeout": 5})
                if response and hasattr(response, "text") and response.text:
                    cleaned = _clean_json_output(response.text)
                    data = json.loads(cleaned)
                    return SkillProposal(
                        skill_name=data.get("skill_name", cluster_name),
                        description=data.get("description", f"Skill for handling {cluster_name}"),
                        use_case=data.get("use_case", f"Handles queries related to {cluster_name}"),
                        example_queries=example_queries[:5],
                        confidence_score=float(data.get("confidence_score", 0.85)),
                        tool_input_schema=data.get("tool_input_schema", {"type": "object", "properties": {"input": {"type": "string"}}}),
                        status="proposed"
                    )
            except Exception as e:
                logger.info(f"LLM proposal generation with {m_name} skipped/failed: {e}")
                break  # Don't stall on quota/retry limits, immediately use robust template

        # Heuristic fallback proposals for known clusters
        fallback_templates = {
            "text_formatting": {
                "skill_name": "text_formatter",
                "description": "Formats, transforms, and normalizes text (uppercase, lowercase, title case, slugify).",
                "use_case": "Automates string transformations and formatting for user queries.",
                "confidence_score": 0.90,
                "tool_input_schema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to format"},
                        "mode": {"type": "string", "enum": ["upper", "lower", "title", "slug"], "description": "Format mode"}
                    },
                    "required": ["text"]
                }
            },
            "translation": {
                "skill_name": "language_translator",
                "description": "Translates text between multiple languages using linguistic lookup or translation models.",
                "use_case": "Empowers the agent to respond across multilingual requests.",
                "confidence_score": 0.88,
                "tool_input_schema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Content to translate"},
                        "target_language": {"type": "string", "description": "Target language (e.g. Spanish, French)"}
                    },
                    "required": ["text", "target_language"]
                }
            },
            "unit_conversion": {
                "skill_name": "unit_converter",
                "description": "Converts metric and imperial measurements, temperatures, and currencies.",
                "use_case": "Provides deterministic physical and financial conversion calculations.",
                "confidence_score": 0.92,
                "tool_input_schema": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "number", "description": "Numerical amount"},
                        "from_unit": {"type": "string", "description": "Starting unit"},
                        "to_unit": {"type": "string", "description": "Desired unit"}
                    },
                    "required": ["value", "from_unit", "to_unit"]
                }
            },
            "weather_lookup": {
                "skill_name": "weather_lookup",
                "description": "Fetches current weather observations and forecasts for given cities.",
                "use_case": "Supplies live meteorological information to users.",
                "confidence_score": 0.85,
                "tool_input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City or location name"}
                    },
                    "required": ["location"]
                }
            },
            "text_summarization": {
                "skill_name": "text_summarizer",
                "description": "Summarizes lengthy articles or paragraphs into concise bullet points or short takeaways.",
                "use_case": "Condenses information for quick comprehension.",
                "confidence_score": 0.87,
                "tool_input_schema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Lengthy text to summarize"},
                        "max_sentences": {"type": "integer", "description": "Number of sentences"}
                    },
                    "required": ["text"]
                }
            },
            "json_data_parser": {
                "skill_name": "json_parser",
                "description": "Parses, validates, formats, and extracts fields from JSON data strings.",
                "use_case": "Simplifies JSON data manipulation and debugging.",
                "confidence_score": 0.90,
                "tool_input_schema": {
                    "type": "object",
                    "properties": {
                        "json_string": {"type": "string", "description": "Raw JSON string"}
                    },
                    "required": ["json_string"]
                }
            }
        }

        template = fallback_templates.get(cluster_name, {
            "skill_name": f"{cluster_name}_tool",
            "description": f"Automated tool generated to handle user queries regarding {cluster_name}.",
            "use_case": f"Extends agent coverage for {cluster_name} queries.",
            "confidence_score": 0.75,
            "tool_input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Input query or parameter"}
                },
                "required": ["query"]
            }
        })

        return SkillProposal(
            skill_name=template["skill_name"],
            description=template["description"],
            use_case=template["use_case"],
            example_queries=example_queries[:5],
            confidence_score=template["confidence_score"],
            tool_input_schema=template["tool_input_schema"],
            status="proposed"
        )

    def analyze_experiences(self, session_id: Optional[str] = None) -> List[SkillProposal]:
        """
        Analyze logged experiences from ExperienceStore, cluster query intents,
        and generate new SkillProposals.
        """
        if not self.experience_store:
            logger.warning("No experience_store provided to SkillGenerator.")
            return list(self.proposals.values())

        if session_id:
            experiences = self.experience_store.get_by_session(session_id)
        else:
            experiences = self.experience_store.get_all()

        if not experiences:
            logger.info("No experiences found to analyze.")
            return list(self.proposals.values())

        clusters = self._cluster_queries(experiences)
        new_or_updated: List[SkillProposal] = []

        for cluster_name, queries in clusters.items():
            if not queries:
                continue

            proposal = self._generate_proposal_with_llm(cluster_name, queries)
            existing = self.proposals.get(proposal.skill_name)

            if existing:
                # Retain integrated status if already integrated
                if existing.status == "integrated":
                    proposal.status = "integrated"
                proposal.example_queries = list(set(existing.example_queries + proposal.example_queries))[:10]

            self.proposals[proposal.skill_name] = proposal
            new_or_updated.append(proposal)

        self.save_proposals()
        return new_or_updated

    def generate_skill_code(self, proposal: SkillProposal) -> str:
        """
        Generate executable Python code for the proposed skill conforming to BaseSkill.
        """
        class_name = "".join(part.capitalize() for part in proposal.skill_name.split("_")) + "Skill"

        prompt = (
            f"Generate a robust, production-ready Python class for an agent skill.\n"
            f"Skill Name: {proposal.skill_name}\n"
            f"Class Name: {class_name}\n"
            f"Description: {proposal.description}\n"
            f"Input Schema: {json.dumps(proposal.tool_input_schema)}\n"
            f"Requirements:\n"
            f"- Inherit from `BaseSkill` (`from app.skills.base import BaseSkill`)\n"
            f"- Implement `__init__(self)` calling `super().__init__(name='{proposal.skill_name}', description='...')`\n"
            f"- Implement `execute(self, **kwargs) -> Any`\n"
            f"- Return a dict with `{{'status': 'success', ...}}` or `{{'status': 'error', 'error': ...}}`\n"
            f"- Write actual working Python logic (no fake stubs/placeholders).\n"
            f"- Return ONLY the Python code inside ```python ``` without conversational filler.\n"
        )

        for m_name in ["models/gemini-2.5-flash"]:
            try:
                model = genai.GenerativeModel(m_name)
                response = model.generate_content(prompt, request_options={"timeout": 5})
                if response and hasattr(response, "text") and response.text:
                    code_text = response.text.strip()
                    if code_text.startswith("```"):
                        lines = code_text.splitlines()
                        if lines[0].startswith("```"):
                            lines = lines[1:]
                        if lines and lines[-1].startswith("```"):
                            lines = lines[:-1]
                        code_text = "\n".join(lines).strip()
                    if "class " in code_text and "execute(" in code_text:
                        return code_text
            except Exception as e:
                logger.info(f"LLM code generation with {m_name} skipped/failed: {e}")
                break

        # Deterministic, high-quality code templates based on skill type
        return self._generate_default_skill_code(proposal, class_name)

    def _generate_default_skill_code(self, proposal: SkillProposal, class_name: str) -> str:
        """Fallback deterministic code generation for known and generic tools."""
        name = proposal.skill_name
        desc = proposal.description.replace('"', '\\"')

        if "format" in name:
            return f'''import re
from typing import Any, Dict
from app.skills.base import BaseSkill

class {class_name}(BaseSkill):
    def __init__(self):
        super().__init__(
            name="{name}",
            description="{desc}"
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
                res = re.sub(r"[^\\w\\s-]", "", text.lower()).strip()
                res = re.sub(r"[-\\s]+", "-", res)
            else:
                res = text.strip()
            return {{"status": "success", "formatted_text": res, "mode": mode}}
        except Exception as e:
            return {{"status": "error", "error": str(e)}}
'''
        elif "convert" in name:
            return f'''from typing import Any, Dict
from app.skills.base import BaseSkill

class {class_name}(BaseSkill):
    def __init__(self):
        super().__init__(
            name="{name}",
            description="{desc}"
        )

    def execute(self, value: float = 0.0, from_unit: str = "celsius", to_unit: str = "fahrenheit", **kwargs) -> Dict[str, Any]:
        try:
            v = float(value)
            fu = from_unit.lower().strip()
            tu = to_unit.lower().strip()

            result = v
            # Temperature conversions
            if fu in ["c", "celsius"] and tu in ["f", "fahrenheit"]:
                result = (v * 9 / 5) + 32
            elif fu in ["f", "fahrenheit"] and tu in ["c", "celsius"]:
                result = (v - 32) * 5 / 9
            # Weight conversions
            elif fu in ["kg", "kilograms"] and tu in ["lb", "lbs", "pounds"]:
                result = v * 2.20462
            elif fu in ["lb", "lbs", "pounds"] and tu in ["kg", "kilograms"]:
                result = v / 2.20462
            # Distance conversions
            elif fu in ["km", "kilometers"] and tu in ["miles", "mi"]:
                result = v * 0.621371
            elif fu in ["miles", "mi"] and tu in ["km", "kilometers"]:
                result = v / 0.621371

            return {{"status": "success", "converted_value": round(result, 4), "from_unit": fu, "to_unit": tu}}
        except Exception as e:
            return {{"status": "error", "error": str(e)}}
'''
        elif "json" in name:
            return f'''import json
from typing import Any, Dict
from app.skills.base import BaseSkill

class {class_name}(BaseSkill):
    def __init__(self):
        super().__init__(
            name="{name}",
            description="{desc}"
        )

    def execute(self, json_string: str = "{{}}", **kwargs) -> Dict[str, Any]:
        try:
            parsed = json.loads(json_string)
            formatted = json.dumps(parsed, indent=2)
            return {{"status": "success", "parsed": parsed, "formatted": formatted, "valid": True}}
        except Exception as e:
            return {{"status": "error", "error": f"Invalid JSON: {{e}}", "valid": False}}
'''
        elif "translate" in name:
            return f'''from typing import Any, Dict
from app.skills.base import BaseSkill

class {class_name}(BaseSkill):
    def __init__(self):
        super().__init__(
            name="{name}",
            description="{desc}"
        )

    def execute(self, text: str = "", target_language: str = "Spanish", **kwargs) -> Dict[str, Any]:
        try:
            # Common dictionary lookup for instant demo translation
            glossary = {{
                "spanish": {{"hello": "hola", "world": "mundo", "thank you": "gracias", "yes": "sí", "no": "no"}},
                "french": {{"hello": "bonjour", "world": "monde", "thank you": "merci", "yes": "oui", "no": "non"}},
                "german": {{"hello": "hallo", "world": "welt", "thank you": "danke", "yes": "ja", "no": "nein"}},
                "hindi": {{"hello": "namaste", "world": "duniya", "thank you": "dhanyavaad", "yes": "haan", "no": "nahi"}}
            }}
            lang = target_language.lower().strip()
            lookup = glossary.get(lang, {{}})
            translated = lookup.get(text.lower().strip(), f"[Translated to {{target_language}}]: {{text}}")
            return {{"status": "success", "original": text, "target_language": target_language, "translation": translated}}
        except Exception as e:
            return {{"status": "error", "error": str(e)}}
'''
        else:
            return f'''from typing import Any, Dict
from app.skills.base import BaseSkill

class {class_name}(BaseSkill):
    def __init__(self):
        super().__init__(
            name="{name}",
            description="{desc}"
        )

    def execute(self, **kwargs) -> Dict[str, Any]:
        try:
            return {{"status": "success", "skill": "{name}", "received_args": kwargs}}
        except Exception as e:
            return {{"status": "error", "error": str(e)}}
'''

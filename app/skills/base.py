from abc import ABC, abstractmethod
from typing import Dict, List, Any

class BaseSkill(ABC):
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        pass


class SkillRegistry:
    def __init__(self):
        self.skills: Dict[str, BaseSkill] = {}

    def register_skill(self, skill: BaseSkill):
        self.skills[skill.name] = skill

    def get_skill(self, name: str) -> BaseSkill:
        return self.skills.get(name)

    def list_skills(self) -> List[Dict[str, str]]:
        return [
            {"name": skill.name, "description": skill.description}
            for skill in self.skills.values()
        ]

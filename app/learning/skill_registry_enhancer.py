import os
import sys
import logging
import importlib.util
import inspect
from typing import Optional, List, Union
from app.skills.base import BaseSkill, SkillRegistry
from app.learning.skill_generator import SkillProposal, SkillGenerator

logger = logging.getLogger(__name__)


class SkillRegistryEnhancer:
    def __init__(
        self,
        skill_registry: SkillRegistry,
        generator: Optional[SkillGenerator] = None,
        generated_skills_dir: str = "app/skills/generated"
    ):
        self.skill_registry = skill_registry
        self.generator = generator
        self.generated_skills_dir = generated_skills_dir

        # Ensure directory and package init file exist
        os.makedirs(self.generated_skills_dir, exist_ok=True)
        init_file = os.path.join(self.generated_skills_dir, "__init__.py")
        if not os.path.exists(init_file):
            with open(init_file, "w", encoding="utf-8") as f:
                f.write("# Auto-generated and learned skills\n")

        self.load_existing_skills()

    def load_existing_skills(self) -> List[str]:
        """Scan generated_skills_dir and load previously generated skills into skill_registry."""
        loaded: List[str] = []
        if not os.path.exists(self.generated_skills_dir):
            return loaded

        for fname in os.listdir(self.generated_skills_dir):
            if fname.endswith(".py") and not fname.startswith("__"):
                skill_name = fname[:-3]
                fpath = os.path.join(self.generated_skills_dir, fname)
                try:
                    module_name = f"app.skills.generated.{skill_name}"
                    spec = importlib.util.spec_from_file_location(module_name, fpath)
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        sys.modules[module_name] = mod
                        spec.loader.exec_module(mod)
                        for attr_name in dir(mod):
                            attr = getattr(mod, attr_name)
                            if (
                                inspect.isclass(attr)
                                and issubclass(attr, BaseSkill)
                                and attr is not BaseSkill
                            ):
                                inst = attr()
                                self.skill_registry.register_skill(inst)
                                loaded.append(inst.name)
                                break
                except Exception as e:
                    logger.warning(f"Failed to load existing generated skill {fname}: {e}")
        return loaded

    def integrate_proposal(self, proposal: Union[SkillProposal, str]) -> bool:
        """
        Takes a SkillProposal (or skill_name string), generates Python code,
        saves it to disk, dynamically imports it, registers it into the SkillRegistry,
        and marks the proposal as 'integrated'.
        """
        prop: Optional[SkillProposal] = None
        if isinstance(proposal, str):
            if not self.generator:
                logger.error("Cannot resolve proposal by name without a generator instance.")
                return False
            prop = self.generator.get_proposal(proposal)
            if not prop:
                logger.error(f"Proposal with name '{proposal}' not found.")
                return False
        else:
            prop = proposal

        try:
            # 1. Generate Python code
            if self.generator:
                code = self.generator.generate_skill_code(prop)
            else:
                dummy_gen = SkillGenerator()
                code = dummy_gen.generate_skill_code(prop)

            # 2. Write code to file in generated_skills_dir
            skill_file_path = os.path.join(self.generated_skills_dir, f"{prop.skill_name}.py")
            with open(skill_file_path, "w", encoding="utf-8") as f:
                f.write(code)

            # 3. Dynamically import the module
            module_name = f"app.skills.generated.{prop.skill_name}"
            spec = importlib.util.spec_from_file_location(module_name, skill_file_path)
            if spec is None or spec.loader is None:
                logger.error(f"Failed to create module spec for {skill_file_path}")
                return False

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # 4. Find the skill class inheriting from BaseSkill
            skill_cls = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    inspect.isclass(attr)
                    and issubclass(attr, BaseSkill)
                    and attr is not BaseSkill
                ):
                    skill_cls = attr
                    break

            if not skill_cls:
                logger.error(f"No BaseSkill subclass found in generated file {skill_file_path}")
                return False

            # 5. Instantiate and register in the SkillRegistry
            skill_instance = skill_cls()
            self.skill_registry.register_skill(skill_instance)
            logger.info(f"Successfully integrated skill: {skill_instance.name} ({skill_cls.__name__})")

            # 6. Update proposal status and persist
            prop.status = "integrated"
            if self.generator:
                self.generator.proposals[prop.skill_name] = prop
                self.generator.save_proposals()

            return True

        except Exception as e:
            logger.error(f"Error integrating proposal '{prop.skill_name}': {e}", exc_info=True)
            return False

    def auto_integrate_high_confidence(self, threshold: float = 0.8) -> List[str]:
        """
        Scan all proposals with status 'proposed' and confidence >= threshold,
        then automatically generate and register them.
        """
        if not self.generator:
            return []

        integrated_names: List[str] = []
        proposals = self.generator.get_proposals(status="proposed")

        for prop in proposals:
            if prop.confidence_score >= threshold:
                success = self.integrate_proposal(prop)
                if success:
                    integrated_names.append(prop.skill_name)

        return integrated_names

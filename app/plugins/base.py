import os
import re
import yaml
import logging
import importlib
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Any, Dict, List

logger = logging.getLogger(__name__)


def _resolve_env_vars(data: Any) -> Any:
    """Recursively resolve environment variables formatted as ${VAR_NAME} or $VAR_NAME."""
    if isinstance(data, str):
        pattern = re.compile(r"\$\{([A-Za-z0-9_]+)\}")
        return pattern.sub(lambda m: os.getenv(m.group(1), ""), data)
    elif isinstance(data, dict):
        return {k: _resolve_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_resolve_env_vars(item) for item in data]
    return data


class PluginType(Enum):
    MODEL = "MODEL"
    MEMORY = "MEMORY"
    TOOL = "TOOL"
    ROUTER = "ROUTER"
    GATEWAY = "GATEWAY"


class Plugin(ABC):
    @abstractmethod
    def get_name(self) -> str:
        """Unique name of the plugin."""
        pass

    @abstractmethod
    def get_type(self) -> PluginType:
        """The category the plugin belongs to."""
        pass

    @abstractmethod
    def get_schema(self) -> dict:
        """Input/output details in JSON Schema format (e.g., for tool calling)."""
        pass

    @abstractmethod
    def initialize(self, config: dict) -> None:
        """Initialize the plugin with configuration (API keys, paths, etc.).
        Include error handling here.
        """
        pass

    @abstractmethod
    def execute(self, input_data: dict) -> dict:
        """Main plugin logic. Accept input, perform the task, and return output."""
        pass

    @abstractmethod
    def validate_config(self, config: dict) -> bool:
        """Validate the configuration."""
        pass


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}

    def register(self, plugin: Plugin) -> None:
        """Add the plugin to the registry. Raise an error if the name already exists."""
        name = plugin.get_name()
        if name in self._plugins:
            raise ValueError(f"Plugin with name '{name}' is already registered.")
        self._plugins[name] = plugin

    def unregister(self, name: str) -> None:
        """Remove the plugin from the registry."""
        if name in self._plugins:
            del self._plugins[name]

    def get(self, name: str) -> Optional[Plugin]:
        """Find a plugin by name."""
        return self._plugins.get(name)

    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Alias for get(name)."""
        return self.get(name)

    def list_plugins(self, plugin_type: Optional[PluginType] = None) -> list[Plugin]:
        """List all plugins. If plugin_type is provided, show only plugins of that category."""
        if plugin_type is None:
            return list(self._plugins.values())
        return [plugin for plugin in self._plugins.values() if plugin.get_type() == plugin_type]

    def get_plugins_by_type(self, plugin_type: PluginType) -> list[Plugin]:
        """Alias for list_plugins(plugin_type)."""
        return self.list_plugins(plugin_type)

    def load_from_config(self, config_path: str) -> None:
        """Load and initialize plugins dynamically from a YAML configuration file."""
        if not os.path.exists(config_path):
            logger.warning(f"Plugin configuration file not found at: {config_path}")
            return

        with open(config_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)

        if not raw_data:
            logger.warning(f"Configuration file {config_path} is empty.")
            return

        data = _resolve_env_vars(raw_data)
        plugin_entries = data.get("plugins", [])
        if not isinstance(plugin_entries, list):
            logger.warning("Invalid configuration format: 'plugins' must be a list.")
            return

        for entry in plugin_entries:
            if not isinstance(entry, dict):
                continue

            class_path = entry.get("class")
            config = entry.get("config", {}) or {}
            enabled = entry.get("enabled", True)

            if not enabled:
                continue

            if not class_path:
                logger.warning(f"Missing 'class' field in plugin configuration: {entry}")
                continue

            try:
                # 1. Dynamically import class
                module_name, class_name = class_path.rsplit(".", 1)
                module = importlib.import_module(module_name)
                plugin_cls = getattr(module, class_name)

                # 2. Create plugin instance
                plugin_instance = plugin_cls()

                # Dependency Injection: if plugin is TOOL and needs a memory_plugin
                if plugin_instance.get_type() == PluginType.TOOL:
                    mem_ref = config.get("memory_plugin")
                    if isinstance(mem_ref, str):
                        # Find by specific plugin name
                        mem_plugin = self.get(mem_ref)
                        if mem_plugin:
                            config["memory_plugin"] = mem_plugin
                        else:
                            # Search by registered memory plugins
                            memory_plugins = self.list_plugins(PluginType.MEMORY)
                            if memory_plugins:
                                config["memory_plugin"] = memory_plugins[0]
                    elif "memory_plugin" in config and config["memory_plugin"] is None:
                        memory_plugins = self.list_plugins(PluginType.MEMORY)
                        if memory_plugins:
                            config["memory_plugin"] = memory_plugins[0]

                # 3. Validate config
                if not plugin_instance.validate_config(config):
                    logger.warning(f"Config validation failed for plugin '{class_path}' with config {config}")
                    continue

                # 4. Initialize plugin
                plugin_instance.initialize(config)

                # 5. Register plugin
                self.register(plugin_instance)
                logger.info(f"Successfully loaded and registered plugin: {plugin_instance.get_name()} ({class_path})")

            except Exception as e:
                logger.warning(f"Failed to load plugin from '{class_path}': {e}")


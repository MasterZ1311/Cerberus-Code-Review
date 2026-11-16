"""
Dynamic Plugin System Architecture for cerberus</>.
Allows modular extension of review agents, language heuristics, pre/post review hooks,
and enterprise compliance policies without modifying core engine files.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    pass
from cerberus.models.schemas import CodeReviewRequest, CodeReviewResponse

logger = logging.getLogger("cerberus.plugins")


class BasePlugin:
    """Base class for all Cerberus extensions and custom plugins."""

    name: str = "base_plugin"
    version: str = "1.0.0"
    description: str = "Base plugin interface"
    author: str = "Cerberus Team"
    is_enabled: bool = True

    def on_load(self, app: Optional[Any] = None) -> None:
        """Invoked upon plugin registration and initialization."""
        pass

    def on_unload(self) -> None:
        """Invoked upon plugin deregistration and cleanup."""
        pass

    def get_custom_agents(self) -> List[Any]:
        """Returns specialized autonomous agents contributed by this plugin."""
        return []

    def get_custom_rules(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Returns custom language AST/regex rules contributed by this plugin.
        Structure: { 'python': [ { 'id': 'CUSTOM-01', 'severity': 'HIGH', ... } ] }
        """
        return {}

    async def pre_review_hook(self, request: CodeReviewRequest) -> CodeReviewRequest:
        """Optional hook executed before multi-agent review starts."""
        return request

    async def post_review_hook(self, response: CodeReviewResponse) -> CodeReviewResponse:
        """Optional hook executed after multi-agent consensus and patch generation."""
        return response


class PluginManager:
    """Manages plugin discovery, lifecycle, hook pipelines, and orchestrator synchronization."""

    def __init__(self):
        self._plugins: Dict[str, BasePlugin] = {}
        self._orchestrator: Optional[Any] = None
        self._lock = asyncio.Lock()

    def set_orchestrator(self, orchestrator: Any) -> None:
        """Binds the active ReviewOrchestrator to receive custom agents and hooks."""
        self._orchestrator = orchestrator
        # Synchronize already loaded plugins
        for plugin in self._plugins.values():
            if plugin.is_enabled:
                self._apply_plugin_to_orchestrator(plugin)

    def _apply_plugin_to_orchestrator(self, plugin: BasePlugin) -> None:
        """Registers a plugin's agents and hooks with the orchestrator."""
        if not self._orchestrator:
            return

        # Register custom agents
        for agent in plugin.get_custom_agents():
            logger.info("Plugin '%s' registered custom agent '%s'", plugin.name, agent.name)
            self._orchestrator.register_agent(agent.name, agent)

        # Register custom rules into HeuristicEngine if available
        custom_rules = plugin.get_custom_rules()
        if custom_rules:
            try:
                from cerberus.providers.heuristic_engine import HeuristicEngine

                for lang, rules in custom_rules.items():
                    logger.info("Plugin '%s' registered %d custom rule(s) for '%s'", plugin.name, len(rules), lang)
                    HeuristicEngine.register_custom_rules(lang, rules)
            except Exception as e:
                logger.warning("Could not register custom rules for plugin '%s': %s", plugin.name, e)

    def register_plugin(self, plugin: BasePlugin) -> None:
        """Registers and activates a new plugin."""
        name = plugin.name
        if name in self._plugins:
            logger.warning("Plugin '%s' is already registered. Overwriting with new instance.", name)

        self._plugins[name] = plugin
        try:
            plugin.on_load()
        except Exception as e:
            logger.error("Error during on_load for plugin '%s': %s", name, e)

        if plugin.is_enabled and self._orchestrator:
            self._apply_plugin_to_orchestrator(plugin)

        logger.info("Successfully registered plugin: %s v%s", name, plugin.version)

    def unregister_plugin(self, name: str) -> bool:
        """Unloads and removes a plugin."""
        if name not in self._plugins:
            return False

        plugin = self._plugins.pop(name)
        try:
            plugin.on_unload()
        except Exception as e:
            logger.error("Error during on_unload for plugin '%s': %s", name, e)

        logger.info("Unregistered plugin: %s", name)
        return True

    def enable_plugin(self, name: str) -> bool:
        """Enables a registered plugin."""
        self.ensure_builtins()
        plugin = self._plugins.get(name)
        if not plugin:
            return False
        plugin.is_enabled = True
        if self._orchestrator:
            self._apply_plugin_to_orchestrator(plugin)
        logger.info("Enabled plugin: %s", name)
        return True

    def disable_plugin(self, name: str) -> bool:
        """Disables a registered plugin."""
        self.ensure_builtins()
        plugin = self._plugins.get(name)
        if not plugin:
            return False
        plugin.is_enabled = False
        logger.info("Disabled plugin: %s", name)
        return True

    def ensure_builtins(self) -> None:
        """Loads default enterprise plugins if not already loaded."""
        if getattr(self, "_builtins_loaded", False):
            return
        self._builtins_loaded = True
        try:
            from cerberus.plugins.secret_scanner import CustomSecretScannerPlugin
            from cerberus.plugins.team_style import TeamStyleConventionsPlugin

            self.register_plugin(CustomSecretScannerPlugin())
            self.register_plugin(TeamStyleConventionsPlugin())
        except Exception as e:
            logger.warning("Could not auto-load built-in plugins: %s", e)

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        """Retrieves a registered plugin by name."""
        self.ensure_builtins()
        return self._plugins.get(name)

    def list_plugins(self) -> List[Dict[str, Any]]:
        """Returns structured metadata for all registered plugins."""
        self.ensure_builtins()
        return [
            {
                "name": p.name,
                "version": p.version,
                "description": p.description,
                "author": p.author,
                "is_enabled": p.is_enabled,
                "custom_agents": [a.name for a in p.get_custom_agents()],
                "custom_rules_count": sum(len(rules) for rules in p.get_custom_rules().values()),
            }
            for p in self._plugins.values()
        ]

    async def execute_pre_review_hooks(self, request: CodeReviewRequest) -> CodeReviewRequest:
        """Executes all enabled plugin pre-review hooks in sequence."""
        self.ensure_builtins()
        current = request
        for plugin in self._plugins.values():
            if not plugin.is_enabled:
                continue
            try:
                hook_res: Any = plugin.pre_review_hook(current)
                if asyncio.iscoroutine(hook_res):
                    hook_res = await hook_res
                if isinstance(hook_res, CodeReviewRequest):
                    current = hook_res
            except Exception as e:
                logger.warning("Plugin '%s' pre_review_hook failed: %s", plugin.name, e)
        return current

    async def execute_post_review_hooks(self, response: CodeReviewResponse) -> CodeReviewResponse:
        """Executes all enabled plugin post-review hooks in sequence."""
        self.ensure_builtins()
        current = response
        for plugin in self._plugins.values():
            if not plugin.is_enabled:
                continue
            try:
                hook_res: Any = plugin.post_review_hook(current)
                if asyncio.iscoroutine(hook_res):
                    hook_res = await hook_res
                if isinstance(hook_res, CodeReviewResponse):
                    current = hook_res
            except Exception as e:
                logger.warning("Plugin '%s' post_review_hook failed: %s", plugin.name, e)
        return current


# Global singleton instance
plugin_manager = PluginManager()


def load_builtin_plugins() -> None:
    """Loads default enterprise plugins for secrets and team style conventions."""
    plugin_manager.ensure_builtins()

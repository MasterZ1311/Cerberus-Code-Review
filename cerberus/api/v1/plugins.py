"""
Plugins Management Router for cerberus</>.
Allows administrative inspection, dynamic enabling, disabling, and hot-reloading of custom plugins.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from cerberus.api.dependencies import require_scopes, verify_api_key
from cerberus.core.plugins import plugin_manager

router = APIRouter(prefix="/api/v1/plugins", tags=["Plugins & Extensions"])


@router.get("", status_code=status.HTTP_200_OK)
async def list_plugins(token: str = Depends(verify_api_key)) -> Dict[str, Any]:
    """Returns metadata for all installed and active Cerberus plugins."""
    plugins = plugin_manager.list_plugins()
    return {
        "total": len(plugins),
        "plugins": plugins,
    }


@router.post("/{name}/enable", status_code=status.HTTP_200_OK)
async def enable_plugin(
    name: str,
    token: str = Depends(require_scopes("admin")),
) -> Dict[str, Any]:
    """Enables a registered plugin (Requires 'admin' scope)."""
    success = plugin_manager.enable_plugin(name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "plugin_not_found", "message": f"Plugin '{name}' not found"},
        )
    return {"status": "success", "message": f"Plugin '{name}' enabled successfully", "plugin": name}


@router.post("/{name}/disable", status_code=status.HTTP_200_OK)
async def disable_plugin(
    name: str,
    token: str = Depends(require_scopes("admin")),
) -> Dict[str, Any]:
    """Disables a registered plugin (Requires 'admin' scope)."""
    success = plugin_manager.disable_plugin(name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "plugin_not_found", "message": f"Plugin '{name}' not found"},
        )
    return {"status": "success", "message": f"Plugin '{name}' disabled successfully", "plugin": name}


@router.post("/{name}/reload", status_code=status.HTTP_200_OK)
async def reload_plugin(
    name: str,
    token: str = Depends(require_scopes("admin")),
) -> Dict[str, Any]:
    """Hot-reloads a registered plugin (Requires 'admin' scope)."""
    plugin = plugin_manager.get_plugin(name)
    if not plugin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "plugin_not_found", "message": f"Plugin '{name}' not found"},
        )

    try:
        plugin.on_unload()
        plugin.on_load()
        return {"status": "success", "message": f"Plugin '{name}' hot-reloaded successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "reload_failed", "message": str(e)},
        ) from e


@router.post("/reload", status_code=status.HTTP_200_OK)
async def reload_all_plugins(
    token: str = Depends(require_scopes("admin")),
) -> Dict[str, Any]:
    """Hot-reloads all registered plugins across the system."""
    plugin_manager.ensure_builtins()
    reloaded_names = []
    for p in list(plugin_manager._plugins.values()):
        try:
            p.on_unload()
            p.on_load()
            reloaded_names.append(p.name)
        except Exception:
            pass
    return {"status": "success", "reloaded": True, "count": len(reloaded_names), "plugins": reloaded_names}

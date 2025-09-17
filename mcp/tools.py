"""Tools exposed by the minimal MCP server."""

from __future__ import annotations

import json
import platform
from typing import Any, Dict

import psutil


def get_host_info() -> str:
    """Collect basic host metadata and return it as a JSON string."""
    virtual_mem = psutil.virtual_memory()

    info: Dict[str, Any] = {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "memory_gb": round(virtual_mem.total / (1024 ** 3), 2),
        "available_memory_gb": round(virtual_mem.available / (1024 ** 3), 2),
        "cpu_count": psutil.cpu_count(logical=True),
    }

    return json.dumps(info)


__all__ = ["get_host_info"]

from functools import wraps
from typing import Any, Callable

def reporting_tool(name: str, description_ar: str, required_permission: str) -> Callable:
    """
    Decorator for official system reports (FR-1501).
    Captures metadata for introspection by the AI Copilot.
    """
    def decorator(func: Callable) -> Callable:
        setattr(func, "__report_meta__", {
            "name": name,
            "description_ar": description_ar,
            "required_permission": required_permission
        })
        
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs)
        return wrapper
    return decorator

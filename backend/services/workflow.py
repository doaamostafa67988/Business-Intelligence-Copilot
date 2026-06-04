"""
Workflow service proxy.

main.py imports from services.workflow — this re-exports
the compiled graph from agents.workflow so the import path is clean.
"""
from agents.workflow import get_workflow, build_workflow

__all__ = ["get_workflow", "build_workflow"]

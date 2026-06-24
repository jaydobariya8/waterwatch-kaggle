"""The WaterWatch agent pipeline.

An orchestrator coordinates six small, single-purpose specialists, wired with ADK-style
workflow primitives (SequentialAgent, LoopAgent, AgentTool). Each specialist is exposed
to the root agent as a tool; the Verifier is a LoopAgent critic that blocks any uncited
claim. See :mod:`waterwatch.agents.base` for the primitives and
:mod:`waterwatch.agents.orchestrator` for the wiring.
"""

from __future__ import annotations

from .orchestrator import Orchestrator, get_orchestrator

__all__ = ["Orchestrator", "get_orchestrator"]

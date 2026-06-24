"""ADK-style agent primitives.

These mirror the Agent Development Kit's workflow building blocks — a base ``Agent``, an
``AgentTool`` wrapper for grounding tools, and the ``SequentialAgent`` / ``ParallelAgent``
/ ``LoopAgent`` orchestrators. Implementing them locally keeps the system runnable with
zero cloud dependencies while reading exactly like the ADK design in the project plan; the
README documents the one-to-one mapping to the real ADK classes.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from ..llm import GeminiClient
from ..schemas import AnalyzeRequest, TraceStep

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    """Shared session state threaded through the pipeline (the Day-3 'memory')."""

    request: AnalyzeRequest
    llm: GeminiClient
    state: dict[str, Any] = field(default_factory=dict)
    trace: list[TraceStep] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    def add_trace(
        self,
        agent: str,
        title: str,
        detail: str,
        *,
        status: str = "ok",
        duration_ms: int | None = None,
    ) -> None:
        self.trace.append(
            TraceStep(agent=agent, title=title, detail=detail, status=status, duration_ms=duration_ms)
        )

    def record_tool_call(self, tool: str, args: dict[str, Any]) -> None:
        self.tool_calls.append({"tool": tool, "args": args})


class Agent(ABC):
    """Base class: a small, single-purpose unit of work that mutates the context."""

    name: str = "agent"
    title: str = ""

    @abstractmethod
    def run(self, ctx: AgentContext) -> None: ...

    def _timed(self, ctx: AgentContext, fn: Callable[[], str], *, status: str = "ok") -> None:
        start = time.perf_counter()
        detail = fn()
        elapsed = int((time.perf_counter() - start) * 1000)
        ctx.add_trace(self.name, self.title or self.name, detail, status=status, duration_ms=elapsed)


class AgentTool:
    """Wrap a grounding tool (a data-layer function) so an agent can call it and have the
    call recorded — making the tool use visible in the trace (the Day-2 story)."""

    def __init__(self, name: str, fn: Callable[..., Any]) -> None:
        self.name = name
        self._fn = fn

    def __call__(self, ctx: AgentContext, **kwargs: Any) -> Any:
        ctx.record_tool_call(self.name, kwargs)
        return self._fn(**kwargs)


class SequentialAgent(Agent):
    """Run children in order — the Parser → Standards → Health spine."""

    def __init__(self, name: str, children: list[Agent]) -> None:
        self.name = name
        self.children = children

    def run(self, ctx: AgentContext) -> None:
        for child in self.children:
            child.run(ctx)


class ParallelAgent(Agent):
    """Run children independently (semantics; executed sequentially here)."""

    def __init__(self, name: str, children: list[Agent]) -> None:
        self.name = name
        self.children = children

    def run(self, ctx: AgentContext) -> None:
        for child in self.children:
            child.run(ctx)


class LoopAgent(Agent):
    """Run ``body`` repeatedly until ``is_done`` returns True or the budget is exhausted.

    This is the Verifier's 'critic' pattern: keep correcting until the report is clean.
    """

    def __init__(
        self,
        name: str,
        body: Agent,
        is_done: Callable[[AgentContext], bool],
        max_iterations: int = 3,
    ) -> None:
        self.name = name
        self.body = body
        self.is_done = is_done
        self.max_iterations = max_iterations

    def run(self, ctx: AgentContext) -> None:
        iterations = 0
        while iterations < self.max_iterations:
            iterations += 1
            ctx.state["_loop_iteration"] = iterations
            self.body.run(ctx)
            if self.is_done(ctx):
                break
        ctx.state["_loop_iterations_used"] = iterations

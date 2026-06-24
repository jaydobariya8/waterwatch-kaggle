"""WaterWatch — a verifiable, civic-action multi-agent system for drinking-water safety.

The package never asserts a number or a health claim it cannot cite: limits come from a
bundled BIS 10500 table and health effects from a curated WHO/BIS knowledge base, and a
dedicated Verifier agent blocks any uncited statement.
"""

from __future__ import annotations

__version__ = "1.0.0"
__all__ = ["__version__"]

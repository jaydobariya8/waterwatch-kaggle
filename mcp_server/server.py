"""WaterWatch MCP server (Day-2 concept).

Exposes the grounded data layer as a Model Context Protocol server so the limits, area
data, treatment KB and health KB are clean, discoverable, and reusable tools — the same
functions the in-process agents call. Run standalone over stdio with:

    python -m mcp_server.server

The tools wrap :mod:`waterwatch.data_layer`, which is the single source of truth, so the
MCP surface and the in-process agents can never disagree.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the sibling ``waterwatch`` package importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from waterwatch import data_layer  # noqa: E402

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - optional dependency
    raise SystemExit(
        "The 'mcp' package is required to run the MCP server. Install it with: pip install mcp"
    ) from exc

mcp = FastMCP("waterwatch-mcp")


@mcp.tool()
def get_bis_limit(param: str) -> dict:
    """Return the BIS 10500 acceptable + permissible limit for a parameter, with citation."""
    return data_layer.get_bis_limit(param)


@mcp.tool()
def evaluate_sample(params: dict[str, float]) -> list[dict]:
    """Evaluate a full sample (param -> value) against BIS 10500. Returns cited breaches."""
    return data_layer.evaluate_sample(params)


@mcp.tool()
def get_area_readings(pincode: str) -> dict:
    """Return recent official water-quality readings for a pincode (bundled snapshot)."""
    return data_layer.get_area_readings(pincode)


@mcp.tool()
def match_filtration(contaminants: list[str]) -> list[dict]:
    """Map contaminants to the cheapest effective treatment for each, with citation."""
    return data_layer.match_filtration(contaminants)


@mcp.tool()
def health_effect(contaminant: str) -> dict:
    """Return a cited, plain-language health-impact summary for a contaminant."""
    return data_layer.health_effect(contaminant)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

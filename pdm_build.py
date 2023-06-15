"""PDM build hook to generate dynamic README.
"""
from __future__ import annotations

from pathlib import Path

from pdm.backend.hooks import Context


def pdm_build_initialize(context: Context) -> None:
    """Generate README by concatenating README.md and CHANGES.md"""
    metadata = context.config.metadata
    if "readme" in metadata.get("dynamic", []):
        metadata["dynamic"].remove("readme")
        metadata["readme"] = {
            "text": compute_readme(context.root),
            "content-type": "text/markdown",
        }


def compute_readme(root: Path) -> str:
    readme = root / "README.md"
    changes = root / "CHANGES.md"
    return "\n".join(
        file.read_text("utf-8").rstrip() + "\n" for file in (readme, changes)
    )

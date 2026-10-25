from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def project_root() -> Path:
    """Find the checkout containing config/ and data/mock/.

    ONTOLOGY_FDE_HOME makes the boundary explicit in packaged deployments.  In a checkout,
    both an editable installation and PYTHONPATH=src work without extra configuration.
    """

    configured = os.environ.get("ONTOLOGY_FDE_HOME")
    candidates = [Path(configured)] if configured else []
    candidates.extend([Path.cwd(), *Path.cwd().parents])
    here = Path(__file__).resolve()
    candidates.extend([here.parent, *here.parents])
    for candidate in candidates:
        if (candidate / "config").is_dir() and (candidate / "data" / "mock").is_dir():
            return candidate
    raise RuntimeError(
        "Cannot locate ontology-fde-practical-guide. Run from the repository or set "
        "ONTOLOGY_FDE_HOME."
    )


def load_structured(relative_path: str | Path) -> Any:
    """Load JSON or JSON-subset YAML using only the Python standard library."""

    path = project_root() / relative_path
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )

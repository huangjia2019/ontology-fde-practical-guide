#!/usr/bin/env python3
"""Preserve the named publication regressions while allowing new tests."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def discovered_test_methods() -> set[str]:
    found = set()
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test_"):
                        found.add(f"{path.stem}.{node.name}.{item.name}")
    return found


def main() -> int:
    baseline = json.loads((ROOT / "config/evals/published_test_baseline.json").read_text(encoding="utf-8"))
    required = set(baseline["required_test_methods"])
    found = discovered_test_methods()
    errors = [f"Missing original regression: {name}" for name in sorted(required - found)]
    for filename, key in (("golden_set_v1.json", "golden_cases"), ("incident_replays.json", "incident_replays")):
        cases = json.loads((ROOT / "config/evals" / filename).read_text(encoding="utf-8"))["cases"]
        if len(cases) < baseline[key]:
            errors.append(f"{filename}: expected at least {baseline[key]} cases; got {len(cases)}")
    if errors:
        print("\n".join(errors))
        return 1
    print(f"PASS: original {baseline['publication_baseline']} + {baseline['delivery_checks_at_baseline']} regressions retained; {len(found - required)} added; {len(found)} test methods discovered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

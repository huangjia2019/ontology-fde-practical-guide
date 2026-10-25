#!/usr/bin/env python3
"""Run the book's local example without installation or PYTHONPATH setup."""

import os
import sys
from pathlib import Path


def main():
    if sys.version_info < (3, 11):
        print(
            "本项目需要 Python 3.11 或更高版本。当前是 Python "
            + ".".join(map(str, sys.version_info[:3]))
            + "。安装新版后，请用对应解释器运行，例如 python3.12 run.py serve。",
            file=sys.stderr,
        )
        return 2
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root / "src"))
    os.chdir(root)
    from ontology_fde.cli import main as cli_main

    cli_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

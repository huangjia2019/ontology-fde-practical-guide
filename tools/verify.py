#!/usr/bin/env python3
"""Run the offline release checks on macOS, Linux, or Windows."""

import os
from pathlib import Path
import subprocess
import sys


def main():
    if sys.version_info < (3, 11):
        print("需要 Python 3.11 或更高版本。先运行 python3 --version 检查。", file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    env["PYTHONUTF8"] = "1"
    env.pop("ONTOLOGY_FDE_HOME", None)
    steps = [
        ("读者链接与界面图", ["tools/verify_book_assets.py"]),
        ("出版回归基线", ["tools/verify_release_baseline.py"]),
        ("单元及集成测试", ["-m", "unittest", "discover", "-s", "tests", "-v"]),
        ("黄金样例、事故回放与规则验证", ["run.py", "evaluate", "--output", "artifacts/evaluation-report.json"]),
        ("完整示例", ["run.py", "demo", "--output", "artifacts/demo"]),
    ]
    steps += [(f"第 {n} 站检查", ["run.py", "checkpoint", str(n), "--check"]) for n in range(1, 11)]
    steps += [("退出与交接演练", ["run.py", "exit-drill"])]
    for name, args in steps:
        print(f"\n检查：{name}", flush=True)
        try:
            result = subprocess.run(
                [sys.executable, *args], cwd=root, env=env,
                capture_output=True, text=True, encoding="utf-8", timeout=120,
            )
        except subprocess.TimeoutExpired:
            print(f"FAIL: {name} 超过 120 秒，检查已停止。", file=sys.stderr)
            return 1
        if result.returncode:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            return result.returncode
        if "unittest" in args:
            print("\n".join(result.stderr.strip().splitlines()[-4:]))
        else:
            print(f"PASS: {name}")
    print("\n全部离线检查通过。运行材料保存在 artifacts/，没有连接企业系统。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

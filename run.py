#!/usr/bin/env python3
"""tasks.yaml に定義されたスクリプトをフェーズ単位または個別に実行する。"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

from utils.logger import RotatingLogFile

ROOT = Path(__file__).resolve().parent
TASKS_FILE = ROOT / "tasks.yaml"


def load_tasks() -> dict:
    with TASKS_FILE.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_scripts(tasks: dict, phase: str | None, script_path: str | None) -> list[dict]:
    if script_path:
        normalized = script_path.replace("\\", "/")
        for phase_name, phase_def in tasks["phases"].items():
            for entry in phase_def.get("scripts", []):
                if entry["path"].replace("\\", "/") == normalized:
                    return [{**entry, "phase": phase_name}]
        raise SystemExit(f"tasks.yaml に未定義のスクリプト: {script_path}")

    if not phase:
        raise SystemExit("--phase または --script を指定してください")

    if phase == "all":
        result: list[dict] = []
        for phase_name in ("collect", "process"):
            phase_def = tasks["phases"].get(phase_name, {})
            for entry in phase_def.get("scripts", []):
                result.append({**entry, "phase": phase_name})
        return result

    phase_def = tasks["phases"].get(phase)
    if not phase_def:
        raise SystemExit(f"未知のフェーズ: {phase}")
    return [{**entry, "phase": phase} for entry in phase_def.get("scripts", [])]


def run_script(entry: dict, python_exe: str, continue_on_error: bool) -> int:
    script = ROOT / entry["path"]
    log_path = ROOT / entry.get("log", f"logs/{script.stem}.log")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = f"{'=' * 48}\n{timestamp} - タスク開始 ({entry['path']})\n"

    print(f"[RUN] {entry['path']}")
    with RotatingLogFile(log_path) as log_file:
        log_file.write(header)

        result = subprocess.run(
            [python_exe, str(script)],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )

        footer = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - タスク終了 ({entry['path']})\n{'=' * 48}\n"
        log_file.write(footer)

    if result.returncode != 0:
        print(f"[FAIL] {entry['path']} (exit {result.returncode})", file=sys.stderr)
        if not continue_on_error:
            return result.returncode
    else:
        print(f"[OK]   {entry['path']}")
    return result.returncode


def list_scripts(tasks: dict) -> None:
    for phase_name, phase_def in tasks["phases"].items():
        print(f"\n[{phase_name}] {phase_def.get('description', '')}")
        for entry in phase_def.get("scripts", []):
            schedule = phase_def.get("schedule", "")
            print(f"  {entry['path']:<55} {entry.get('name', '')} ({schedule})")


def main() -> None:
    parser = argparse.ArgumentParser(description="tasks.yaml に基づいてスクリプトを実行")
    parser.add_argument(
        "--phase",
        choices=["collect", "process", "manual", "all"],
        help="実行するフェーズ（all = collect + process）",
    )
    parser.add_argument("--script", help="単一スクリプトのパス（tasks.yaml 内の path）")
    parser.add_argument("--list", action="store_true", help="登録スクリプト一覧を表示")
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="使用する Python 実行ファイル",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="エラーがあっても後続スクリプトを実行",
    )
    args = parser.parse_args()

    tasks = load_tasks()

    if args.list:
        list_scripts(tasks)
        return

    entries = resolve_scripts(tasks, args.phase, args.script)
    if not entries:
        print("実行対象がありません")
        return

    exit_code = 0
    for entry in entries:
        code = run_script(entry, args.python, args.continue_on_error)
        if code != 0 and not args.continue_on_error:
            sys.exit(code)
        if code != 0:
            exit_code = code

    sys.exit(exit_code)


if __name__ == "__main__":
    main()

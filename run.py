#!/usr/bin/env python3
"""tasks.yaml に定義されたスクリプトをフェーズ単位または個別に実行する。"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

from utils.logger import RotatingLogFile, setup_logger

ROOT = Path(__file__).resolve().parent
TASKS_FILE = ROOT / "tasks.yaml"
RUN_LOG = "run.log"

logger = logging.getLogger(__name__)


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


def run_script(
    entry: dict,
    python_exe: str,
    continue_on_error: bool,
    index: int,
    total: int,
) -> int:
    script = ROOT / entry["path"]
    log_path = ROOT / entry.get("log", f"logs/{script.stem}.log")
    label = entry.get("name") or entry["path"]

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = f"{'=' * 48}\n{timestamp} - タスク開始 ({entry['path']})\n"

    logger.info(
        "[%d/%d] スクリプト実行開始: %s (%s) → %s",
        index,
        total,
        label,
        entry["path"],
        log_path,
    )
    with RotatingLogFile(log_path) as log_file:
        log_file.write(header)
        log_file.flush()

        result = subprocess.run(
            [python_exe, str(script)],
            cwd=ROOT,
            env={
                **os.environ,
                "PYTHONPATH": str(ROOT),
                # 子プロセスの標準出力を UTF-8 に統一し、ログの文字化けを防ぐ。
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
            },
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )

        footer = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - タスク終了 ({entry['path']})\n{'=' * 48}\n"
        log_file.write(footer)

    if result.returncode != 0:
        logger.error(
            "[%d/%d] スクリプト失敗: %s (exit %d)",
            index,
            total,
            entry["path"],
            result.returncode,
        )
        if not continue_on_error:
            return result.returncode
    else:
        logger.info("[%d/%d] スクリプト完了: %s", index, total, entry["path"])
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

    setup_logger(RUN_LOG)

    mode = f"phase={args.phase}" if args.phase else f"script={args.script}"
    logger.info(
        "実行開始 (%s, python=%s, continue_on_error=%s)",
        mode,
        args.python,
        args.continue_on_error,
    )
    logger.info("実行対象: %d 件", len(entries))
    for i, entry in enumerate(entries, 1):
        label = entry.get("name") or entry["path"]
        logger.info("  予定 [%d] [%s] %s - %s", i, entry["phase"], entry["path"], label)

    total = len(entries)
    exit_code = 0
    prev_phase: str | None = None
    for i, entry in enumerate(entries, 1):
        phase = entry["phase"]
        if phase != prev_phase:
            logger.info("--- フェーズ開始: %s ---", phase)
            prev_phase = phase

        code = run_script(entry, args.python, args.continue_on_error, i, total)
        if code != 0 and not args.continue_on_error:
            logger.error("エラーにより実行を中断 (exit %d)", code)
            sys.exit(code)
        if code != 0:
            exit_code = code

    if exit_code == 0:
        logger.info("全 %d 件のスクリプトが正常終了しました", total)
    else:
        logger.warning("実行完了（失敗あり）: exit %d", exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

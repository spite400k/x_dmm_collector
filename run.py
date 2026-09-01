#!/usr/bin/env python3
"""tasks.yaml に定義されたスクリプトをフェーズ単位または個別に実行する。"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

from utils.logger import RotatingLogFile, configure_utf8_environment, setup_logger
from utils.run_lock import (
    RunLock,
    RunLockError,
    read_lock_holder,
    wait_until_locks_free,
)

configure_utf8_environment()

ROOT = Path(__file__).resolve().parent
TASKS_FILE = ROOT / "tasks.yaml"
RUN_LOG = "run.log"
RUN_LOCK_PATH = ROOT / "logs" / "run.lock"

# 加工フェーズを系統分割して並列実行するためのフェーズ名
PROCESS_PIPELINE_PHASES = ("process_main", "process_actress", "process_mesugaki")

PHASE_CHOICES = [
    "collect",
    "backfill_tachiyomi",
    "process",
    "process_main",
    "process_actress",
    "process_mesugaki",
    "process_main_weekly",
    "process_mesugaki_weekly",
    "manual",
    "all",
]

# 週次フェーズは日次と同じ系統ロックを使い、同時実行しない
PHASE_LOCK = {
    "process_main": "process_main",
    "process_actress": "process_actress",
    "process_mesugaki": "process_mesugaki",
    "process_main_weekly": "process_main",
    "process_mesugaki_weekly": "process_mesugaki",
}

# --script 実行時にどの系統ロックを取るか
SCRIPT_PIPELINE: dict[str, str] = {
    "scripts/process/update_items.py": "process_main",
    "scripts/process/create_ai_review.py": "process_main",
    "scripts/process/create_weekly_rankings.py": "process_main",
    "scripts/process/create_actress_review.py": "process_actress",
    "scripts/process/create_weekly_rankings_actress.py": "process_actress",
    "scripts/process/update_mesugaki.py": "process_mesugaki",
    "scripts/process/create_ai_review_mesugaki.py": "process_mesugaki",
    "scripts/process/create_weekly_rankings_mesugaki.py": "process_mesugaki",
}

# 収集が延びたあと、加工 3 系統が同時に起きないよう空ける秒数（OpenAI 対策）
PROCESS_STAGGER_AFTER_COLLECT = {
    "process_main": 0,
    "process_actress": 3600,
    "process_mesugaki": 7200,
    "process_main_weekly": 0,
    "process_mesugaki_weekly": 0,
}

DEFAULT_PEER_WAIT_TIMEOUT = 36 * 3600
DEFAULT_PEER_WAIT_POLL = 30.0
PEER_WAIT_LOG_INTERVAL = 600.0
PEER_WAIT_TIMEOUT_ENV = "X_DMM_PEER_WAIT_TIMEOUT"
PEER_WAIT_POLL_ENV = "X_DMM_PEER_WAIT_POLL"
PROCESS_STAGGER_ENV = "X_DMM_PROCESS_STAGGER_SECONDS"

logger = logging.getLogger(__name__)


def pipeline_lock_path(phase: str) -> Path:
    return ROOT / "logs" / f"run_{phase}.lock"


def resolve_lock_paths(phase: str | None, script_path: str | None) -> list[Path]:
    """実行対象に応じたロックファイルパスを返す（複数可）。"""
    if phase in PHASE_LOCK:
        return [pipeline_lock_path(PHASE_LOCK[phase])]
    if phase == "process":
        # 全系統直列実行時は各系統ロックをすべて取得し、分割 bat と衝突させない
        return [pipeline_lock_path(p) for p in PROCESS_PIPELINE_PHASES]
    if phase == "all":
        return [RUN_LOCK_PATH, *[pipeline_lock_path(p) for p in PROCESS_PIPELINE_PHASES]]
    if script_path:
        normalized = script_path.replace("\\", "/")
        pipeline = SCRIPT_PIPELINE.get(normalized)
        if pipeline:
            return [pipeline_lock_path(pipeline)]
        return [RUN_LOCK_PATH]
    return [RUN_LOCK_PATH]


def resolve_peer_wait_paths(phase: str | None, script_path: str | None) -> list[Path]:
    """自分のロック以外で、空くまで待つ相手ジョブのロック。

    収集と加工は Chrome を同時に使わない。加工 3 系統同士は並列のまま。
    同じ系統の二重起動は待たず、既存どおり即失敗する。
    """
    if phase == "all":
        return []
    if phase in PHASE_LOCK or phase == "process":
        return [RUN_LOCK_PATH]
    if phase == "backfill_tachiyomi":
        return [
            RUN_LOCK_PATH,
            *[pipeline_lock_path(p) for p in PROCESS_PIPELINE_PHASES],
        ]
    if script_path:
        normalized = script_path.replace("\\", "/")
        if normalized in SCRIPT_PIPELINE:
            return [RUN_LOCK_PATH]
        if normalized == "scripts/process/backfill_tachiyomi.py":
            return [
                RUN_LOCK_PATH,
                *[pipeline_lock_path(p) for p in PROCESS_PIPELINE_PHASES],
            ]
    return [pipeline_lock_path(p) for p in PROCESS_PIPELINE_PHASES]


def peer_wait_settings() -> tuple[float, float]:
    timeout = float(os.environ.get(PEER_WAIT_TIMEOUT_ENV, str(DEFAULT_PEER_WAIT_TIMEOUT)))
    poll = float(os.environ.get(PEER_WAIT_POLL_ENV, str(DEFAULT_PEER_WAIT_POLL)))
    return timeout, poll


def wait_for_peer_locks(phase: str | None, script_path: str | None) -> bool:
    """相手ジョブが終わるまで待つ。待った場合は True。"""
    paths = resolve_peer_wait_paths(phase, script_path)
    if not paths:
        return False
    timeout, poll = peer_wait_settings()
    last_log = -1.0

    def on_wait(held: list[Path], elapsed: float) -> None:
        nonlocal last_log
        if last_log >= 0 and elapsed - last_log < PEER_WAIT_LOG_INTERVAL:
            return
        last_log = elapsed
        holders = ", ".join(f"{p.name}={read_lock_holder(p)}" for p in held)
        logger.info("相手ジョブの終了を待機中 (%.0fs): %s", elapsed, holders)

    return wait_until_locks_free(
        paths,
        timeout=timeout,
        poll_interval=poll,
        on_wait=on_wait,
    )


def apply_process_stagger(phase: str | None, waited_for_collect: bool) -> None:
    """収集を待ったあと、actress / mesugaki を 1h / 2h ずらす。"""
    if not waited_for_collect or not phase:
        return
    if os.environ.get(PROCESS_STAGGER_ENV) == "0":
        return
    delay = PROCESS_STAGGER_AFTER_COLLECT.get(phase, 0)
    if delay <= 0:
        return
    logger.info("収集終了後の OpenAI 間隔待機: %d 秒 (%s)", delay, phase)
    time.sleep(delay)


class LockSet:
    """複数の RunLock をまとめて取得・解放する。"""

    def __init__(self, paths: list[Path]):
        self._locks = [RunLock(p) for p in paths]
        self._acquired: list[RunLock] = []

    def acquire(self) -> None:
        try:
            for lock in self._locks:
                lock.acquire()
                self._acquired.append(lock)
        except RunLockError:
            self.release()
            raise

    def release(self) -> None:
        while self._acquired:
            self._acquired.pop().release()


def should_echo_child_output(*, echo_output: bool = False) -> bool:
    """GHA 上、または --echo-output 指定時は子プロセス出力をコンソールへも出す。"""
    return echo_output or os.environ.get("GITHUB_ACTIONS") == "true"


def stream_script_output(
    proc: subprocess.Popen[str],
    log_file: RotatingLogFile,
    *,
    echo: bool,
) -> str:
    """子プロセス stdout をログへ書き、必要ならコンソールへも tee する。"""
    chunks: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        chunks.append(line)
        log_file.write(line)
        log_file.flush()
        if echo:
            sys.stdout.write(line)
            sys.stdout.flush()
    return "".join(chunks)


def log_child_output_on_failure(script_path: str, output: str) -> None:
    """失敗時に子プロセス出力を親ロガーへ出す（ファイル専用実行時の調査用）。"""
    body = output.rstrip()
    if not body:
        logger.error("子プロセス出力なし: %s", script_path)
        return
    logger.error(
        "----- 子プロセス出力 (%s) -----\n%s\n----- 出力終了 (%s) -----",
        script_path,
        body,
        script_path,
    )


def load_tasks() -> dict:
    with TASKS_FILE.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_scripts(tasks: dict, phase: str | None, script_path: str | None) -> list[dict]:
    if script_path:
        normalized = script_path.replace("\\", "/")
        # process（全系統）より系統フェーズを優先し、ログ上の phase 名を明確にする
        fallback: dict | None = None
        for phase_name, phase_def in tasks["phases"].items():
            for entry in phase_def.get("scripts", []):
                if entry["path"].replace("\\", "/") != normalized:
                    continue
                matched = {**entry, "phase": phase_name}
                if phase_name == "process":
                    fallback = matched
                    continue
                if phase_name.endswith("_weekly"):
                    continue
                return [matched]
        if fallback is not None:
            return [fallback]
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


def script_cli_args(entry: dict) -> list[str]:
    """tasks.yaml の args を子プロセス引数にする。"""
    raw = entry.get("args") or []
    if isinstance(raw, str):
        return [raw]
    return [str(a) for a in raw]


def run_script(
    entry: dict,
    python_exe: str,
    continue_on_error: bool,
    index: int,
    total: int,
    *,
    echo_output: bool = False,
) -> int:
    script = ROOT / entry["path"]
    extra_args = script_cli_args(entry)
    log_path = ROOT / entry.get("log", f"logs/{script.stem}.log")
    label = entry.get("name") or entry["path"]
    echo = should_echo_child_output(echo_output=echo_output)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    arg_note = f" {' '.join(extra_args)}" if extra_args else ""
    header = f"{'=' * 48}\n{timestamp} - タスク開始 ({entry['path']}{arg_note})\n"

    logger.info(
        "[%d/%d] スクリプト実行開始: %s (%s) → %s",
        index,
        total,
        label,
        entry["path"],
        log_path,
    )
    child_output = ""
    with RotatingLogFile(log_path) as log_file:
        log_file.write(header)
        log_file.flush()

        proc = subprocess.Popen(
            [python_exe, str(script), *extra_args],
            cwd=ROOT,
            env={
                **os.environ,
                "PYTHONPATH": str(ROOT),
                # 子プロセスの標準出力を UTF-8 に統一し、ログの文字化けを防ぐ。
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        child_output = stream_script_output(proc, log_file, echo=echo)
        returncode = proc.wait()

        footer = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - タスク終了 ({entry['path']})\n{'=' * 48}\n"
        log_file.write(footer)

    if returncode != 0:
        logger.error(
            "[%d/%d] スクリプト失敗: %s (exit %d)",
            index,
            total,
            entry["path"],
            returncode,
        )
        # ライブ tee 済みでも、失敗箇所が探しやすいよう明示ブロックを出す
        log_child_output_on_failure(entry["path"], child_output)
        if not continue_on_error:
            return returncode
    else:
        logger.info("[%d/%d] スクリプト完了: %s", index, total, entry["path"])
    return returncode


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
        choices=PHASE_CHOICES,
        help="実行するフェーズ（all = collect + process。並列用: process_main / process_actress / process_mesugaki。週次: process_main_weekly / process_mesugaki_weekly。立ち読み後埋め: backfill_tachiyomi）",
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
    parser.add_argument(
        "--echo-output",
        action="store_true",
        help="子プロセスの標準出力をコンソールにも出す（GITHUB_ACTIONS 時は自動有効）",
    )
    parser.add_argument(
        "--no-lock",
        action="store_true",
        help="多重起動防止ロックを取得しない（相手ジョブ待ちもスキップ。緊急時のみ）",
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

    lock_set: LockSet | None = None
    if not args.no_lock:
        try:
            waited = wait_for_peer_locks(args.phase, args.script)
            apply_process_stagger(args.phase, waited)
        except RunLockError as exc:
            logger.error("%s", exc)
            sys.exit(2)
        lock_set = LockSet(resolve_lock_paths(args.phase, args.script))
        try:
            lock_set.acquire()
        except RunLockError as exc:
            logger.error("%s", exc)
            sys.exit(2)

    try:
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

            code = run_script(
                entry,
                args.python,
                args.continue_on_error,
                i,
                total,
                echo_output=args.echo_output,
            )
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
    finally:
        if lock_set is not None:
            lock_set.release()


if __name__ == "__main__":
    main()

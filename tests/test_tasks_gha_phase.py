"""tasks.yaml の gha フェーズ分離（bat 除外）を検証する。"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TASKS_FILE = ROOT / "tasks.yaml"

GHA_SCRIPTS = {
    "scripts/process/create_weekly_rankings.py",
    "scripts/process/create_weekly_rankings_mesugaki.py",
    "scripts/process/create_weekly_rankings_actress.py",
    "scripts/process/create_actress_review.py",
}


def _load_tasks() -> dict:
    with TASKS_FILE.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _paths(phase: str) -> set[str]:
    tasks = _load_tasks()
    return {e["path"] for e in tasks["phases"][phase].get("scripts", [])}


class TestGhaPhaseSeparation:
    def test_gha_phase_contains_four_scripts(self):
        assert _paths("gha") == GHA_SCRIPTS

    def test_process_phase_excludes_gha_scripts(self):
        process_paths = _paths("process")
        assert process_paths.isdisjoint(GHA_SCRIPTS)

    def test_manual_phase_excludes_actress_review(self):
        assert "scripts/process/create_actress_review.py" not in _paths("manual")

    def test_all_phase_via_run_resolve_excludes_gha(self):
        """run.py の all = collect + process のみ（gha を含まない）。"""
        from run import load_tasks, resolve_scripts

        entries = resolve_scripts(load_tasks(), "all", None)
        paths = {e["path"] for e in entries}
        assert paths.isdisjoint(GHA_SCRIPTS)

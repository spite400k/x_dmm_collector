"""ChromeDriver パス解決（webdriver-manager の不正パスを補正）。"""

from __future__ import annotations

from pathlib import Path

from webdriver_manager.chrome import ChromeDriverManager

_CACHED: str | None = None


def chromedriver_path() -> str:
    """有効な chromedriver 実行ファイルパスを返す。

    webdriver-manager が存在しないネストパス
    （例: .../chromedriver-win32/chromedriver.exe）を返すことがあるため、
    実ファイルを親ディレクトリ側から探す。
    """
    global _CACHED
    if _CACHED is not None and Path(_CACHED).is_file():
        return _CACHED

    resolved = resolve_chromedriver_path(ChromeDriverManager().install())
    _CACHED = resolved
    return resolved


def resolve_chromedriver_path(raw: str) -> str:
    """install() が返したパスから実在する chromedriver を解決する。"""
    path = Path(raw)
    if _is_chromedriver_binary(path):
        return str(path.resolve())

    # VERSION/ とその直下サブディレクトリまで（例: chromedriver-win32/）
    search_roots = [path.parent, path.parent.parent]
    candidates: list[Path] = []
    for root in search_roots:
        if not root.is_dir():
            continue
        candidates.extend(root.glob("chromedriver.exe"))
        candidates.extend(root.glob("chromedriver"))
        candidates.extend(root.glob("*/chromedriver.exe"))
        candidates.extend(root.glob("*/chromedriver"))

    for candidate in candidates:
        if _is_chromedriver_binary(candidate):
            return str(candidate.resolve())

    raise FileNotFoundError(f"chromedriver executable not found near {raw!r}")


def _is_chromedriver_binary(path: Path) -> bool:
    if not path.is_file():
        return False
    return path.name.lower() in ("chromedriver", "chromedriver.exe")


def clear_chromedriver_cache() -> None:
    """テスト用: キャッシュをクリアする。"""
    global _CACHED
    _CACHED = None

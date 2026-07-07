"""Загрузка и слияние конфигурации: .analyzerrc (TOML или JSON) + аргументы CLI."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    import tomllib as toml_reader  # Python 3.11+
    _TOML_MODE = "binary"
except ImportError:  # pragma: no cover
    try:
        import tomli as toml_reader  # type: ignore
        _TOML_MODE = "binary"
    except ImportError:
        toml_reader = None
        _TOML_MODE = None


@dataclass
class AnalyzerConfig:
    project_root: str
    includes: List[str] = field(default_factory=list)
    defines: List[str] = field(default_factory=list)
    source_dirs: List[str] = field(default_factory=list)
    exclude_globs: List[str] = field(default_factory=list)
    outdir: str = "Debug"
    verbose: bool = False
    jobs: int = 0  # 0 => auto (os.cpu_count())
    fail_on_severity: str = "error"     # порог для exit code
    fail_on_count: int = 0              # >0: фейлить если найдено больше N замечаний
    formats: List[str] = field(default_factory=lambda: ["console"])
    custom_rules_path: Optional[str] = None
    enable_secret_scan: bool = True
    enable_clang_format: bool = False
    use_cache: bool = True
    cache_path: str = ".analyzer_cache.json"

    def jobs_or_auto(self) -> int:
        return self.jobs if self.jobs > 0 else max(1, (os.cpu_count() or 2) - 1)


def _read_rc_file(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    if path.endswith(".json"):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    # По умолчанию считаем TOML
    if toml_reader is None:
        raise RuntimeError(
            f"Найден {path}, но не установлен парсер TOML. "
            f"Установите 'tomli' (Python < 3.11) или используйте .analyzerrc.json"
        )
    with open(path, "rb") as fh:
        return toml_reader.load(fh)


def load_config(project_root: str, rc_path: Optional[str], cli_overrides: Dict[str, Any]) -> AnalyzerConfig:
    """Порядок приоритета: значения по умолчанию < .analyzerrc < явные аргументы CLI."""
    candidates = []
    if rc_path:
        candidates.append(rc_path)
    else:
        candidates += [
            os.path.join(project_root, ".analyzerrc"),
            os.path.join(project_root, ".analyzerrc.toml"),
            os.path.join(project_root, ".analyzerrc.json"),
        ]

    rc_data: Dict[str, Any] = {}
    for candidate in candidates:
        if os.path.exists(candidate):
            rc_data = _read_rc_file(candidate)
            break

    cfg = AnalyzerConfig(project_root=project_root)

    # Применяем значения из .analyzerrc
    for k, v in rc_data.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)

    # Явные аргументы CLI имеют наивысший приоритет (только не-None/не-пустые)
    for k, v in cli_overrides.items():
        if v is None:
            continue
        if isinstance(v, (list, tuple)) and len(v) == 0:
            continue
        setattr(cfg, k, v)

    return cfg

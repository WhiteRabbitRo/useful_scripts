"""FileWalker — обход исходников и учёт кэша (по хешу содержимого файла)."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from typing import Dict, List, Tuple


class FileWalker:
    def __init__(self, source_dirs: List[str], exclude_globs: List[str] | None = None):
        self.source_dirs = source_dirs
        self.exclude_globs = exclude_globs or []

    def collect(self, extensions: Tuple[str, ...] = (".c", ".h")) -> List[str]:
        files: List[str] = []
        for src in self.source_dirs:
            if not os.path.isdir(src):
                continue
            for root, _dirs, filenames in os.walk(src):
                for fn in filenames:
                    if not fn.endswith(extensions):
                        continue
                    full = os.path.join(root, fn)
                    if self._is_excluded(full):
                        continue
                    files.append(full)
        return sorted(set(files))

    def _is_excluded(self, path: str) -> bool:
        return any(fnmatch.fnmatch(path, pattern) for pattern in self.exclude_globs)

    @staticmethod
    def file_hash(path: str) -> str:
        h = hashlib.sha256()
        try:
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    h.update(chunk)
        except OSError:
            return ""
        return h.hexdigest()


class ResultCache:
    """Простой персистентный кэш: file_hash -> {tool: [findings-as-dict]}.

    Заменяет собой "кэширование AST": поскольку внешние анализаторы
    (cppcheck/clang/gcc) не отдают нам разбираемое AST напрямую, мы кэшируем
    по неизменности содержимого файла (SHA-256) — если файл не менялся,
    повторный запуск анализатора на нём пропускается.
    """

    def __init__(self, cache_path: str):
        self.cache_path = cache_path
        self._data: Dict[str, Dict[str, list]] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as fh:
                    self._data = json.load(fh)
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def save(self) -> None:
        try:
            with open(self.cache_path, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh)
        except OSError:
            pass

    def get(self, file_hash: str, tool: str):
        entry = self._data.get(file_hash)
        if entry is None:
            return None
        return entry.get(tool)

    def put(self, file_hash: str, tool: str, findings_as_dicts: list) -> None:
        self._data.setdefault(file_hash, {})[tool] = findings_as_dicts

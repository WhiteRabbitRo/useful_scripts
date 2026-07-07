"""Общие модели данных: находки (Finding) и уровни критичности (Severity)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


class Severity(IntEnum):
    """Уровни критичности, отсортированы по возрастанию важности."""

    INFO = 0
    STYLE = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4

    @classmethod
    def from_string(cls, value: str) -> "Severity":
        mapping = {
            "info": cls.INFO,
            "note": cls.INFO,
            "style": cls.STYLE,
            "warning": cls.WARNING,
            "warn": cls.WARNING,
            "error": cls.ERROR,
            "critical": cls.CRITICAL,
            "security": cls.CRITICAL,
        }
        return mapping.get(value.lower().strip(), cls.WARNING)

    def sarif_level(self) -> str:
        return {
            Severity.INFO: "note",
            Severity.STYLE: "note",
            Severity.WARNING: "warning",
            Severity.ERROR: "error",
            Severity.CRITICAL: "error",
        }[self]

    def color_code(self) -> str:
        # Коды ANSI, используются только если colorama недоступна.
        return {
            Severity.INFO: "\033[0;36m",
            Severity.STYLE: "\033[0;37m",
            Severity.WARNING: "\033[0;33m",
            Severity.ERROR: "\033[0;31m",
            Severity.CRITICAL: "\033[1;31m",
        }[self]


@dataclass
class Finding:
    """Единичное замечание статического анализа, независимое от инструмента."""

    tool: str                 # cppcheck | clang | gcc-analyzer | secret-scanner | custom:<rule_id>
    rule_id: str              # идентификатор правила/чек-код
    message: str
    file: str
    line: int = 0
    column: int = 0
    severity: Severity = Severity.WARNING
    cwe: Optional[str] = None
    snippet: Optional[str] = None
    fingerprint: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if not self.fingerprint:
            key = f"{self.tool}:{self.rule_id}:{self.file}:{self.line}:{self.message}"
            self.fingerprint = hashlib.sha1(key.encode("utf-8", "ignore")).hexdigest()

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "rule_id": self.rule_id,
            "message": self.message,
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "severity": self.severity.name,
            "cwe": self.cwe,
            "snippet": self.snippet,
            "fingerprint": self.fingerprint,
        }

    def to_sarif_result(self) -> dict:
        return {
            "ruleId": f"{self.tool}:{self.rule_id}",
            "level": self.severity.sarif_level(),
            "message": {"text": self.message},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": self.file},
                        "region": {
                            "startLine": max(self.line, 1),
                            "startColumn": max(self.column, 1),
                        },
                    }
                }
            ],
            "partialFingerprints": {"primaryFingerprint": self.fingerprint},
        }

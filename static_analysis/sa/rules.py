"""RuleLoader: встроенные правила поиска опасных паттернов (OWASP-подобные для C)
+ кастомные правила из JSON/TOML + детектор секретов/ключей.

Все правила контекстно-зависимы: срабатывания внутри комментариев или
строковых литералов (для правил опасных функций) отбрасываются через CodeMap.
Для детектора секретов, наоборот, строки не исключаются — секреты почти
всегда лежат именно в строковых литералах.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import List, Optional

from .code_context import CodeMap
from .models import Finding, Severity
from .strategies import AnalysisContext, AnalyzerStrategy

try:
    import tomllib as toml_reader
except ImportError:  # pragma: no cover
    try:
        import tomli as toml_reader  # type: ignore
    except ImportError:
        toml_reader = None


@dataclass
class Rule:
    id: str
    pattern: str
    message: str
    severity: str = "warning"
    cwe: Optional[str] = None
    context_sensitive: bool = True  # исключать комментарии/строки?

    def compiled(self) -> re.Pattern:
        return re.compile(self.pattern)


# Встроенные правила: классические уязвимые C-функции (эквивалент части OWASP Top 10 /
# CWE Top 25 для C: буферные переполнения, форматные строки, гонки TOCTOU и т.д.)
BUILTIN_RULES: List[Rule] = [
    Rule("dangerous-strcpy", r"\bstrcpy\s*\(", "Использование strcpy() без проверки границ буфера — риск переполнения (CWE-120)", "error", "CWE-120"),
    Rule("dangerous-strcat", r"\bstrcat\s*\(", "Использование strcat() без проверки границ буфера — риск переполнения (CWE-120)", "error", "CWE-120"),
    Rule("dangerous-gets", r"\bgets\s*\(", "Использование gets() — функция принципиально небезопасна и удалена из C11 (CWE-242)", "critical", "CWE-242"),
    Rule("dangerous-sprintf", r"\bsprintf\s*\(", "Использование sprintf() без ограничения длины — используйте snprintf (CWE-120)", "warning", "CWE-120"),
    Rule("format-string", r"printf\s*\(\s*[a-zA-Z_][\w]*\s*\)", "Возможная уязвимость форматной строки: переменная как единственный аргумент printf (CWE-134)", "error", "CWE-134"),
    Rule("weak-rand", r"\brand\s*\(\s*\)", "rand() не криптостоек — не использовать для генерации ключей/токенов (CWE-338)", "warning", "CWE-338"),
    Rule("system-call", r"\bsystem\s*\(", "Вызов system() — риск command injection при участии внешних данных (CWE-78)", "error", "CWE-78"),
    Rule("weak-md5", r"\bMD5(_Init|_Update|_Final)?\s*\(", "Использование MD5 — криптографически слабый алгоритм (CWE-327)", "warning", "CWE-327"),
    Rule("hardcoded-tmp", r"/tmp/[\w.\-]+", "Жёстко заданный путь во временной директории — риск небезопасного использования /tmp (CWE-377)", "info", "CWE-377"),
]


class RuleLoader:
    """Загружает встроенные и кастомные правила из JSON/TOML."""

    def __init__(self, custom_rules_path: Optional[str] = None):
        self.rules: List[Rule] = list(BUILTIN_RULES)
        if custom_rules_path:
            self.rules.extend(self._load_custom(custom_rules_path))

    @staticmethod
    def _load_custom(path: str) -> List[Rule]:
        if not os.path.exists(path):
            return []
        if path.endswith(".json"):
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            if toml_reader is None:
                raise RuntimeError("Для чтения TOML-правил установите пакет 'tomli' (Python < 3.11)")
            with open(path, "rb") as fh:
                data = toml_reader.load(fh)

        rules = []
        for item in data.get("rules", []):
            rules.append(
                Rule(
                    id=item["id"],
                    pattern=item["pattern"],
                    message=item.get("message", item["id"]),
                    severity=item.get("severity", "warning"),
                    cwe=item.get("cwe"),
                    context_sensitive=item.get("context_sensitive", True),
                )
            )
        return rules


class CustomRuleStrategy(AnalyzerStrategy):
    """Стратегия, применяющая правила RuleLoader (встроенные + кастомные) построчно/по regex,
    с контекстным исключением комментариев и строк."""

    name = "custom-rules"

    def __init__(self, loader: RuleLoader):
        self.loader = loader

    def is_available(self) -> bool:
        return True  # чистый Python, внешних зависимостей нет

    def run(self, files: List[str], ctx: AnalysisContext) -> List[Finding]:
        findings: List[Finding] = []
        compiled_rules = [(r, r.compiled()) for r in self.loader.rules]
        for file in files:
            try:
                with open(file, "r", encoding="utf-8", errors="ignore") as fh:
                    text = fh.read()
            except OSError:
                continue

            code_map: Optional[CodeMap] = None
            for rule, regex in compiled_rules:
                if rule.context_sensitive and code_map is None:
                    code_map = CodeMap(text)
                for m in regex.finditer(text):
                    if rule.context_sensitive and code_map is not None:
                        if not code_map.is_real_code(m.start(), m.end()):
                            continue  # срабатывание в комментарии/строке — игнорируем
                        line = code_map.line_at(m.start())
                    else:
                        line = text.count("\n", 0, m.start()) + 1
                    findings.append(
                        Finding(
                            tool="custom-rules",
                            rule_id=rule.id,
                            message=rule.message,
                            file=file,
                            line=line,
                            severity=Severity.from_string(rule.severity),
                            cwe=rule.cwe,
                        )
                    )
        return findings


# --- Детектор секретов/ключей -------------------------------------------------

_SECRET_PATTERNS = [
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private-key-block", re.compile(r"-----BEGIN (RSA|EC|OPENSSH|DSA|PGP) PRIVATE KEY-----")),
    # Покрывает как `key = "..."` / `key: "..."`, так и C-специфичное `#define KEY "..."`
    ("generic-api-key", re.compile(
        r"(?i)(?:#define\s+)?\w*(api[_-]?key|secret|token)\w*\s*(?:[=:]\s*)?[\"'][A-Za-z0-9_\-/+]{16,}[\"']"
    )),
    ("hardcoded-password", re.compile(r"(?i)(?:#define\s+)?\w*password\w*\s*(?:[=:]\s*)?[\"'][^\"']{4,}[\"']")),
    ("slack-token", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}")),
    ("stripe-key", re.compile(r"sk_(live|test)_[A-Za-z0-9]{16,}")),
    ("google-api-key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
]


class SecretScannerStrategy(AnalyzerStrategy):
    """Ищет захардкоженные секреты/ключи. Умышленно НЕ исключает строковые
    литералы: подавляющее большинство утечек секретов находится именно там."""

    name = "secret-scanner"

    def is_available(self) -> bool:
        return True

    def run(self, files: List[str], ctx: AnalysisContext) -> List[Finding]:
        findings: List[Finding] = []
        for file in files:
            try:
                with open(file, "r", encoding="utf-8", errors="ignore") as fh:
                    lines = fh.readlines()
            except OSError:
                continue
            for lineno, line in enumerate(lines, start=1):
                for rule_id, regex in _SECRET_PATTERNS:
                    if regex.search(line):
                        findings.append(
                            Finding(
                                tool=self.name,
                                rule_id=rule_id,
                                message=f"Обнаружен потенциальный секрет ({rule_id}) в исходном коде",
                                file=file,
                                line=lineno,
                                severity=Severity.CRITICAL,
                                cwe="CWE-798",
                            )
                        )
        return findings

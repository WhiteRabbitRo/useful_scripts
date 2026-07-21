"""Паттерн "Стратегия" для разных анализаторов.

Каждая стратегия принимает список файлов + общий контекст (includes/defines)
и возвращает список Finding. Это позволяет добавлять новые анализаторы
(например, PVS-Studio, semgrep, PEP8/ESLint для других языков проекта)
без изменения AnalyzerEngine — достаточно реализовать AnalyzerStrategy.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

from .models import Finding, Severity


@dataclass
class AnalysisContext:
    includes: List[str]     # уже в форме -Ipath
    defines: List[str]      # уже в форме -DNAME=VAL или NAME=VAL
    project_root: str
    verbose: bool = False
    cppcheck_platform: str = "unix64"


class AnalyzerStrategy(ABC):
    """Абстрактный базовый класс для всех статических анализаторов."""

    name: str = "base"

    @abstractmethod
    def is_available(self) -> bool:
        """Проверка, что нужный бинарник установлен."""

    @abstractmethod
    def run(self, files: List[str], ctx: AnalysisContext) -> List[Finding]:
        """Запустить анализ над списком файлов и вернуть находки."""

    def run_single(self, file: str, ctx: AnalysisContext) -> List[Finding]:
        """По умолчанию — запуск на одном файле через run([file]).

        Нужен отдельно, т.к. AnalyzerEngine распараллеливает работу
        по отдельным файлам, а не по инструментам целиком.
        """
        return self.run([file], ctx)


_CPPCHECK_LINE_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<sev>\w+):\s*(?P<msg>.*?)\s*\[(?P<id>[\w-]+)\]\s*$"
)


class CppcheckStrategy(AnalyzerStrategy):
    name = "cppcheck"

    def is_available(self) -> bool:
        return shutil.which("cppcheck") is not None

    def run(self, files: List[str], ctx: AnalysisContext) -> List[Finding]:
        if not files:
            return []
        cmd = [
            "cppcheck",
            "--enable=all",
            f"--platform={ctx.cppcheck_platform}",
            "--force",
            "--inline-suppr",
            "--template={file}:{line}:{column}: {severity}: {message} [{id}]",
            *ctx.includes,
            *files,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ctx.project_root)
        findings: List[Finding] = []
        for line in proc.stderr.splitlines():
            m = _CPPCHECK_LINE_RE.match(line.strip())
            if not m:
                continue
            findings.append(
                Finding(
                    tool=self.name,
                    rule_id=m.group("id"),
                    message=m.group("msg"),
                    file=m.group("file"),
                    line=int(m.group("line")),
                    column=int(m.group("col")),
                    severity=Severity.from_string(m.group("sev")),
                )
            )
        return findings


_CLANG_LINE_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<sev>warning|error):\s*(?P<msg>.*?)(?:\s*\[(?P<id>[\w.\-]+)\])?$"
)


class ClangAnalyzeStrategy(AnalyzerStrategy):
    name = "clang"

    def is_available(self) -> bool:
        return shutil.which("clang") is not None

    def run(self, files: List[str], ctx: AnalysisContext) -> List[Finding]:
        if not files:
            return []
        findings: List[Finding] = []
        for file in files:
            cmd = [
                "clang", "--analyze", "-Xanalyzer", "-analyzer-output=text",
                *ctx.includes, *ctx.defines, file,
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ctx.project_root)
            for line in proc.stderr.splitlines():
                m = _CLANG_LINE_RE.match(line.strip())
                if not m:
                    continue
                findings.append(
                    Finding(
                        tool=self.name,
                        rule_id=m.group("id") or "clang-analyzer",
                        message=m.group("msg"),
                        file=m.group("file"),
                        line=int(m.group("line")),
                        column=int(m.group("col")),
                        severity=Severity.from_string(m.group("sev")),
                    )
                )
        return findings


class GccAnalyzerStrategy(AnalyzerStrategy):
    name = "gcc-analyzer"

    def is_available(self) -> bool:
        return shutil.which("gcc") is not None

    def run(self, files: List[str], ctx: AnalysisContext) -> List[Finding]:
        if not files:
            return []
        findings: List[Finding] = []
        for file in files:
            cmd = [
                "gcc", "-Wall", "-Wextra", "-fanalyzer", "-fanalyzer-verbosity=3",
                "-fsyntax-only", *ctx.defines, *ctx.includes, file,
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ctx.project_root)
            for line in proc.stderr.splitlines():
                m = _CLANG_LINE_RE.match(line.strip())
                if not m:
                    continue
                findings.append(
                    Finding(
                        tool=self.name,
                        rule_id=m.group("id") or "gcc-analyzer",
                        message=m.group("msg"),
                        file=m.group("file"),
                        line=int(m.group("line")),
                        column=int(m.group("col")),
                        severity=Severity.from_string(m.group("sev")),
                    )
                )
        return findings


class ClangFormatStyleStrategy(AnalyzerStrategy):
    """Функциональный эквивалент PEP8/ESLint для C: проверка форматирования.

    Отчёт носит информативный характер (severity=STYLE), не является
    результатом статического анализа безопасности.
    """

    name = "clang-format"

    def is_available(self) -> bool:
        return shutil.which("clang-format") is not None

    def run(self, files: List[str], ctx: AnalysisContext) -> List[Finding]:
        findings: List[Finding] = []
        for file in files:
            cmd = ["clang-format", "--dry-run", "--Werror", file]
            proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ctx.project_root)
            if proc.returncode != 0:
                findings.append(
                    Finding(
                        tool=self.name,
                        rule_id="format-mismatch",
                        message="Файл не соответствует принятому стилю форматирования (.clang-format)",
                        file=file,
                        line=0,
                        severity=Severity.STYLE,
                    )
                )
        return findings

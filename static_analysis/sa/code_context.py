"""Лёгкая токенизация C-файла для контекстного анализа.

Это НЕ полноценный препроцессор/AST, а быстрый посимвольный сканер,
который для каждой позиции в файле помечает, находится ли она внутри
комментария, строкового литерала или обычного кода. Используется
кастомными regex-правилами (rules.py), чтобы не создавать ложных
срабатываний по коду, "закомментированному" или находящемуся в
строках-примерах (например, sprintf(buf, "gets(x); // not real")).
"""

from __future__ import annotations

from enum import Enum, auto
from typing import List


class SpanKind(Enum):
    CODE = auto()
    COMMENT = auto()
    STRING = auto()


class CodeMap:
    """Хранит для каждого символа исходного текста его тип (SpanKind) и номер строки."""

    def __init__(self, text: str):
        self.text = text
        self.kinds: List[SpanKind] = [SpanKind.CODE] * len(text)
        self.lines: List[int] = [0] * len(text)
        self._build()

    def _build(self) -> None:
        text = self.text
        n = len(text)
        i = 0
        line = 1
        kinds = self.kinds
        lines = self.lines

        while i < n:
            ch = text[i]
            lines[i] = line
            if ch == "\n":
                line += 1
                i += 1
                continue

            # Однострочный комментарий //
            if ch == "/" and i + 1 < n and text[i + 1] == "/":
                start = i
                while i < n and text[i] != "\n":
                    lines[i] = line
                    kinds[i] = SpanKind.COMMENT
                    i += 1
                continue

            # Многострочный комментарий /* ... */
            if ch == "/" and i + 1 < n and text[i + 1] == "*":
                start = i
                kinds[i] = SpanKind.COMMENT
                i += 1
                while i < n:
                    lines[i] = line
                    kinds[i] = SpanKind.COMMENT
                    if text[i] == "\n":
                        line += 1
                    if text[i] == "*" and i + 1 < n and text[i + 1] == "/":
                        i += 1
                        lines[i] = line
                        kinds[i] = SpanKind.COMMENT
                        i += 1
                        break
                    i += 1
                continue

            # Строковый литерал "..."
            if ch == '"':
                kinds[i] = SpanKind.STRING
                i += 1
                while i < n and text[i] != '"':
                    lines[i] = line
                    kinds[i] = SpanKind.STRING
                    if text[i] == "\\" and i + 1 < n:
                        i += 1
                        lines[i] = line
                        kinds[i] = SpanKind.STRING
                    if text[i] == "\n":
                        line += 1
                    i += 1
                if i < n:
                    kinds[i] = SpanKind.STRING
                    lines[i] = line
                    i += 1
                continue

            # Символьный литерал 'x'
            if ch == "'":
                kinds[i] = SpanKind.STRING
                i += 1
                while i < n and text[i] != "'":
                    lines[i] = line
                    kinds[i] = SpanKind.STRING
                    if text[i] == "\\" and i + 1 < n:
                        i += 1
                        lines[i] = line
                        kinds[i] = SpanKind.STRING
                    i += 1
                if i < n:
                    kinds[i] = SpanKind.STRING
                    lines[i] = line
                    i += 1
                continue

            kinds[i] = SpanKind.CODE
            i += 1

        self.kinds = kinds
        self.lines = lines

    def kind_at(self, pos: int) -> SpanKind:
        if 0 <= pos < len(self.kinds):
            return self.kinds[pos]
        return SpanKind.CODE

    def line_at(self, pos: int) -> int:
        if 0 <= pos < len(self.lines):
            return self.lines[pos]
        return 0

    def is_real_code(self, start: int, end: int) -> bool:
        """True, если хотя бы один символ диапазона [start, end) — обычный код
        (не комментарий и не строка). Используется для правил, ищущих реальные
        вызовы опасных функций, а не их упоминания в комментариях/строках."""
        for i in range(start, min(end, len(self.kinds))):
            if self.kinds[i] == SpanKind.CODE:
                return True
        return False

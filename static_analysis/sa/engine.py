"""AnalyzerEngine — центральный оркестратор.

Параллелизм: используем concurrent.futures.ProcessPoolExecutor вместо
asyncio, потому что сама нагрузка — это блокирующие вызовы subprocess
(cppcheck/clang/gcc), а не I/O-bound задачи, для которых был бы уместен
asyncio. ProcessPoolExecutor также даёт реальный параллелизм, не упираясь
в GIL, в отличие от threading.
"""

from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List

from .config import AnalyzerConfig
from .models import Finding, Severity
from .rules import CustomRuleStrategy, RuleLoader, SecretScannerStrategy
from .strategies import (
    AnalysisContext,
    AnalyzerStrategy,
    ClangAnalyzeStrategy,
    ClangFormatStyleStrategy,
    CppcheckStrategy,
    GccAnalyzerStrategy,
)
from .walker import FileWalker, ResultCache


def _run_strategy_on_file(strategy: AnalyzerStrategy, file: str, ctx: AnalysisContext) -> List[dict]:
    """Функция верхнего уровня (нужна для сериализации в multiprocessing)."""
    findings = strategy.run_single(file, ctx)
    return [f.to_dict() for f in findings]


def _dict_to_finding(d: dict) -> Finding:
    return Finding(
        tool=d["tool"], rule_id=d["rule_id"], message=d["message"], file=d["file"],
        line=d["line"], column=d.get("column", 0), severity=Severity[d["severity"]],
        cwe=d.get("cwe"), snippet=d.get("snippet"), fingerprint=d.get("fingerprint", ""),
    )


class AnalyzerEngine:
    def __init__(self, config: AnalyzerConfig):
        self.config = config
        self.walker = FileWalker(config.source_dirs, config.exclude_globs)
        self.cache = ResultCache(config.cache_path) if config.use_cache else None
        self.rule_loader = RuleLoader(config.custom_rules_path)

        self.strategies: List[AnalyzerStrategy] = [
            CppcheckStrategy(),
            ClangAnalyzeStrategy(),
            GccAnalyzerStrategy(),
            CustomRuleStrategy(self.rule_loader),
        ]
        if config.enable_secret_scan:
            self.strategies.append(SecretScannerStrategy())
        if config.enable_clang_format:
            self.strategies.append(ClangFormatStyleStrategy())

        # Оставляем только доступные в системе инструменты, с предупреждением
        self._unavailable: List[str] = []
        available = []
        for s in self.strategies:
            if s.is_available():
                available.append(s)
            else:
                self._unavailable.append(s.name)
        self.strategies = available

    def run(self) -> tuple[List[Finding], Dict[str, float]]:
        files = self.walker.collect()
        ctx = AnalysisContext(
            includes=[f"-I{inc}" for inc in self.config.includes] if not self._already_prefixed() else self.config.includes,
            defines=self.config.defines,
            project_root=self.config.project_root,
            verbose=self.config.verbose,
            cppcheck_platform=self.config.cppcheck_platform,
        )

        all_findings: List[Finding] = []
        timings: Dict[str, float] = {}

        # Стратегии, которые естественно работают "по файлу" (тяжёлые внешние тулы) —
        # распараллеливаем по парам (strategy, file). Остальные (custom-rules,
        # secret-scanner) — дёшевы, гоняем их последовательно за всё дерево сразу.
        per_file_strategies = [s for s in self.strategies if s.name in ("cppcheck", "clang", "gcc-analyzer", "clang-format")]
        whole_tree_strategies = [s for s in self.strategies if s not in per_file_strategies]

        jobs = self.config.jobs_or_auto()
        t0 = time.time()

        # cppcheck умеет сам принимать список файлов и работать эффективнее одним
        # вызовом (внутренний кэш include-графа), поэтому его гоняем отдельно,
        # одним вызовом на всё дерево, а не по файлам.
        for strategy in per_file_strategies:
            s_t0 = time.time()
            if strategy.name == "cppcheck":
                all_findings.extend(strategy.run(files, ctx))
            else:
                all_findings.extend(self._run_parallel(strategy, files, ctx, jobs))
            timings[strategy.name] = time.time() - s_t0

        for strategy in whole_tree_strategies:
            s_t0 = time.time()
            all_findings.extend(strategy.run(files, ctx))
            timings[strategy.name] = time.time() - s_t0

        timings["_total"] = time.time() - t0
        return self._dedupe(all_findings), timings

    def _already_prefixed(self) -> bool:
        return all(inc.startswith("-I") for inc in self.config.includes) if self.config.includes else False

    def _run_parallel(self, strategy: AnalyzerStrategy, files: List[str], ctx: AnalysisContext, jobs: int) -> List[Finding]:
        results: List[Finding] = []
        files_to_run = []
        cached_results: List[Finding] = []

        for file in files:
            if self.cache is not None:
                fh = FileWalker.file_hash(file)
                cached = self.cache.get(fh, strategy.name)
                if cached is not None:
                    cached_results.extend(_dict_to_finding(d) for d in cached)
                    continue
                files_to_run.append((file, fh))
            else:
                files_to_run.append((file, None))

        if not files_to_run:
            return cached_results

        if jobs <= 1 or len(files_to_run) == 1:
            for file, fh in files_to_run:
                findings = strategy.run_single(file, ctx)
                results.extend(findings)
                if self.cache is not None and fh:
                    self.cache.put(fh, strategy.name, [f.to_dict() for f in findings])
            self._flush_cache()
            return cached_results + results

        with ProcessPoolExecutor(max_workers=jobs) as pool:
            future_map = {
                pool.submit(_run_strategy_on_file, strategy, file, ctx): (file, fh)
                for file, fh in files_to_run
            }
            for future in as_completed(future_map):
                file, fh = future_map[future]
                try:
                    dicts = future.result()
                except Exception as exc:  # noqa: BLE001 — изолируем сбой одного файла
                    dicts = [{
                        "tool": strategy.name, "rule_id": "internal-error",
                        "message": f"Ошибка анализа файла: {exc}", "file": file,
                        "line": 0, "column": 0, "severity": "WARNING",
                        "cwe": None, "snippet": None, "fingerprint": "",
                    }]
                if self.cache is not None and fh:
                    self.cache.put(fh, strategy.name, dicts)
                results.extend(_dict_to_finding(d) for d in dicts)

        self._flush_cache()
        return cached_results + results

    def _flush_cache(self) -> None:
        if self.cache is not None:
            self.cache.save()

    @staticmethod
    def _dedupe(findings: List[Finding]) -> List[Finding]:
        seen = set()
        unique = []
        for f in findings:
            if f.fingerprint in seen:
                continue
            seen.add(f.fingerprint)
            unique.append(f)
        return unique

    @property
    def unavailable_tools(self) -> List[str]:
        return self._unavailable

#!/usr/bin/env python3
"""static_analysis.py — оркестратор статического анализа C-кода.

Замена Bash-скрипта static_analysis.sh: та же идея (обёртка над cppcheck,
clang --analyze, gcc -fanalyzer), плюс: параллельное выполнение, кэш
результатов по хешу файла, кастомные правила, детектор секретов, вывод
в JSON/HTML/SARIF, конфиг .analyzerrc и exit-code порог для CI/CD.

Пример запуска (соответствует вашему прежнему вызову):

    ./static_analysis.py \\
        -i submodules/dtls/libatd/include \\
        -i submodules/dtls/libatd/src \\
        -i submodules/dtls/submodules/libacm/include \\
        -i submodules/dtls/submodules/uthash/src \\
        -d ATD_DEBUG=1 -d ATD_TLS12_SUPPORT=1 -d ATD_DTLS12_SUPPORT=1 \\
        -s submodules/dtls/libatd/src \\
        --format console --format json --format html --format sarif \\
        --fail-on error
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sa.config import load_config  # noqa: E402
from sa.engine import AnalyzerEngine  # noqa: E402
from sa.models import Severity  # noqa: E402
from sa.report import ReportGenerator  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="static_analysis.py",
        description="Статический анализ C-кода: cppcheck + clang --analyze + gcc -fanalyzer + кастомные правила + секреты.",
    )
    parser.add_argument("-i", "--incdir", action="append", default=[], metavar="DIR",
                         help="Папка с заголовочными файлами (относительно корня проекта). Можно указывать несколько раз.")
    parser.add_argument("-d", "--define", action="append", default=[], metavar="NAME=VAL",
                         help="Define для препроцессора (например, ATD_TLS12_SUPPORT=1). Можно указывать несколько раз.")
    parser.add_argument("-s", "--srcdir", action="append", default=[], metavar="DIR",
                         help="Папка с исходниками (.c/.h), обходится рекурсивно.")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                         help="Glob-паттерн для исключения файлов (например, '*/tests/*').")
    parser.add_argument("--logdir", default=None, metavar="DIR",
                         help="Директория для отчётов (относительно корня проекта). По умолчанию: Debug/")
    parser.add_argument("--config", default=None, metavar="FILE",
                         help="Явный путь к .analyzerrc (TOML/JSON). По умолчанию ищется в корне проекта.")
    parser.add_argument("--format", action="append", dest="formats", default=[],
                         choices=["console", "json", "html", "sarif"],
                         help="Формат(ы) отчёта. Можно указывать несколько раз. По умолчанию: console.")
    parser.add_argument("--fail-on", dest="fail_on_severity", default=None,
                         choices=["info", "style", "warning", "error", "critical"],
                         help="Минимальная критичность, при которой процесс завершится с кодом 1 (для CI/CD).")
    parser.add_argument("--fail-on-count", dest="fail_on_count", type=int, default=None,
                         help="Если найдено больше N замечаний (любой критичности) — завершить с кодом 1.")
    parser.add_argument("--jobs", "-j", dest="jobs", type=int, default=None,
                         help="Количество параллельных процессов (по умолчанию: число ядер - 1).")
    parser.add_argument("--custom-rules", dest="custom_rules_path", default=None, metavar="FILE",
                         help="JSON/TOML-файл с кастомными правилами.")
    parser.add_argument("--no-secrets", dest="enable_secret_scan", action="store_false", default=None,
                         help="Отключить детектор секретов/ключей.")
    parser.add_argument("--clang-format", dest="enable_clang_format", action="store_true", default=None,
                         help="Включить проверку форматирования через clang-format (аналог PEP8/ESLint для C).")
    parser.add_argument("--no-cache", dest="use_cache", action="store_false", default=None,
                         help="Отключить кэш результатов по хешу файла.")
    parser.add_argument("-v", "--verbose", action="store_true", default=None, help="Подробный вывод.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    project_root = os.getcwd()

    cli_overrides = {
        "includes": args.incdir,
        "defines": args.define,
        "source_dirs": args.srcdir,
        "exclude_globs": args.exclude,
        "outdir": args.logdir,
        "verbose": args.verbose,
        "jobs": args.jobs,
        "fail_on_severity": args.fail_on_severity,
        "fail_on_count": args.fail_on_count,
        "formats": args.formats,
        "custom_rules_path": args.custom_rules_path,
        "enable_secret_scan": args.enable_secret_scan,
        "enable_clang_format": args.enable_clang_format,
        "use_cache": args.use_cache,
    }

    config = load_config(project_root, args.config, cli_overrides)

    if not config.source_dirs:
        print("Ошибка: не указана ни одна директория с исходниками (-s/--srcdir или source_dirs в .analyzerrc)", file=sys.stderr)
        return 2

    if not config.formats:
        config.formats = ["console"]

    print(f"[INFO] Корень проекта: {project_root}")
    print(f"[INFO] Директории исходников: {config.source_dirs}")

    engine = AnalyzerEngine(config)
    if engine.unavailable_tools:
        print(f"[WARN] Пропущены недоступные в системе инструменты: {', '.join(engine.unavailable_tools)}")

    findings, timings = engine.run()
    report = ReportGenerator(findings, timings)

    outdir = os.path.join(project_root, config.outdir)
    if "console" in config.formats:
        print()
        print(report.to_console(verbose=bool(config.verbose)))

    other_formats = [f for f in config.formats if f != "console"]
    if other_formats:
        written = report.write_all(outdir, other_formats)
        for fmt, path in written.items():
            print(f"[INFO] Отчёт {fmt} записан в: {path}")

    # Exit code для CI/CD
    threshold = Severity.from_string(config.fail_on_severity)
    over_threshold = [f for f in findings if f.severity >= threshold]
    should_fail = bool(over_threshold) or (config.fail_on_count > 0 and len(findings) > config.fail_on_count)

    if should_fail:
        print(f"\n[FAIL] Найдено {len(over_threshold)} замечаний с критичностью >= {threshold.name} "
              f"(порог количества: {config.fail_on_count}, всего замечаний: {len(findings)})")
        return 1

    print(f"\n[OK] Порог для CI/CD не превышен ({len(findings)} замечаний всего).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

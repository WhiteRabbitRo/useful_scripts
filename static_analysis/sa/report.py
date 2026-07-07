"""ReportGenerator — форматирование результатов анализа в разные форматы."""

from __future__ import annotations

import html
import json
import os
from typing import Dict, List

from .models import Finding, Severity

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    _HAS_COLORAMA = True
except ImportError:
    _HAS_COLORAMA = False


_SEVERITY_COLOR = {
    Severity.INFO: "CYAN",
    Severity.STYLE: "WHITE",
    Severity.WARNING: "YELLOW",
    Severity.ERROR: "RED",
    Severity.CRITICAL: "MAGENTA",
}


class ReportGenerator:
    def __init__(self, findings: List[Finding], timings: Dict[str, float], tool_version: str = "2.0.0"):
        self.findings = sorted(findings, key=lambda f: f.severity, reverse=True)
        self.timings = timings
        self.tool_version = tool_version

    # ---------------------------------------------------------------- console
    def to_console(self, verbose: bool = False) -> str:
        lines = []
        by_severity: Dict[Severity, int] = {}
        for f in self.findings:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1

        for f in self.findings:
            color_name = _SEVERITY_COLOR[f.severity]
            if _HAS_COLORAMA:
                color = getattr(Fore, color_name)
                reset = Style.RESET_ALL
            else:
                color = f.severity.color_code()
                reset = "\033[0m"
            loc = f"{f.file}:{f.line}"
            cwe = f" ({f.cwe})" if f.cwe else ""
            lines.append(f"{color}[{f.severity.name:8s}]{reset} {loc} [{f.tool}/{f.rule_id}]{cwe}: {f.message}")

        lines.append("")
        lines.append("=== Итоги ===")
        for sev in sorted(by_severity.keys(), reverse=True):
            lines.append(f"  {sev.name:8s}: {by_severity[sev]}")
        lines.append(f"  ВСЕГО   : {len(self.findings)}")

        if verbose and self.timings:
            lines.append("")
            lines.append("=== Время выполнения (сек) ===")
            for tool, secs in self.timings.items():
                lines.append(f"  {tool:15s}: {secs:.2f}")

        return "\n".join(lines)

    # ------------------------------------------------------------------ json
    def to_json(self) -> str:
        return json.dumps(
            {
                "tool_version": self.tool_version,
                "summary": self._summary(),
                "findings": [f.to_dict() for f in self.findings],
                "timings": self.timings,
            },
            ensure_ascii=False,
            indent=2,
        )

    # ------------------------------------------------------------------ sarif
    def to_sarif(self) -> str:
        rules_seen = {}
        results = []
        for f in self.findings:
            rule_key = f"{f.tool}:{f.rule_id}"
            if rule_key not in rules_seen:
                rules_seen[rule_key] = {
                    "id": rule_key,
                    "name": f.rule_id,
                    "shortDescription": {"text": f.message[:120]},
                    "properties": {"cwe": f.cwe} if f.cwe else {},
                }
            results.append(f.to_sarif_result())

        sarif = {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "static-analysis-suite",
                            "informationUri": "https://example.internal/static-analysis-suite",
                            "version": self.tool_version,
                            "rules": list(rules_seen.values()),
                        }
                    },
                    "results": results,
                }
            ],
        }
        return json.dumps(sarif, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------- html
    def to_html(self) -> str:
        rows = []
        for f in self.findings:
            css_class = f.severity.name.lower()
            rows.append(
                f"<tr class='{css_class}'>"
                f"<td>{f.severity.name}</td>"
                f"<td>{html.escape(f.file)}:{f.line}</td>"
                f"<td>{html.escape(f.tool)}/{html.escape(f.rule_id)}</td>"
                f"<td>{html.escape(f.cwe or '')}</td>"
                f"<td>{html.escape(f.message)}</td>"
                f"</tr>"
            )
        summary = self._summary()
        summary_html = "".join(f"<span class='badge {k.lower()}'>{k}: {v}</span>" for k, v in summary.items())

        return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Отчёт статического анализа</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem; background: #0f1115; color: #e6e6e6; }}
  h1 {{ font-size: 1.4rem; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
  th, td {{ text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid #2a2d34; font-size: 0.85rem; }}
  th {{ background: #171a21; position: sticky; top: 0; }}
  tr.critical td:first-child {{ color: #ff5c8a; font-weight: 700; }}
  tr.error td:first-child {{ color: #ff6b6b; font-weight: 700; }}
  tr.warning td:first-child {{ color: #ffd166; }}
  tr.style td:first-child, tr.info td:first-child {{ color: #6ec6ff; }}
  .badge {{ display: inline-block; padding: 0.25rem 0.6rem; border-radius: 999px; margin-right: 0.5rem; background: #1f2430; font-size: 0.8rem; }}
</style>
</head>
<body>
  <h1>Отчёт статического анализа (v{self.tool_version})</h1>
  <div>{summary_html}</div>
  <table>
    <thead><tr><th>Severity</th><th>Расположение</th><th>Правило</th><th>CWE</th><th>Сообщение</th></tr></thead>
    <tbody>
      {''.join(rows) if rows else '<tr><td colspan="5">Замечаний не найдено 🎉</td></tr>'}
    </tbody>
  </table>
</body>
</html>"""

    def _summary(self) -> Dict[str, int]:
        summary: Dict[str, int] = {}
        for f in self.findings:
            summary[f.severity.name] = summary.get(f.severity.name, 0) + 1
        return summary

    def write_all(self, outdir: str, formats: List[str]) -> Dict[str, str]:
        os.makedirs(outdir, exist_ok=True)
        written = {}
        if "json" in formats:
            path = os.path.join(outdir, "report.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.to_json())
            written["json"] = path
        if "html" in formats:
            path = os.path.join(outdir, "report.html")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.to_html())
            written["html"] = path
        if "sarif" in formats:
            path = os.path.join(outdir, "report.sarif")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.to_sarif())
            written["sarif"] = path
        return written

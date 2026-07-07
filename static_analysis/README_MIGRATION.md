# Миграция со старого `static_analysis.sh` на новый Python-инструмент

## Почему Python, а не «улучшенный Bash»

Запрошенные требования — классы (`AnalyzerEngine`, `RuleLoader`, `ReportGenerator`,
`FileWalker`), паттерн «Стратегия», `multiprocessing`/`asyncio`, кэш AST,
JSON/TOML-конфиги, SARIF, `argparse` — не реализуемы в Bash без превращения
его в псевдо-объектную систему на костылях (массивы + `eval` + именование
функций как «методов»). Bash хорош как тонкая обёртка над CLI-утилитами, но
не как платформа для ООП-архитектуры. Поэтому ядро переписано на Python 3.10+,
а сами анализаторы (`cppcheck`, `clang --analyze`, `gcc -fanalyzer`) остались
теми же внешними бинарниками — просто вызываются из Python через `subprocess`.

## Соответствие опций

| Старый Bash-флаг         | Новый флаг                     | Комментарий |
|---------------------------|---------------------------------|-------------|
| `-i=DIR` / `--incdir=DIR` | `-i DIR` / `--incdir DIR`       | То же поведение, путь также разрешается относительно корня проекта |
| `-d=DEF` / `--define=DEF` | `-d DEF` / `--define DEF`       | Без изменений |
| `-s=DIR` / `--srcdir=DIR` | `-s DIR` / `--srcdir DIR`       | Без изменений |
| `--logdir=DIR`            | `--logdir DIR`                  | Без изменений |
| `-v` / `--verbose`        | `-v` / `--verbose`               | Без изменений (в старом скрипте был баг: переменная `VERBOS` вместо `VERBOSE` — здесь исправлено) |
| `-h` / `--help`           | `-h` / `--help`                  | Генерируется автоматически через `argparse` |
| —                          | `--format {console,json,html,sarif}` | Новое: можно указывать несколько раз |
| —                          | `--fail-on {info,style,warning,error,critical}` | Новое: порог для exit code в CI/CD |
| —                          | `--fail-on-count N`             | Новое: фейл по общему количеству замечаний |
| —                          | `--jobs N` / `-j N`             | Новое: число параллельных процессов |
| —                          | `--custom-rules FILE`            | Новое: кастомные JSON/TOML-правила |
| —                          | `--no-secrets`                   | Новое: отключить детектор секретов |
| —                          | `--clang-format`                 | Новое: проверка форматирования (замена PEP8/ESLint для C) |
| —                          | `--config FILE`                  | Новое: явный путь к `.analyzerrc` |

## Шаги миграции

1. Установите зависимости:
   ```bash
   pip install -r requirements.txt --break-system-packages
   # Внешние бинарники (если ещё не установлены):
   sudo apt-get install cppcheck clang clang-tools gcc clang-format
   ```

2. Замените вызов в CI/скриптах сборки:

   **Было:**
   ```bash
   ./scripts/static_analysis.sh -i=submodules/dtls/libatd/include \
       -d=ATD_TLS12_SUPPORT=1 -s=submodules/dtls/libatd/src
   ```

   **Стало:**
   ```bash
   ./scripts/static_analysis.py -i submodules/dtls/libatd/include \
       -d ATD_TLS12_SUPPORT=1 -s submodules/dtls/libatd/src \
       --format console --format sarif --fail-on error
   ```

   Обратите внимание: знак `=` между флагом и значением больше не обязателен
   (argparse принимает оба варианта: `-i DIR` и `-i=DIR` работать не будет —
   используйте пробел или полную форму `--incdir=DIR`).

3. (Опционально) Перенесите повторяющиеся аргументы в `.analyzerrc` в корне
   проекта — см. `.analyzerrc.example.toml`. Тогда команда сведётся к:
   ```bash
   ./scripts/static_analysis.py --fail-on error
   ```

4. Для интеграции с GitHub Advanced Security / Azure DevOps используйте
   `--format sarif` и загрузите `Debug/report.sarif` через
   `github/codeql-action/upload-sarif` (GitHub) или задачу
   `PublishCodeAnalysisResults` (Azure DevOps).

5. Старые лог-файлы (`cppcheck.out`, `clang.out`, `gccanalyzer.out`) заменены
   единым `report.json`/`report.html`/`report.sarif` в той же директории
   (`--logdir`, по умолчанию `Debug/`). Если внешние скрипты парсили старые
   файлы построчно — переключите их на чтение `report.json` (структурировано,
   с `severity`, `cwe`, `fingerprint` для дедупликации).

## Что осталось от старого поведения

- Автоматическая установка отсутствующих пакетов (`package_check_and_install`)
  **не перенесена**: неявный `sudo apt-get install` внутри CI-скрипта — плохая
  практика (нарушает воспроизводимость сборки, требует sudo). Вместо этого
  недоступные инструменты просто пропускаются с предупреждением
  (`[WARN] Пропущены недоступные в системе инструменты: ...`), а установка
  выносится в Dockerfile/CI-шаги, как и положено.
- Про PEP8/ESLint: они неприменимы к C. Их роль выполняет `--clang-format`
  (проверка соответствия `.clang-format` в режиме `--dry-run --Werror`).

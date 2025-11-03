# Repository Guidelines

## Project Structure & Module Organization
- Root scripts: `announcement_processor.py`, `announcement_prv_processor.py`, utilities like `reprocess_announcements.py` and debug tools.
- Core library code: `src/`
  - `src/config/` (config, logging, templates), `src/core/` (processing flow), `src/models/` (SQLAlchemy DB models), `src/utils/` (OCR, file, parsing helpers).
- Data and logs: `data_dir/` (inputs), `output/` (generated; may be created at runtime), `logs/`.
- Tests and examples: `test_*.py` scripts in repo root; images and sample CSVs for debugging.

## Build, Test, and Development Commands
- Setup: `bash install.sh` — creates venv (optional) and installs minimal/full requirements.
- Run main processor: `bash run.sh` or `python announcement_processor.py --help`.
- PRV processor example: `python announcement_prv_processor.py --data prv8 --date-filter 20250710`.
- Ad‑hoc tests: `python test_date_filter.py`, `python test_flat_structure.py`, `python simple_test.py <record_id>`.
- Env: copy `.env` locally and adjust DB/Ollama settings; export `PYTHONPATH=$(pwd):$PYTHONPATH` if running without `run.sh`.

## Coding Style & Naming Conventions
- Python 3.10+. Use 4‑space indentation, UTF‑8, and type hints where practical.
- Filenames: follow existing patterns — many modules under `src/` use CamelCase (e.g., `announcementDatabase.py`); new top‑level scripts and tests use snake_case (`my_tool.py`, `test_feature.py`). Keep imports consistent with file casing.
- No enforced linter in repo; prefer black/ruff style locally (line length 100) but do not reformat unrelated files.

## Testing Guidelines
- Lightweight script-style tests live at repo root (`test_*.py`). Add focused tests near affected code or extend existing ones.
- Optional pytest use is fine, but do not require it; prioritize runnable scripts with clear prints/asserts.
- Include sample inputs under `data_dir/` and document expected outputs (e.g., `output/<folder>/content.md`).

## Commit & Pull Request Guidelines
- Commits: concise, imperative subject; include scope when helpful (e.g., `models: fix duplicate folder handling`). Keep related changes together.
- PRs: clear description, reproduction steps, and sample commands. Note DB/schema changes (see `create_announcement_pre_processing_table.sql`). Attach logs or screenshots when output formatting changes.
- Security: never commit real secrets. Use local `.env`; redact keys in examples.


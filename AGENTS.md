# Repository Guidelines

## Project Structure & Module Organization
This workspace is currently minimal: the only committed project artifact is a local Python virtual environment in `.venv/` (Python 3.12). Treat `.venv/` as generated, local-only infrastructure and do not place application code there. Add new runtime code under `src/` or a top-level package directory, keep tests in `tests/`, and place non-code assets in a dedicated folder such as `assets/` if they are introduced.

## Build, Test, and Development Commands
Use the existing virtual environment for local work:

- `source .venv/bin/activate` activates the repository's Python environment.
- `.venv/bin/python -m pip list` shows installed packages; the environment is currently nearly empty.
- `.venv/bin/python -m pip install -r requirements.txt` is the expected install pattern once a dependency file is added.
- `.venv/bin/python -m pytest` should be the default test entry point when tests are introduced.
- `npm install --prefix kata_viewer` installs dependencies for the static React viewer.
- `npm run dev --prefix kata_viewer` copies the root CSV reports and starts the viewer locally.
- `npm run build --prefix kata_viewer` copies the root CSV reports and builds the static viewer.
- `npm run preview --prefix kata_viewer` serves the built viewer locally.

If you add a build script, task runner, or alternate test command, document it in this file in the same change.

## Coding Style & Naming Conventions
Target Python 3.12. Use 4-space indentation, `snake_case` for modules, functions, and variables, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants. Keep modules focused on a single concern and avoid mixing reusable logic with command-line entry points. No formatter or linter is configured yet, so keep style consistent and introduce tooling explicitly if needed.

## Testing Guidelines
No test framework is committed yet. When adding tests, prefer `pytest`, store them in `tests/`, and name files `test_<feature>.py`. Keep tests deterministic, fast, and isolated from network or machine-specific state. Add regression tests with each bug fix.

## Commit & Pull Request Guidelines
Git history is not available in this workspace, so follow standard imperative commit subjects such as `Add kata scoring parser`. Keep commits narrowly scoped and explain behavior changes in the body when needed. Pull requests should include a short summary, validation steps, linked issues when applicable, and screenshots only for visible UI changes.

## Configuration & Security
Do not commit secrets, API keys, or machine-specific files. Prefer a documented `.env.example` for configuration once environment variables are needed.

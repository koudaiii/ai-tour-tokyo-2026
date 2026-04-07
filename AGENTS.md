# Repository Guidelines

## Project Structure & Module Organization
- Application files (`app.py`, `pyproject.toml`, `Dockerfile`, `compose.yml`) are at the repository root.
- `sql/` holds PostgreSQL schema (`bootstrap_create_table.sql`), PostgreSQL dump (`isuconp_data.dump`), and bootstrap helper SQL files (`bootstrap_*.sql`).
- `templates/` contains Jinja2 HTML templates; `public/` holds static assets (CSS, JS, images).
- `benchmarker/` contains the Go load tester, while `provisioning/` tracks Ansible roles for operational parity.

## Build, Test, and Development Commands
- `docker compose up`: run nginx, the app tier, PostgreSQL, and Memcached locally.
- `cd benchmarker && make && ./bin/benchmarker -t "http://localhost:8080" -u ./userdata`: rebuild and execute the scorer after optimizations.

## Coding Style & Naming Conventions
- Python: follow PEP 8; dependencies managed via `uv` (pyproject.toml / uv.lock).
- Shared SQL, template, and static asset filenames stay snake_case; keep uploaded media names space-free.

## Testing Guidelines
- Supplement changes with unit tests when touching core logic (`pytest`) even if suites are sparse.
- Benchmark every performance tweak and note the score delta in your PR description.
- For schema updates, load `sql/bootstrap_create_table.sql` and restore `sql/isuconp_data.dump` with `pg_restore`, then smoke-test login plus timeline flows.

## Commit & Pull Request Guidelines
- Use imperative commit subjects (`optimize timeline query`); dependency bumps often follow `chore(deps):`/`fix(deps):` patterns.
- Keep commits narrowly scoped so regressions are traceable; include schema files and generated assets with the change.
- PRs summarize the bottleneck, the fix, benchmark results, and env var updates; link issues when applicable.
- Attach screenshots or shell snippets for benchmark output or UI adjustments and flag manual deploy steps.

## Security & Configuration Tips
- Never commit secrets or dumps; reference required env vars (`ISUCONP_DB_HOST`, etc.) instead.
- Rotate credentials through `provisioning/` and keep sensitive data vaulted.
- Enforce login checks on new endpoints and prefer filesystem-backed images over raw BLOB responses when optimizing.

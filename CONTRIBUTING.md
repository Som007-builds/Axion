# Contributing to Axion

Axion is a research prototype. Contributions that improve correctness,
reproducibility, and evidence quality are more valuable than new surface area.

## Development setup

Follow [Installation and quick start](README.md#installation-and-quick-start).
For backend work you only need the offline test dependencies:

```bash
python -m venv venv
source venv/bin/activate          # Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

Neo4j and ChromaDB are required only for integration tests and live runs.

## Before opening a pull request

```bash
pytest                            # 252 offline tests; must stay green
pytest -m integration             # only if you have live Neo4j + ChromaDB
cd axion && pnpm lint && pnpm exec tsc --noEmit && pnpm build
```

If your change touches evaluation logic, also run:

```bash
python eval/run_eval.py --predictor majority
python eval/judge_ablation.py --report-only
```

## Scope and conventions

- Keep pull requests focused on one concern.
- Match the existing structure, naming, and logging style.
- New backend behaviour needs a test; evaluation changes need a before/after
  number and an updated entry in `eval/README.md`.
- Frontend changes must stay inside the Cobalt Grid token system
  (`axion/app/globals.css`): square corners, the two-colour rule
  (`#F0EBDE` paper / `#1F2BE0` ink), no shadows or gradients, and monochrome
  status encodings.
- Do not commit credentials, `.env` files, downloaded PDFs, vector stores, or
  generated candidate dumps. `.gitignore` already covers the usual cases.

## Reporting problems

Use the GitHub issue templates. For security-sensitive reports, follow
[SECURITY.md](SECURITY.md) instead of opening a public issue.

## Large changes

Open an issue before starting work that changes the data model, the evaluation
protocol, the API contract, or the relationship ontology. Those changes affect
stored data and published numbers, so they need agreement on the approach first.

# eval/baseline_llm_eval.py
"""
Deprecated shim.

The original script hard-coded the lowercase ``eval/data/test.csv`` path (which
breaks on case-sensitive filesystems) and conflated same-paper pairs, UNRELATED
verdicts and JSON parse failures into a single "excluded" bucket.

All logic now lives in ``eval/run_eval.py``. This shim preserves the old entry
point so existing docs/commands keep working:

    python eval/baseline_llm_eval.py
    # equivalent to:
    python eval/run_eval.py --predictor llm --dataset test.csv
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from eval.run_eval import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(
        main(["--predictor", "llm", "--dataset", "test.csv"] + sys.argv[1:])
    )

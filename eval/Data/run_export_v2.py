from pathlib import Path
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from eval.Data.export_candidate_pairs import export_candidate_pairs

out_path = Path("eval/Data/candidate_pairs_v2.csv")
count = export_candidate_pairs(out_path)
print(f"Exported {count} candidate pairs to {out_path}")

import pandas as pd
import os

fpath = os.path.join(os.path.dirname(__file__), "labeled_pairs.csv")
df = pd.read_csv(fpath)

out = os.path.join(os.path.dirname(__file__), "pairs_text_only.txt")
with open(out, "w", encoding="utf-8") as f:
    for i, row in df.iterrows():
        f.write(f"ROW {i}\n")
        f.write(f"  A [{row['claim_a_paper_title']}]: {row['claim_a_text']}\n")
        f.write(f"  B [{row['claim_b_paper_title']}]: {row['claim_b_text']}\n")
        f.write(f"  distance: {row['distance']}\n")
        f.write(f"  same_paper: {row['claim_a_arxiv_id'] == row['claim_b_arxiv_id']}\n")
        f.write("\n")

print(f"Wrote {len(df)} pairs to {out}")

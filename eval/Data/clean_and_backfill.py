import os
import pandas as pd

def clean_and_backfill():
    # Paths
    labeled_path = os.path.join("eval", "Data", "labeled_pairs.csv")
    cleaned_path = os.path.join("eval", "Data", "labeled_pairs_cleaned.csv")
    candidates_path = os.path.join("eval", "Data", "candidate_pairs.csv")
    backfill_path = os.path.join("eval", "Data", "candidate_pairs_backfill.csv")

    # 1. Load and clean labeled_pairs.csv
    labeled_df = pd.read_csv(labeled_path)
    # Remove rows where arxiv_ids are the same
    cleaned_df = labeled_df[labeled_df["claim_a_arxiv_id"] != labeled_df["claim_b_arxiv_id"]].copy()
    cleaned_df.to_csv(cleaned_path, index=False)

    print(f"Original labeled_pairs count: {len(labeled_df)}")
    print(f"Cleaned labeled_pairs_cleaned count: {len(cleaned_df)}")

    # Check for CONTRADICTS count in cleaned dataset
    contradicts_count = (cleaned_df["label"] == "CONTRADICTS").sum()
    print(f"Total CONTRADICTS in cleaned dataset: {contradicts_count}")
    if contradicts_count < 10:
        print("WARNING: CONTRADICTS examples are very low. Metrics for this class will be unreliable.")

    # Check for any remaining same-arxiv_id pairs
    same_arxiv_cleaned = (cleaned_df["claim_a_arxiv_id"] == cleaned_df["claim_b_arxiv_id"]).sum()
    print(f"Same-arxiv_id pairs in cleaned dataset: {same_arxiv_cleaned}")

    # 2. Generate backfill candidates
    if not os.path.exists(candidates_path):
        print(f"Error: {candidates_path} not found. Run export_candidate_pairs.py first.")
        return

    candidates_df = pd.read_csv(candidates_path)

    # Exclude same-arxiv_id pairs directly from candidates
    candidates_df = candidates_df[candidates_df["claim_a_arxiv_id"] != candidates_df["claim_b_arxiv_id"]].copy()

    # We need to exclude pairs already in the cleaned labeled set.
    # To do this safely, we construct a normalized pair key for both dataframes.
    def make_key(row):
        return tuple(sorted([str(row["claim_a_id"]), str(row["claim_b_id"])]))

    labeled_keys = set(cleaned_df.apply(make_key, axis=1))

    # Filter out candidates already labeled
    candidates_df["pair_key"] = candidates_df.apply(make_key, axis=1)
    new_candidates_df = candidates_df[~candidates_df["pair_key"].isin(labeled_keys)].copy()

    # Sort by distance ascending
    new_candidates_df = new_candidates_df.sort_values(by="distance", ascending=True)

    # Select required number (300 total - current cleaned + 15 buffer)
    target_total = 300
    needed_count = max(0, target_total - len(cleaned_df)) + 15

    backfill_df = new_candidates_df.head(needed_count).copy()

    # Verify no same-arxiv_id pairs in backfill
    same_arxiv_backfill = (backfill_df["claim_a_arxiv_id"] == backfill_df["claim_b_arxiv_id"]).sum()
    print(f"Same-arxiv_id pairs in backfill dataset: {same_arxiv_backfill}")

    # Map columns for output: pair_id, claim_id_a, claim_id_b, text_a, text_b, cosine_distance
    backfill_df = backfill_df.reset_index(drop=True)
    backfill_out = pd.DataFrame()
    
    # pair_id can just be an index
    backfill_out["pair_id"] = range(len(backfill_df))
    backfill_out["claim_id_a"] = backfill_df["claim_a_id"]
    backfill_out["claim_id_b"] = backfill_df["claim_b_id"]
    backfill_out["text_a"] = backfill_df["claim_a_text"]
    backfill_out["text_b"] = backfill_df["claim_b_text"]
    backfill_out["cosine_distance"] = backfill_df["distance"]

    backfill_out.to_csv(backfill_path, index=False)
    print(f"Generated {len(backfill_out)} new backfill candidates saved to {backfill_path}")


if __name__ == "__main__":
    clean_and_backfill()

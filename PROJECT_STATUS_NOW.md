# Project Status Report (`PROJECT_STATUS_NOW.md`)
**Generated at:** 2026-08-10 (Current Workspace Snapshot)

> ⚠️ **SUPERSEDED.** This is a point-in-time snapshot from 2026-08-10. The eval
> dataset has changed since (see §8 of [`PROJECT_INFO.md`](PROJECT_INFO.md) and
> [`eval/README.md`](eval/README.md)): `eval/Data/Labeled_pairs.csv` is now
> 0 bytes and the harness was rewritten. Do not rely on the row counts below.
> Authoritative inventory: [`PROJECT_INFO.md`](PROJECT_INFO.md).

---

## 1. DATASET STATE

### File List & Row Counts (`eval/Data/`)

| File Name | Size | Line/Row Count | Label / Column Summary |
| :--- | :--- | :--- | :--- |
| `candidate_pairs.csv` | 35.7 MB | **2,227 rows** | Raw exported semantic candidate claim pairs (top-8 neighbors). |
| `candidate_pairs_backfill.csv` | 85.2 KB | **247 rows** | Candidates sorted by cosine distance for backfilling dataset. |
| `labeled_pairs.csv` | 5.08 MB | **300 rows** | Full expert-annotated claim pairs dataset (300 pairs). |
| `labeled_pairs_cleaned.csv` | 1.05 MB | **68 rows** | Filtered dataset with intra-paper (same `arxiv_id`) pairs removed. |
| `train.csv` | 3.57 MB | **210 rows** | Stratified training split (70% of `labeled_pairs.csv`). |
| `val.csv` | 756.8 KB | **45 rows** | Stratified validation split (15% of `labeled_pairs.csv`). |
| `test.csv` | 758.2 KB | **45 rows** | Stratified test split (15% of `labeled_pairs.csv`). |
| `pairs_text_only.txt` | 140.2 KB | **1,800 lines** | Text formatted view of `labeled_pairs.csv` for human inspection. |
| `embeddings_cache.pkl` | 0 bytes | **0 rows** | Empty pickle cache file. |

---

### Label Distributions (Labeled Files)

* **`labeled_pairs.csv`** (n = 300)
  * `UNRELATED`: 177 (59.0%)
  * `SUPPORTS`: 118 (39.3%)
  * `CONTRADICTS`: 5 (1.7%)

* **`labeled_pairs_cleaned.csv`** (n = 68; same-paper pairs removed)
  * `UNRELATED`: 68 (100.0%)
  * `SUPPORTS`: 0 (0.0%)
  * `CONTRADICTS`: 0 (0.0%)
  * *Note: All 118 `SUPPORTS` and 5 `CONTRADICTS` pairs in the original `labeled_pairs.csv` were intra-paper pairs (from the exact same paper).*

* **`train.csv`** (n = 210; 70% stratified split)
  * `UNRELATED`: 124 (59.0%)
  * `SUPPORTS`: 83 (39.5%)
  * `CONTRADICTS`: 3 (1.4%)

* **`val.csv`** (n = 45; 15% stratified split)
  * `UNRELATED`: 27 (60.0%)
  * `SUPPORTS`: 17 (37.8%)
  * `CONTRADICTS`: 1 (2.2%)

* **`test.csv`** (n = 45; 15% stratified split)
  * `UNRELATED`: 26 (57.8%)
  * `SUPPORTS`: 18 (40.0%)
  * `CONTRADICTS`: 1 (2.2%)

---

### Stage 1 Ingestion Status & Neo4j Verification

* **Status:** **FULLY COMPLETED** (Stage 1 ingestion successfully finished).
* **Paper Count:** **48 papers** in Neo4j (increased from 9 baseline papers to 48 papers).
* **Claim Nodes in Neo4j:** **2,389 claims**.
* **Vector Embeddings in ChromaDB:** **2,389 vectors**.
* **Neo4j Relationships:**
  * `EXTRACTED_FROM`: 2,389
  * `CONTRADICTS`: 224
  * `SUPPORTS`: 132
  * `RELATED_TO`: 93

---

## 2. CODE STATE

### Modifiability & Integration Audits

* **`agents/contradiction.py` Status:** **Unmodified / Baseline State.**
  * `git status` confirms zero working directory modifications.
  * Uses standard prompt-based LLM classification (`check_pair` calling `call_llm`).
  * No classifier model, hybrid cascade, or local model integration has been attempted inside this file.

* **Classifier & Model Directory Status:**
  * Directory `eval/classifier/`: **Does NOT exist.**
  * Directory `eval/models/`: **Exists but is empty** (0 files / 0 trained model weights).

---

### Script Inventory (`eval/` & `eval/Data/`)

1. **`eval/baseline_llm_eval.py`**: Evaluates baseline LLM prediction performance on `eval/data/test.csv` using `agents.contradiction.check_pair()` and outputs latency/accuracy metrics to `eval/results/baseline_llm.json`.
2. **`eval/run_eval.py`**: Empty script placeholder (0 bytes).
3. **`eval/Data/apply_labels.py`**: Applies expert annotation dictionary to 300 candidate pairs in `labeled_pairs.csv`.
4. **`eval/Data/clean_and_backfill.py`**: Removes intra-paper pairs (`claim_a_arxiv_id == claim_b_arxiv_id`) from `labeled_pairs.csv` to generate `labeled_pairs_cleaned.csv` and outputs top un-labeled candidate pairs to `candidate_pairs_backfill.csv`.
5. **`eval/Data/export_candidate_pairs.py`**: Searches ChromaDB for top-8 semantic claim neighbors across papers and exports candidate claim pairs with embeddings to CSV.
6. **`eval/Data/extract_text.py`**: Exports formatted text representation of `labeled_pairs.csv` into `pairs_text_only.txt` for manual inspection.
7. **`eval/Data/inspect_pairs.py`**: Helper script printing shape, column list, and non-null count for `labeled_pairs.csv`.
8. **`eval/Data/print_stats.py`**: Displays top 15 most similar pairs and summary distance stats for `candidate_pairs_backfill.csv`.
9. **`eval/Data/print_v2_stats.py`**: Helper script printing top 20 pairs and distance statistics for `candidate_pairs_v2.csv`.
10. **`eval/Data/run_export_v2.py`**: Wrapper script executing `export_candidate_pairs()` targeted at `eval/data/candidate_pairs_v2.csv`.
11. **`eval/Data/split_dataset.py`**: Executes stratified random splitting (70% train / 15% val / 15% test) on `labeled_pairs.csv`.

---

## 3. RESULTS STATE

### Evaluation Summary (`eval/results/`)

* **File Present:** `eval/results/baseline_llm.json`
* **Timestamp:** `2026-08-02T08:38:51Z`
* **Version Status:** **OLD CONTAMINATED VERSION.**
  * Generated on August 2 on the uncleaned dataset.
  * Contains `latency_ms: 0.0` for all intra-paper pairs (same `arxiv_id`) because `check_pair()` immediately returned `None` when checking same-paper pairs, which defaulted to `UNRELATED` in early metrics.
  * Has **NOT** been re-run on the cleaned dataset (`labeled_pairs_cleaned.csv`) or the newly expanded 48-paper graph.

* **Recorded Baseline Metrics:**
  * **Accuracy:** `0.4889`
  * **Precision (Macro):** `0.1789`
  * **Recall (Macro):** `0.2821`
  * **F1 (Macro):** `0.2189`
  * **Average Latency:** `216.25 ms`
  * **P50 Latency:** `0.00 ms`
  * **P95 Latency:** `1,037.75 ms`

---

## 4. LAST KNOWN ACTION

* **Last Action Before Hang / Restart:**
  * The ingestion pipeline (Stage 1) for fetching overlapping arXiv papers was launched in the background, followed by initiating `run_export_v2.py` for exporting updated candidate pairs from the 48-paper graph.

* **State of Partial Writes & Databases:**
  * **Neo4j Graph Database:** **Complete and Consistent.** All 48 paper nodes, 2,389 claim nodes, and 2,838 graph relationships are completely written and indexed.
  * **ChromaDB Vector Index:** **Complete and Consistent.** All 2,389 claim vector embeddings are indexed and in sync with Neo4j.
  * **CSV Exports:** `candidate_pairs_v2.csv` was not created before the restart, leaving no corrupted partial CSV file.
  * **Existing Data Splits:** `train.csv`, `val.csv`, `test.csv`, `labeled_pairs.csv`, and `labeled_pairs_cleaned.csv` are intact and uncorrupted.
  * **Conclusion:** No cleanup or manual database repair is required. The system is in a clean, consistent state ready for next steps.

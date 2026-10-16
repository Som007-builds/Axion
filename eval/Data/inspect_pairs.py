import pandas as pd
import os

fpath = os.path.join(os.path.dirname(__file__), "labeled_pairs.csv")
df = pd.read_csv(fpath)
print(f"Total rows: {len(df)}")
print(f"Columns: {list(df.columns)}")
print(f"Label column values: {df['label'].unique()}")
print(f"Non-null labels: {df['label'].notna().sum()}")

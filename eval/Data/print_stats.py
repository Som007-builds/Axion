import pandas as pd
df = pd.read_csv('eval/Data/candidate_pairs_backfill.csv')
print('--- Top 15 Most Similar Candidate Pairs ---\n')
for i, row in df.head(15).iterrows():
    dist = row['cosine_distance']
    text_a = row['text_a']
    text_b = row['text_b']
    print(f'Pair {i+1} (Distance: {dist:.4f})')
    print(f'Claim A: {text_a}')
    print(f'Claim B: {text_b}')
    print('-'*80)

print('\n--- Cosine Distance Stats (n=247) ---')
print(f'Min:    {df["cosine_distance"].min():.4f}')
print(f'Max:    {df["cosine_distance"].max():.4f}')
print(f'Median: {df["cosine_distance"].median():.4f}')

import pandas as pd
df = pd.read_csv('eval/Data/candidate_pairs_v2.csv')

# Drop any potential exact duplicate cross-paper pair if any
df = df.drop_duplicates(subset=["claim_a_id", "claim_b_id"])

print('--- Top 20 Most Similar Candidate Pairs (V2) ---\n')
for i, row in df.head(20).iterrows():
    dist = row['distance'] # V2 script outputs 'distance', not 'cosine_distance' unless renamed
    text_a = row['claim_a_text']
    text_b = row['claim_b_text']
    print(f'Pair {i+1} (Distance: {dist:.4f})')
    print(f'Claim A: {text_a}')
    print(f'Claim B: {text_b}')
    print('-'*80)

print('\n--- Cosine Distance Stats (n={}) ---'.format(len(df)))
print(f'Min:    {df["distance"].min():.4f}')
print(f'Max:    {df["distance"].max():.4f}')
print(f'Median: {df["distance"].median():.4f}')

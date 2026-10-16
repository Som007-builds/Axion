import csv
from collections import Counter

with open('eval/Data/contradicts_review_labeled.csv', 'r', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))

print('Total rows:', len(rows))
counts = Counter(r['human_label'] for r in rows)
for label in ('CONTRADICTS', 'SUPPORTS', 'UNRELATED'):
    print(f'  {label}: {counts.get(label, 0)}')

print()
print('=== CONTRADICTS pairs ===')
for r in rows:
    if r['human_label'] == 'CONTRADICTS':
        pid = r["pair_id"]
        ta = r["text_a"][:90]
        tb = r["text_b"][:90]
        print(f'  [{pid}] A: {ta}')
        print(f'       B: {tb}')
        print()

print('=== SUPPORTS pairs ===')
for r in rows:
    if r['human_label'] == 'SUPPORTS':
        pid = r["pair_id"]
        ta = r["text_a"][:90]
        tb = r["text_b"][:90]
        print(f'  [{pid}] A: {ta}')
        print(f'       B: {tb}')
        print()

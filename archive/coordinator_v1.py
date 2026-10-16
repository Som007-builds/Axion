import json
from archive.graph_queries_sqlite import get_all_claims, get_contradictions, get_gaps
from embeddings.store import find_similar_claims
from llm import call_llm

SYNTHESIS_PROMPT = """You are a research synthesizer. A researcher has asked:

"{question}"

Here is what the field's knowledge graph contains:

RELEVANT CLAIMS ({n_claims} total):
{claims}

RELEVANT CONTRADICTIONS ({n_contradictions} total):
{contradictions}

RELEVANT GAPS ({n_gaps} total):
{gaps}

Synthesize this into a structured report. Be specific, cite paper titles where possible.

Return ONLY valid JSON, no other text:
{{
  "consensus": [
    "A specific thing the field broadly agrees on (cite papers)"
  ],
  "disputed": [
    {{
      "topic": "what is disputed",
      "positions": ["position from paper A", "opposing position from paper B"]
    }}
  ],
  "missing": [
    "A specific unanswered question the field has not addressed"
  ],
  "recommended_next_papers": [
    "A type of study or experiment that would resolve key disputes or gaps"
  ]
}}
"""


def run(research_question: str) -> dict:
    print(f"\n=== Coordinator: '{research_question}' ===\n")

    # 1. Find relevant claims via semantic search
    similar_claim_results = find_similar_claims(research_question, n_results=15)
    relevant_claim_ids = set()
    relevant_claims_text = ""

    for i, r in enumerate(similar_claim_results[:10]):
        relevant_claims_text += f"{i+1}. [{r['metadata'].get('arxiv_id', '?')}] {r['text']}\n"
        cid = int(r["doc_id"].replace("claim_", ""))
        relevant_claim_ids.add(cid)

    # 2. Find relevant contradictions
    all_contradictions = get_contradictions()
    relevant_contradictions = [
        c for c in all_contradictions
        if c["claim_a_id"] in relevant_claim_ids
        or c["claim_b_id"] in relevant_claim_ids
    ][:5]

    contradictions_text = ""
    for c in relevant_contradictions:
        contradictions_text += (
            f"- [{c['paper_a'][:40]}] vs [{c['paper_b'][:40]}]: "
            f"{c['explanation']}\n"
        )

    # 3. Find relevant gaps
    all_gaps = get_gaps()
    relevant_gaps = [
        g for g in all_gaps
        if any(cid in relevant_claim_ids for cid in g["related_claims"])
    ][:5]

    gaps_text = "\n".join(f"- {g['text']}" for g in relevant_gaps)

    # 4. Synthesize with LLM
    prompt = SYNTHESIS_PROMPT.format(
        question=research_question,
        n_claims=len(similar_claim_results),
        claims=relevant_claims_text or "None found.",
        n_contradictions=len(relevant_contradictions),
        contradictions=contradictions_text or "None found.",
        n_gaps=len(relevant_gaps),
        gaps=gaps_text or "None found."
    )

    raw = call_llm(prompt, max_tokens=2000)

    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        data = json.loads(raw[start:]) if start != -1 else {}

    return data


def format_report(question: str, result: dict) -> str:
    lines = [
        f"# Axion Report",
        f"**Question:** {question}\n",
        "## What the field agrees on",
    ]
    for item in result.get("consensus", []):
        lines.append(f"- {item}")

    lines.append("\n## What is disputed")
    for d in result.get("disputed", []):
        lines.append(f"\n**{d['topic']}**")
        for p in d.get("positions", []):
            lines.append(f"  - {p}")

    lines.append("\n## What is missing (Research Gaps)")
    for gap in result.get("missing", []):
        lines.append(f"- {gap}")

    lines.append("\n## Recommended next studies")
    for rec in result.get("recommended_next_papers", []):
        lines.append(f"- {rec}")

    return "\n".join(lines)


if __name__ == "__main__":
    question = "Does chain-of-thought prompting help small language models?"
    result = run(question)
    print(format_report(question, result))
# graph/neo4j_queries.py
"""
Neo4j Cypher query layer.
Drop-in replacement for graph/queries.py.
All functions have identical signatures and return formats.
"""
from graph.neo4j_client import run_query, run_write


# ─────────────────────────────────────────────────────────────
# Papers
# ─────────────────────────────────────────────────────────────

def insert_paper(arxiv_id: str, title: str, authors: str,
                 abstract: str, published: str) -> str:
    """
    Insert or update a paper. Returns arxiv_id (used as primary key in Neo4j).
    """
    year = None
    if published and len(published) >= 4:
        try:
            year = int(published[:4])
        except ValueError:
            pass

    run_write("""
        MERGE (p:Paper {arxiv_id: $arxiv_id})
        SET p.title = $title,
            p.authors = $authors,
            p.abstract = $abstract,
            p.published = $published,
            p.year = $year
    """, {
        "arxiv_id": arxiv_id,
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "published": published,
        "year": year
    })
    return arxiv_id


def get_paper_by_arxiv_id(arxiv_id: str) -> dict | None:
    results = run_query("""
        MATCH (p:Paper {arxiv_id: $arxiv_id})
        RETURN p.arxiv_id AS arxiv_id, p.title AS title,
               p.authors AS authors, p.abstract AS abstract,
               p.published AS published, p.year AS year
    """, {"arxiv_id": arxiv_id})
    return results[0] if results else None


# ─────────────────────────────────────────────────────────────
# Claims
# ─────────────────────────────────────────────────────────────

def insert_claim(paper_id: str, claim_text: str, section: str,
                 confidence: float = 1.0, embedding_id: str = None,
                 paper_year: int = None, structured: dict = None) -> str:
    """
    Insert a claim and link it to its paper.
    paper_id is arxiv_id in Neo4j (not SQLite int).
    Returns the Neo4j elementId string.

    Phase 4: `structured` dict may contain:
        subject, predicate, object_val, metric, direction, evidence_span, conditions (JSON str)
    Old callers without `structured` are fully backward-compatible.
    """
    import json as _json

    # Build base properties
    props = {
        "arxiv_id":     paper_id,
        "text":         claim_text,
        "section":      section,
        "confidence":   confidence,
        "embedding_id": embedding_id or "",
        "paper_year":   paper_year,
        "subject":      "",
        "predicate":    "",
        "object_val":   "",
        "metric":       "",
        "direction":    "unclear",
        "evidence_span": "",
        "conditions":   "{}",
    }

    if structured and isinstance(structured, dict):
        for field in ("subject", "predicate", "metric", "direction", "evidence_span"):
            val = structured.get(field)
            if val and isinstance(val, str):
                props[field] = val.strip()
        # "object" is a reserved Cypher keyword — stored as "object_val"
        obj_val = structured.get("object") or structured.get("object_val")
        if obj_val and isinstance(obj_val, str):
            props["object_val"] = obj_val.strip()
        cond = structured.get("conditions")
        if cond and isinstance(cond, dict):
            props["conditions"] = _json.dumps(cond)
        elif cond and isinstance(cond, str):
            props["conditions"] = cond

    result = run_write("""
        MATCH (p:Paper {arxiv_id: $arxiv_id})
        CREATE (c:Claim {
            text:         $text,
            section:      $section,
            confidence:   $confidence,
            embedding_id: $embedding_id,
            paper_year:   $paper_year,
            subject:      $subject,
            predicate:    $predicate,
            object_val:   $object_val,
            metric:       $metric,
            direction:    $direction,
            evidence_span: $evidence_span,
            conditions:   $conditions
        })
        CREATE (c)-[:EXTRACTED_FROM]->(p)
        SET c.claim_id = elementId(c)
        RETURN elementId(c) AS claim_id
    """, props)
    return result[0]["claim_id"] if result else None



def get_all_claims() -> list[dict]:
    results = run_query("""
        MATCH (c:Claim)-[:EXTRACTED_FROM]->(p:Paper)
        RETURN elementId(c) AS id, c.text AS text, c.section AS section,
               c.confidence AS confidence, p.arxiv_id AS arxiv_id,
               p.title AS paper_title, c.paper_year AS paper_year
    """)
    return results


def get_claims_in_year_range(year_start: int, year_end: int) -> list[dict]:
    """
    Return all claims from papers published within [year_start, year_end].
    Native Cypher range filter — no post-processing needed.
    """
    results = run_query("""
        MATCH (c:Claim)-[:EXTRACTED_FROM]->(p:Paper)
        WHERE c.paper_year >= $year_start AND c.paper_year <= $year_end
        RETURN elementId(c) AS id, c.text AS text, c.section AS section,
               c.confidence AS confidence, p.arxiv_id AS arxiv_id,
               p.title AS paper_title, c.paper_year AS paper_year
        ORDER BY c.paper_year ASC
    """, {"year_start": year_start, "year_end": year_end})
    return results


# ─────────────────────────────────────────────────────────────
# Relationships
# ─────────────────────────────────────────────────────────────

def insert_relationship(claim_a_id: int, claim_b_id: int,
                        rel_type: str, explanation: str,
                        confidence: float) -> None:
    """
    Insert a CONTRADICTS or SUPPORTS relationship between two claims.
    """
    if rel_type == "CONTRADICTS":
        run_write("""
            MATCH (a:Claim) WHERE elementId(a) = $claim_a_id
            MATCH (b:Claim) WHERE elementId(b) = $claim_b_id
            MERGE (a)-[r:CONTRADICTS]->(b)
            SET r.explanation = $explanation,
                r.confidence = $confidence
        """, {
            "claim_a_id": claim_a_id,
            "claim_b_id": claim_b_id,
            "explanation": explanation,
            "confidence": confidence
        })
    elif rel_type == "SUPPORTS":
        run_write("""
            MATCH (a:Claim) WHERE elementId(a) = $claim_a_id
            MATCH (b:Claim) WHERE elementId(b) = $claim_b_id
            MERGE (a)-[r:SUPPORTS]->(b)
            SET r.explanation = $explanation,
                r.confidence = $confidence
        """, {
            "claim_a_id": claim_a_id,
            "claim_b_id": claim_b_id,
            "explanation": explanation,
            "confidence": confidence
        })


def get_contradictions() -> list[dict]:
    """
    Returns all CONTRADICTS relationships with both claim texts and paper titles.
    Includes claim_a_id and claim_b_id for coordinator v2 matching.
    """
    results = run_query("""
        MATCH (a:Claim)-[r:CONTRADICTS]->(b:Claim)
        MATCH (a)-[:EXTRACTED_FROM]->(pa:Paper)
        MATCH (b)-[:EXTRACTED_FROM]->(pb:Paper)
        RETURN elementId(r) AS id,
               r.explanation AS explanation,
               r.confidence AS confidence,
               a.text AS claim_a,
               a.section AS claim_a_section,
               a.confidence AS claim_a_confidence,
               a.evidence_span AS claim_a_evidence_span,
               a.subject AS claim_a_subject,
               a.predicate AS claim_a_predicate,
               a.object_val AS claim_a_object_val,
               a.metric AS claim_a_metric,
               a.direction AS claim_a_direction,
               a.conditions AS claim_a_conditions,
               pa.title AS paper_a,
               pa.arxiv_id AS paper_a_arxiv_id,
               b.text AS claim_b,
               b.section AS claim_b_section,
               b.confidence AS claim_b_confidence,
               b.evidence_span AS claim_b_evidence_span,
               b.subject AS claim_b_subject,
               b.predicate AS claim_b_predicate,
               b.object_val AS claim_b_object_val,
               b.metric AS claim_b_metric,
               b.direction AS claim_b_direction,
               b.conditions AS claim_b_conditions,
               pb.title AS paper_b,
               pb.arxiv_id AS paper_b_arxiv_id,
               elementId(a) AS claim_a_id,
               elementId(b) AS claim_b_id
        ORDER BY r.confidence DESC
    """)
    return results


def get_supports() -> list[dict]:
    results = run_query("""
        MATCH (a:Claim)-[r:SUPPORTS]->(b:Claim)
        MATCH (a)-[:EXTRACTED_FROM]->(pa:Paper)
        MATCH (b)-[:EXTRACTED_FROM]->(pb:Paper)
        RETURN elementId(r) AS id,
               r.explanation AS explanation,
               r.confidence AS confidence,
               a.text AS claim_a,
               pa.title AS paper_a,
               b.text AS claim_b,
               pb.title AS paper_b
        ORDER BY r.confidence DESC
    """)
    return results


# ─────────────────────────────────────────────────────────────
# Gaps
# ─────────────────────────────────────────────────────────────

def insert_gap(text: str, source: str, related_claim_ids: list[str],
               confidence: float | None = None) -> str | None:
    """
    Insert a research gap and link it to related claims.

    ``confidence`` is the generating model's self-reported score, stored so the
    UI can show it as a model score rather than an uncalibrated fact. It is
    optional because the future-work prompt does not ask for one.
    Returns the Neo4j element id.
    """
    result = run_write("""
        CREATE (g:Gap {text: $text, source: $source, confidence: $confidence})
        SET g.gap_id = elementId(g)
        RETURN elementId(g) AS gap_id
    """, {"text": text, "source": source, "confidence": confidence})

    gap_id = result[0]["gap_id"] if result else None

    if gap_id and related_claim_ids:
        for cid in related_claim_ids:
            run_write("""
                MATCH (g:Gap) WHERE elementId(g) = $gap_id
                MATCH (c:Claim) WHERE elementId(c) = $claim_id
                MERGE (g)-[:RELATED_TO]->(c)
            """, {"gap_id": gap_id, "claim_id": cid})

    return gap_id


def get_gaps() -> list[dict]:
    """
    Returns all gaps with their related claim IDs and stored model score.
    """
    results = run_query("""
        MATCH (g:Gap)
        OPTIONAL MATCH (g)-[:RELATED_TO]->(c:Claim)
        RETURN elementId(g) AS id, g.text AS text, g.source AS source,
               g.confidence AS confidence,
               collect(elementId(c)) AS related_claims
    """)
    return results


def get_claim_references(claim_ids: list[str]) -> dict[str, dict]:
    """Look up display/provenance data for related-claim IDs in one query.

    Missing or stale IDs simply do not appear in the returned mapping; callers
    must keep the raw ID as a fallback instead of inventing claim text.
    """
    ids = [str(cid) for cid in claim_ids if cid]
    if not ids:
        return {}

    rows = run_query("""
        MATCH (c:Claim)-[:EXTRACTED_FROM]->(p:Paper)
        WHERE elementId(c) IN $claim_ids
        RETURN elementId(c) AS id,
               c.text AS text,
               c.section AS section,
               c.confidence AS confidence,
               p.arxiv_id AS arxiv_id,
               p.title AS paper_title
    """, {"claim_ids": ids})
    return {str(row["id"]): row for row in rows if row.get("id")}


# ─────────────────────────────────────────────────────────────
# Graph stats
# ─────────────────────────────────────────────────────────────

def get_graph_stats() -> dict:
    # COUNT {} subqueries always return a single row — no aggregation pitfalls,
    # unlike chained `MATCH ... WITH count(...)`, which yields zero rows when any
    # label/relationship has 0 entries.
    result = run_query("""
        RETURN COUNT { MATCH (p:Paper) }               AS papers,
               COUNT { MATCH (c:Claim) }               AS claims,
               COUNT { MATCH ()-[:CONTRADICTS]->() }   AS contradictions,
               COUNT { MATCH (g:Gap) }                 AS gaps
    """)
    if result:
        return result[0]
    return {"papers": 0, "claims": 0, "contradictions": 0, "gaps": 0}
# graph/migrate_to_neo4j.py
"""
One-time migration: SQLite → Neo4j.
Reads all papers, claims, relationships, and gaps from SQLite.
Writes them to Neo4j as a property graph.

Safe to run multiple times — uses MERGE so no duplicates.

Run: python -m graph.migrate_to_neo4j
"""
import sqlite3
from config import DB_PATH
from graph.neo4j_client import run_write
from graph.neo4j_schema import init_neo4j


def get_sqlite_conn():
    return sqlite3.connect(str(DB_PATH))


def migrate_papers(conn):
    print("\n[1/4] Migrating papers...")
    rows = conn.execute("""
        SELECT id, arxiv_id, title, authors, abstract, published
        FROM papers
    """).fetchall()

    for row in rows:
        paper_id, arxiv_id, title, authors, abstract, published = row
        year = None
        if published and len(published) >= 4:
            try:
                year = int(published[:4])
            except ValueError:
                pass

        run_write("""
            MERGE (p:Paper {arxiv_id: $arxiv_id})
            SET p.sqlite_id = $sqlite_id,
                p.title = $title,
                p.authors = $authors,
                p.abstract = $abstract,
                p.published = $published,
                p.year = $year
        """, {
            "arxiv_id": arxiv_id,
            "sqlite_id": paper_id,
            "title": title or "",
            "authors": authors or "",
            "abstract": abstract or "",
            "published": published or "",
            "year": year
        })

    print(f"  Migrated {len(rows)} papers.")


def migrate_claims(conn):
    print("\n[2/4] Migrating claims...")
    rows = conn.execute("""
        SELECT cl.id, cl.claim_text, cl.section, cl.confidence,
               cl.embedding_id, cl.paper_year, p.arxiv_id
        FROM claims cl
        JOIN papers p ON cl.paper_id = p.id
    """).fetchall()

    for row in rows:
        claim_id, text, section, confidence, embedding_id, paper_year, arxiv_id = row

        run_write("""
            MERGE (c:Claim {claim_id: $claim_id})
            SET c.text = $text,
                c.section = $section,
                c.confidence = $confidence,
                c.embedding_id = $embedding_id,
                c.paper_year = $paper_year
            WITH c
            MATCH (p:Paper {arxiv_id: $arxiv_id})
            MERGE (c)-[:EXTRACTED_FROM]->(p)
        """, {
            "claim_id": claim_id,
            "text": text or "",
            "section": section or "",
            "confidence": confidence or 1.0,
            "embedding_id": embedding_id or "",
            "paper_year": paper_year,
            "arxiv_id": arxiv_id
        })

    print(f"  Migrated {len(rows)} claims.")


def migrate_relationships(conn):
    print("\n[3/4] Migrating relationships...")
    rows = conn.execute("""
        SELECT r.id, r.claim_a_id, r.claim_b_id, r.rel_type,
               r.explanation, r.confidence
        FROM relationships r
    """).fetchall()

    contradicts = 0
    supports = 0

    for row in rows:
        rel_id, claim_a_id, claim_b_id, rel_type, explanation, confidence = row

        if rel_type == "CONTRADICTS":
            run_write("""
                MATCH (a:Claim {claim_id: $claim_a_id})
                MATCH (b:Claim {claim_id: $claim_b_id})
                MERGE (a)-[r:CONTRADICTS]->(b)
                SET r.explanation = $explanation,
                    r.confidence = $confidence,
                    r.sqlite_id = $rel_id
            """, {
                "claim_a_id": claim_a_id,
                "claim_b_id": claim_b_id,
                "explanation": explanation or "",
                "confidence": confidence or 0.0,
                "rel_id": rel_id
            })
            contradicts += 1
        elif rel_type == "SUPPORTS":
            run_write("""
                MATCH (a:Claim {claim_id: $claim_a_id})
                MATCH (b:Claim {claim_id: $claim_b_id})
                MERGE (a)-[r:SUPPORTS]->(b)
                SET r.explanation = $explanation,
                    r.confidence = $confidence,
                    r.sqlite_id = $rel_id
            """, {
                "claim_a_id": claim_a_id,
                "claim_b_id": claim_b_id,
                "explanation": explanation or "",
                "confidence": confidence or 0.0,
                "rel_id": rel_id
            })
            supports += 1

    print(f"  Migrated {contradicts} CONTRADICTS, {supports} SUPPORTS relationships.")


def migrate_gaps(conn):
    print("\n[4/4] Migrating gaps...")
    rows = conn.execute(
        "SELECT id, gap_text, related_claim_ids FROM gaps"
    ).fetchall()
    for row in rows:
        gap_id, text, related_claim_ids_str = row
        run_write("""
            MERGE (g:Gap {gap_id: $gap_id})
            SET g.text = $text, g.source = 'sqlite_migration'
        """, {"gap_id": gap_id, "text": text or ""})
        if related_claim_ids_str:
            try:
                claim_ids = json.loads(related_claim_ids_str)
                for cid in claim_ids:
                    run_write("""
                        MATCH (g:Gap {gap_id: $gap_id})
                        MATCH (c:Claim {claim_id: $claim_id})
                        MERGE (g)-[:RELATED_TO]->(c)
                    """, {"gap_id": gap_id, "claim_id": cid})
            except Exception:
                pass
    print(f"  Migrated {len(rows)} gaps.")

def verify(conn):
    print("\n[Verify] Checking migration...")
    from graph.neo4j_client import run_query

    sqlite_papers = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    sqlite_claims = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    sqlite_rels = conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
    sqlite_gaps = conn.execute("SELECT COUNT(*) FROM gaps").fetchone()[0]

    neo4j_papers = run_query("MATCH (p:Paper) RETURN count(p) AS n")[0]["n"]
    neo4j_claims = run_query("MATCH (c:Claim) RETURN count(c) AS n")[0]["n"]
    neo4j_rels = run_query("MATCH ()-[r:CONTRADICTS|SUPPORTS]->() RETURN count(r) AS n")[0]["n"]
    neo4j_gaps = run_query("MATCH (g:Gap) RETURN count(g) AS n")[0]["n"]

    print(f"  Papers:        SQLite={sqlite_papers}  Neo4j={neo4j_papers}  {'OK' if sqlite_papers == neo4j_papers else 'MISMATCH'}")
    print(f"  Claims:        SQLite={sqlite_claims}  Neo4j={neo4j_claims}  {'OK' if sqlite_claims == neo4j_claims else 'MISMATCH'}")
    print(f"  Relationships: SQLite={sqlite_rels}  Neo4j={neo4j_rels}  {'OK' if sqlite_rels == neo4j_rels else 'MISMATCH'}")
    print(f"  Gaps:          SQLite={sqlite_gaps}  Neo4j={neo4j_gaps}  {'OK' if sqlite_gaps == neo4j_gaps else 'MISMATCH'}")


def run():
    print("=" * 60)
    print("Axion — SQLite to Neo4j Migration")
    print("=" * 60)

    init_neo4j()

    conn = get_sqlite_conn()
    try:
        migrate_papers(conn)
        migrate_claims(conn)
        migrate_relationships(conn)
        migrate_gaps(conn)
        verify(conn)
    finally:
        conn.close()

    print("\nMigration complete.")
    print("SQLite file preserved at data/db/axion.db as backup.")
    print("You can now update config.py to use Neo4j exclusively.")


if __name__ == "__main__":
    run()
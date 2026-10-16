"""
Offline unit tests for the ingestion utilities.

Covers the pieces that had no test coverage at all:
  * `ingestion.pdf_parser.chunk_text` (overlap / whitespace handling)
  * `ingestion.pdf_parser.extract_sections` (header splitting)
  * `ingestion.progress.IngestionProgressTracker` (state machine + logs)

No network, no Neo4j, no ChromaDB — safe for CI.
"""
from pathlib import Path

from config import CHUNK_OVERLAP, CHUNK_SIZE
from ingestion.pdf_parser import chunk_text, extract_sections
from ingestion.progress import IngestionProgressTracker


# ─── chunk_text ───────────────────────────────────────────────────────────────

class TestChunkText:

    def test_empty_text_yields_no_chunks(self):
        assert chunk_text("") == []

    def test_short_text_is_a_single_chunk(self):
        chunks = chunk_text("hello world")
        assert chunks == ["hello world"]

    def test_chunks_overlap_by_configured_amount(self):
        text = "".join(str(i % 10) for i in range(2000))
        chunks = chunk_text(text)

        assert len(chunks) >= 2
        assert chunks[0] == text[:CHUNK_SIZE]
        # the tail of chunk N is the head of chunk N+1
        assert chunks[1][:CHUNK_OVERLAP] == chunks[0][-CHUNK_OVERLAP:]

    def test_whitespace_only_text_is_dropped(self):
        assert chunk_text(" " * 2000) == []


# ─── extract_sections ─────────────────────────────────────────────────────────

class TestExtractSections:

    def test_splits_on_known_section_headers(self, monkeypatch):
        import ingestion.pdf_parser as parser

        synthetic = (
            "A Study of Things\n"
            "Abstract\n"
            "We study things.\n"
            "Introduction\n"
            "Things matter.\n"
            "Method\n"
            "We did things.\n"
            "Conclusion\n"
            "Things are done.\n"
        )
        monkeypatch.setattr(parser, "extract_text", lambda _path: synthetic)

        sections = parser.extract_sections(Path("ignored.pdf"))

        assert set(sections) == {"preamble", "Abstract", "Introduction", "Method", "Conclusion"}
        assert "We study things." in sections["Abstract"]
        assert "We did things." in sections["Method"]
        assert "Things are done." in sections["Conclusion"]


# ─── IngestionProgressTracker ─────────────────────────────────────────────────

class TestProgressTracker:

    def test_starts_idle(self):
        p = IngestionProgressTracker().get_progress()
        assert p["status"] == "idle"
        assert p["running"] is False
        assert p["percent"] == 0

    def test_start_sets_searching(self):
        t = IngestionProgressTracker()
        t.start("chain of thought", 3)
        p = t.get_progress()

        assert p["status"] == "searching"
        assert p["topic"] == "chain of thought"
        assert p["limit"] == 3
        assert p["running"] is True
        assert p["percent"] == 10
        assert p["remaining_seconds"] == 30

    def test_processing_percentage_and_remaining_time(self):
        t = IngestionProgressTracker()
        t.start("topic", 4)
        t.update_status("processing", "Downloading")
        t.start_paper(2, "2401.00001", "A title")

        p = t.get_progress()
        # (2-1)/4 = 0.25 -> int(15 + 0.25*65) = 31
        assert p["percent"] == 31
        # no papers finished yet -> default 35s/paper + 15s overhead
        assert p["remaining_seconds"] == 35 * 4 + 15

    def test_finish_paper_accumulates_counters(self):
        t = IngestionProgressTracker()
        t.start("topic", 3)
        t.update_status("processing")
        t.start_paper(1, "2401.1", "T")
        t.finish_paper(2.0, 5)

        p = t.get_progress()
        assert p["papers_added"] == 1
        assert p["claims_added"] == 5

    def test_complete_marks_done(self):
        t = IngestionProgressTracker()
        t.start("topic", 1)
        t.complete(7)

        p = t.get_progress()
        assert p["status"] == "completed"
        assert p["percent"] == 100
        assert p["running"] is False
        assert p["contradictions_found"] == 7

    def test_fail_marks_failed(self):
        t = IngestionProgressTracker()
        t.start("topic", 1)
        t.fail("kaboom")

        p = t.get_progress()
        assert p["status"] == "failed"
        assert p["percent"] == 0
        assert p["running"] is False
        assert p["error_message"] == "kaboom"

    def test_restart_resets_counters(self):
        t = IngestionProgressTracker()
        t.start("first", 1)
        t.update_status("processing")
        t.start_paper(1, "2401.1", "T")
        t.finish_paper(1.0, 3)

        t.start("second", 2)
        p = t.get_progress()
        assert p["topic"] == "second"
        assert p["papers_added"] == 0
        assert p["claims_added"] == 0
        assert p["status"] == "searching"

    def test_log_buffer_is_capped(self):
        t = IngestionProgressTracker()
        for i in range(250):
            t.add_log(f"message {i}")
        assert len(t.get_progress()["logs"]) == 200

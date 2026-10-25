"""Canonical research-gap source taxonomy.

Gap extraction has two real workflows in this codebase:

* ``cluster`` — a question inferred from a cluster of related claims.
* ``future_work`` — a question mined from a paper's future-work/limitations text.

Older corpora also contain values that do not identify one of those workflows.
We keep those records visible instead of silently relabelling them:

* ``legacy_import`` — imported by the SQLite → Neo4j migration.
* ``unknown`` — any other/missing source.

The API normalises the raw graph property at this boundary. The graph itself
keeps the provenance value written at ingestion time.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

CANONICAL_GAP_SOURCES: tuple[str, ...] = (
    "cluster",
    "future_work",
    "legacy_import",
    "unknown",
)

SOURCE_LABELS: dict[str, str] = {
    "cluster": "Cluster-derived",
    "future_work": "Future work",
    "legacy_import": "Legacy import",
    "unknown": "Unclassified",
}

SOURCE_DESCRIPTIONS: dict[str, str] = {
    "cluster": "Inferred from a cluster of related claims.",
    "future_work": "Mined from an explicit future-work or limitations statement.",
    "legacy_import": (
        "Imported from the pre-Neo4j corpus; the original extraction workflow "
        "was not recorded."
    ),
    "unknown": (
        "The stored source value does not identify a supported extraction "
        "workflow."
    ),
}

# Only aliases whose meaning is explicit in the stored value are accepted.
# Deliberately do not map "semantic" or "llm_synthesized": those older UI labels
# do not say which extraction workflow produced a record.
ALIASES: dict[str, str] = {
    "sqlite_migration": "legacy_import",
    "legacy": "legacy_import",
    "legacy_import": "legacy_import",
}

# Sources a client may ask for. Raw graph values are intentionally not part of
# the public filter vocabulary; they are normalised before filtering.
FILTER_SOURCES: tuple[str, ...] = CANONICAL_GAP_SOURCES


def normalize_gap_source(raw: object) -> str:
    """Return one canonical source for a raw stored value.

    Unknown and missing values are represented honestly as ``unknown`` rather
    than being guessed to be cluster- or future-work-derived.
    """
    if raw is None:
        return "unknown"
    value = str(raw).strip().lower()
    if value in CANONICAL_GAP_SOURCES:
        return value
    return ALIASES.get(value, "unknown")


def source_label(source: str) -> str:
    return SOURCE_LABELS.get(source, SOURCE_LABELS["unknown"])


def source_description(source: str) -> str:
    return SOURCE_DESCRIPTIONS.get(source, SOURCE_DESCRIPTIONS["unknown"])


def count_gap_sources(gaps: Iterable[Mapping[str, object]]) -> dict[str, int]:
    """Count all gaps by canonical source, plus the corpus total."""
    counts = {"all": 0}
    counts.update({source: 0 for source in CANONICAL_GAP_SOURCES})
    for gap in gaps:
        counts["all"] += 1
        counts[normalize_gap_source(gap.get("source"))] += 1
    return counts

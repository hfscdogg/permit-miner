"""
segmentation.py — Permit classification for audience-targeted postcards.

Produces three things from a raw permit dict:
  - tags:    JSON-serializable list of canonical keywords present in the permit
             (pulled from config.QUALIFYING_TAGS). Stored on permits.permit_tags.
  - segment: One of {"new_construction","major_remodel","kitchen_bath",
             "outdoor_living","default"}. Drives Lob template selection.
  - value_tier: "mid" | "high" | "luxury". Passed to Lob as a merge variable
             so templates can adjust headline / CTA per audience.
"""
from __future__ import annotations

import json

import config


# Segment priority — first match wins when a permit triggers multiple buckets.
SEGMENT_PRIORITY = (
    "new_construction",
    "major_remodel",
    "kitchen_bath",
    "outdoor_living",
)

# Tag → segment mapping. Tags are matched lowercase against permit text.
SEGMENT_TAG_MAP: dict[str, tuple[str, ...]] = {
    "new_construction": ("new_construction", "new construction", "single family"),
    "major_remodel":    ("addition", "renovation", "remodel", "master suite", "master bedroom"),
    "kitchen_bath":     ("kitchen", "bathroom"),
    "outdoor_living":   ("pool", "deck", "patio", "outdoor kitchen", "detached garage"),
}


def classify_permit(description: str, permit_type: str, is_new_construction: bool) -> list[str]:
    """Return the canonical qualifying tags present in the permit text.

    Tags come from config.QUALIFYING_TAGS. is_new_construction forces the
    "new_construction" tag on when the flag is set, even if the keyword
    isn't in the description (some scrapers infer new-build from permit_type).
    """
    text = f"{permit_type or ''} {description or ''}".lower()
    tags: list[str] = []
    for tag in config.QUALIFYING_TAGS:
        if tag in text and tag not in tags:
            tags.append(tag)
    if is_new_construction and "new_construction" not in tags:
        tags.insert(0, "new_construction")
    return tags


def resolve_segment(tags: list[str], is_new_construction: bool) -> str:
    """Collapse a tag list to a single segment id using SEGMENT_PRIORITY."""
    if is_new_construction:
        return "new_construction"
    tag_set = {t.lower() for t in (tags or [])}
    for segment in SEGMENT_PRIORITY:
        for keyword in SEGMENT_TAG_MAP[segment]:
            if keyword in tag_set:
                return segment
    return "default"


def resolve_value_tier(job_value_cents: int | None, assessed_value_cents: int | None) -> str:
    """Derive a coarse value tier for merge-variable targeting.

    Assessed value is divided by ~10 so a $1.5M home reads similarly to a
    $150K project — both signal premium work.
    """
    job = int(job_value_cents or 0) // 100
    assessed = int(assessed_value_cents or 0) // 100
    score = max(job, assessed // 10)
    if score >= 500_000:
        return "luxury"
    if score >= 150_000:
        return "high"
    return "mid"


def tags_to_json(tags: list[str]) -> str:
    return json.dumps(tags, separators=(",", ":"))


def tags_from_json(raw: str | None) -> list[str]:
    """Parse the permit_tags column. Tolerates legacy rows where the column
    was populated with the raw description string instead of JSON."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(t) for t in parsed]
    except (json.JSONDecodeError, TypeError):
        pass
    return []

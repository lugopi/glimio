"""Shared identifiers for supported summary output formats."""

# Keep the set of selectable formats in one place so CLI, Web validation and the
# summary workflow cannot silently disagree. ``auto`` is a request mode; it is
# resolved to one of the concrete formats before drafting starts.
REPORT_FORMATS: tuple[str, ...] = (
    "auto",
    "summary",
    "narrative",
    "dialogue",
    "learning",
    "daily",
    "technical",
    "formal",
    "brainstorm",
)

CLASSIFIABLE_REPORT_FORMATS: tuple[str, ...] = tuple(
    report_format for report_format in REPORT_FORMATS if report_format != "auto"
)

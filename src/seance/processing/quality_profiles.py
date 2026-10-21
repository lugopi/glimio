"""User-facing processing profiles mapped to concrete LLM generation budgets."""
from __future__ import annotations

from typing import Any


PROCESSING_PROFILES: dict[str, dict[str, Any]] = {
    "turbo": {
        "max_tokens": 3500,
        "analysis_tokens": 1800,
        "analysis_retries": 1,
        "analysis_max_splits": 2,
        "no_review": True,
    },
    "balanced": {
        "max_tokens": 6000,
        "analysis_tokens": 3500,
        "analysis_retries": 3,
        "analysis_max_splits": 6,
        "no_review": False,
    },
    "quality": {
        "max_tokens": 8000,
        "analysis_tokens": 5500,
        "analysis_retries": 4,
        "analysis_max_splits": 8,
        "no_review": False,
    },
    "pixel-perfect": {
        "max_tokens": 12000,
        "analysis_tokens": 8000,
        "analysis_retries": 5,
        "analysis_max_splits": 10,
        "no_review": False,
    },
    "custom": {},
}


PROFILE_GENERATION_SETTINGS = {
    profile: dict(values) for profile, values in PROCESSING_PROFILES.items()
}


def apply_processing_profile(settings: dict[str, Any]) -> dict[str, Any]:
    """Return settings with the selected profile's generation budgets applied."""
    profile = str(settings.get("processing_profile", "balanced"))
    if profile not in PROCESSING_PROFILES:
        raise ValueError(f"Profil de traitement inconnu : {profile}")
    return {**settings, **PROCESSING_PROFILES[profile]}

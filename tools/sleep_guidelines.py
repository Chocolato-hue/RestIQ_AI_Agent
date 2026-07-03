"""
Compatibility wrapper for tools.sleep_guidelines namespace.
Redirects everything to tools.sleep_guideline.
"""

from tools.sleep_guideline import (
    SleepGuideline,
    SOURCE_CITATION,
    get_recommended_hours,
    evaluate_duration_against_guideline,
    fetch_source_verification,
)

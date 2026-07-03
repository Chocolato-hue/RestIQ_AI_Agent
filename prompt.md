## ✅ Yes — Add This to Your `prompt.md` File

This is a great idea. Storing the prompt in a `.md` file saves tokens and gives you a reusable reference. Here's how to structure it:

---

### 📁 File: `prompt.md`

```markdown
# RestIQ Sleep Guidelines Integration — Implementation Prompt

## Overview
Integrate `tools/sleep_guidelines.py` (CDC/AASM-based age recommendations) into the conversation flow, Intake Agent, Analyzer Agent, and database.

---

## 1. Conversation Flow (Streamlit) — Ask for Age Naturally

**Goal:** Collect numeric age in a conversational way using structured inputs.

### Tone Options (Choose One)
- **Friendly:** "Before we continue, could you tell me how old you are? Just the number is fine."
- **Casual:** "Just a quick question — how old are you?"
- **Gentle:** "If you don't mind me asking, what's your age?"
- **Parent:** "What's the child's age in years? (0.5 for six months)"

### Streamlit UI Snippet
```python
# streamlit_app.py
import streamlit as st

with st.form("intake_form"):
    st.markdown("### Tell us about yourself")
    age_years = st.number_input(
        "How old are you? (years)",
        min_value=0.0,
        max_value=130.0,
        value=25.0,
        step=0.1,
        help="Enter years (0.5 for 6 months)."
    )
    avg_hours = st.number_input(
        "Average sleep per night (hours)",
        min_value=0.0,
        max_value=24.0,
        value=7.5,
        step=0.25
    )
    submitted = st.form_submit_button("Continue")

if submitted:
    intake_event = {"age_years": float(age_years), "avg_hours": float(avg_hours)}
```

### Validation & Edge Cases
- If user gives a range or ambiguous input → confirm: *"I heard X years — is that right?"*
- If user does not answer → ask once more, then proceed with default or skip.
- If age < 0 or > 130 → show validation error: *"That age looks off — could you check?"*

---

## 2. Intake Agent — Prompt + Behavior

**Goal:** Collect/validate age and average sleep, call `get_recommended_hours()`.

### System Prompt
```
You are the Intake Agent. Your job: collect required structured fields from the user (age_years, avg_hours) and validate them. Ask only the minimal clarifying questions needed. Use numeric checks. Do NOT call any external network on import.

If provided age and sleep average, call sleep_guidelines.get_recommended_hours(age_years) to determine the correct age band, and return a structured payload:
{
    "age_years": float,
    "avg_hours": float,
    "age_band": str,
    "recommended_min_hours": float,
    "recommended_max_hours": float,
    "source": str
}
```

### Behavior Pseudocode
```python
# agents/intake.py
from tools.sleep_guidelines import get_recommended_hours

def handle_intake_message(user_id: str, message: str, context: dict):
    # If age missing → ask with one of the tone options above.
    # If age provided → parse float, validate 0 <= age <= 130.
    # If avg_hours missing → ask for it.
    # If both present → call get_recommended_hours(age_years).
    guideline = get_recommended_hours(age_years)
    return {
        "age_years": age_years,
        "avg_hours": avg_hours,
        "age_band": guideline.label,
        "recommended_min_hours": guideline.min_hours,
        "recommended_max_hours": guideline.max_hours,
        "source": SOURCE_CITATION
    }
```

### Example Reply to User
*"Thanks — for a 25-year-old, the recommended sleep is 7–9 hours per night. Got it — I'll include that in your record."*

---

## 3. Analyzer Agent — Prompt + Behavior

**Goal:** Call `evaluate_duration_against_guideline()` and produce structured assessment + recommendation.

### System Prompt
```
You are the Analyzer Agent. For each user intake you receive, run the domain-specific check(s), and produce:
1. A structured assessment record for storage.
2. One concise, empathetic, human-facing recommendation sentence.

Use tools from tools.sleep_guidelines to compare avg_hours vs recommended range.
Use VerdictLabel values but serialize to a string for DB storage.
Provide action-oriented suggestions only when appropriate (e.g., if NEEDS_ATTENTION: recommend sleep hygiene tips or suggest consulting a provider if severe).
```

### Behavior Pseudocode
```python
# tools/analyzer.py
from tools.sleep_guidelines import evaluate_duration_against_guideline

def analyze_sleep(intake_record: dict) -> dict:
    assessment = evaluate_duration_against_guideline(
        age_years=intake_record["age_years"],
        average_duration_hours=intake_record["avg_hours"],
    )

    verdict_serial = assessment["verdict"].value if hasattr(assessment["verdict"], "value") else str(assessment["verdict"])

    if verdict_serial == "ON_TRACK":
        summary = f"You're on track: {assessment['note']}"
    elif verdict_serial == "NEEDS_ATTENTION":
        summary = f"Looks like your sleep may be low: {assessment['note']} Consider a consistent bedtime routine and speak with a clinician if this persists."
    else:
        summary = f"You're getting more sleep than recommended: {assessment['note']} If it's due to daytime sleepiness, that may warrant evaluation."

    return {
        "db_assessment": {
            "age_years": intake_record["age_years"],
            "avg_hours": intake_record["avg_hours"],
            "age_band": assessment["age_band"],
            "recommended_min_hours": assessment["recommended_min_hours"],
            "recommended_max_hours": assessment["recommended_max_hours"],
            "within_range": assessment["within_range"],
            "verdict": verdict_serial,
            "note": assessment["note"],
            "source": assessment["source"],
            "analyzed_at": "2026-07-03T12:34:56Z"
        },
        "user_message": summary
    }
```

### Tips
- Analyzer should NOT re-ask age; rely on Intake/DB as source of truth.
- Always convert `VerdictLabel` to a stable string before storing or returning JSON.

---

## 4. Database Schema & Migration

**Goal:** Store intake and analyzer outputs for auditing and future features.

### Migration (SQLite)
```sql
-- db/migrations/001_add_age_to_users.sql
ALTER TABLE users ADD COLUMN age INTEGER;

-- Create sleep_assessments table
CREATE TABLE IF NOT EXISTS sleep_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    age_years REAL,
    avg_hours REAL,
    age_band TEXT,
    recommended_min_hours REAL,
    recommended_max_hours REAL,
    within_range INTEGER,  -- 0 or 1 (boolean)
    verdict TEXT,          -- ON_TRACK / NEEDS_ATTENTION / IMPROVING
    note TEXT,
    source TEXT,
    analyzed_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (user_id)
);

CREATE INDEX idx_sleep_assessments_analyzed_at ON sleep_assessments(analyzed_at);
```

### Example Insert
```python
# tools/storage.py
def store_sleep_assessment(assessment: dict) -> None:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sleep_assessments (
            user_id, age_years, avg_hours, age_band,
            recommended_min_hours, recommended_max_hours,
            within_range, verdict, note, source, analyzed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        assessment["user_id"],
        assessment["age_years"],
        assessment["avg_hours"],
        assessment["age_band"],
        assessment["recommended_min_hours"],
        assessment["recommended_max_hours"],
        assessment["within_range"],
        assessment["verdict"],
        assessment["note"],
        assessment["source"],
        assessment["analyzed_at"]
    ))
    conn.commit()
    conn.close()
```

---

## 5. Additional Notes

| Topic | Recommendation |
|-------|---------------|
| **Network verification** | `fetch_source_verification()` should be opt-in for admin health checks only — never call automatically in Intake/Analyzer. |
| **Tests** | Add unit tests for boundary ages: 0, 0.25, 1, 3, 6, 13, 18, 65, 100. Test negative ages/durations raise `ValueError`. |
| **Serialization** | When creating DB JSON, convert `VerdictLabel` to `.value` or `.name` to ensure JSON compatibility. |
| **UX polish** | Show recommended range immediately after intake. Highlight `within_range` status with colored badge (green/yellow/red). Offer a "Tell me more" button for optional guidance. |

---

## Next Steps

- [ ] Apply migration to add `age` column to `users` table.
- [ ] Create `sleep_assessments` table.
- [ ] Update `tools/profile.py` with `update_user_age()` and `get_user_age()`.
- [ ] Modify `agents/intake.py` to ask for age and call `get_recommended_hours()`.
- [ ] Modify `tools/analyzer.py` to call `evaluate_duration_against_guideline()` and store assessment.
- [ ] Update `streamlit_app.py` with age input form and display age-based insights.
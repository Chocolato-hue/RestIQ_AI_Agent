import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("IntakeAgent")

# Import schemas
from schemas import SleepEntrySchema
from services import intake as intake_service

class IntakeAgent:
    """
    IntakeAgent manages the user check-in flow by receiving raw text,
    routing it to the parse_sleep_input MCP tool, and returning a validated SleepEntrySchema.
    """
    def run(self, user_id: str, raw_text: str) -> SleepEntrySchema:
        logger.info("[INTAKE] Received raw text for user_id '%s': %s", user_id, raw_text)
        
        try:
            entry = intake_service.parse_sleep_input(user_id, raw_text)
            logger.info("[INTAKE] Successfully parsed sleep entry.")
            return entry
        except Exception as e:
            logger.error("[INTAKE] Error during intake processing: %s", str(e), exc_info=True)
            raise ValueError(f"Intake processing failed: {e}") from e


def run_intake(user_id: str, raw_text: str) -> SleepEntrySchema:
    """
    Convenience function to run the IntakeAgent.
    """
    agent = IntakeAgent()
    return agent.run(user_id, raw_text)


if __name__ == "__main__":
    test_input = (
        "I went to bed at 11pm, woke up at 7am, "
        "woke up once during night, slept pretty well, "
        "feeling good this morning, no caffeine after 2, "
        "did a quick workout, had my phone before bed"
    )
    print("\n--- Running IntakeAgent Manual Test ---")
    try:
        result = run_intake(user_id="test_user_123", raw_text=test_input)
        print("\n--- Result SleepEntrySchema ---")
        print(result.model_dump_json(indent=2))
    except Exception as err:
        print(f"\nTest failed with error: {err}")

"""Loads .env and exposes the locked Day-0 decisions (BUILD_PLAN Part II) as constants."""
import os
from dotenv import load_dotenv

load_dotenv()

INVESTIGATOR_PROVIDER = os.getenv("INVESTIGATOR_PROVIDER", "")
INVESTIGATOR_MODEL = os.getenv("INVESTIGATOR_MODEL", "")
INVESTIGATOR_API_KEY = os.getenv("INVESTIGATOR_API_KEY", "")

VERIFIER_PROVIDER = os.getenv("VERIFIER_PROVIDER", "")
VERIFIER_MODEL = os.getenv("VERIFIER_MODEL", "")
VERIFIER_API_KEY = os.getenv("VERIFIER_API_KEY", "")

if INVESTIGATOR_PROVIDER and VERIFIER_PROVIDER and INVESTIGATOR_PROVIDER == VERIFIER_PROVIDER:
    raise RuntimeError(
        "INVESTIGATOR_PROVIDER == VERIFIER_PROVIDER — BUILD_PLAN L3 requires a "
        "different model family for the verifier. This check exists so the "
        "mistake fails loudly at import time, not silently in a rubber-stamped "
        "net-lift number three weeks from now."
    )

AGENT_TEMPERATURE = float(os.getenv("AGENT_TEMPERATURE", "0"))

# BUILD_PLAN L1
RECORD_COUNT = 1000

# BUILD_PLAN L8 — stated policy choice, not empirically optimised. Say so in the doc/demo.
LOSS_RATIO_FALSE_MATCH_TO_FALSE_NEEDS_HUMAN = 50

DB_PATH = os.getenv("SBE_DB_PATH", "./runs/sbe.db")

"""
config.py — Static Permit Miner configuration.
All dynamic / secret values live in .env. This module holds
constants that rarely change and are safe to commit.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Territory ─────────────────────────────────────────────────────────────────
# 11 Richmond-metro ZIP codes. Shovels covers all except Henrico (see below).
ZIP_CODES = [
    "23226", "23229", "23233", "23238",   # West End / Henrico
    "23113", "23114",                      # Chesterfield / Midlothian
    "23059", "23103",                      # Goochland / Short Pump area
    "23831", "23832", "23836",             # Chesterfield south/east
]

# Henrico ZIPs pulled via monthly Excel import (Shovels coverage gap)
HENRICO_ZIPS = ["23229", "23233", "23238"]

# ── Filtering ──────────────────────────────────────────────────────────────────
# Shovels stores assessed value in CENTS. $500K = 50,000,000 cents.
MIN_ASSESSED_VALUE_CENTS = 50_000_000

# Tags that qualify a permit. New-construction tags always bypass value filter.
QUALIFYING_TAGS = [
    "new_construction", "addition", "renovation", "remodel",
    "pool", "deck", "patio", "outdoor_kitchen",
    "kitchen", "bathroom", "master_suite",
    "hvac", "electrical", "plumbing", "solar",
    "adu", "detached_garage",
]

NEW_CONSTRUCTION_TAGS = {"new_construction", "new_build", "new_home"}

# Permit type keywords that signal new construction (fallback if tags absent)
NEW_CONSTRUCTION_TYPE_KEYWORDS = ["new", "single family new", "new construction"]

# ── Exclusion Learning ─────────────────────────────────────────────────────────
# Number of manual exclusions before a contractor is auto-blocklisted
AUTO_BLOCK_THRESHOLD = 3

# ── Drip ──────────────────────────────────────────────────────────────────────
DRIP_DELAY_DAYS = 21          # Days after first send with no scan → second touch
DRIP_MAX_TOUCHES = 2          # Only one follow-up per permit

# ── Shovels API ───────────────────────────────────────────────────────────────
SHOVELS_BASE_URL = "https://api.shovels.ai/v2"
SHOVELS_PAGE_SIZE = 50        # Max per page for /permits/search

# ── Lob API ───────────────────────────────────────────────────────────────────
LOB_BASE_URL = "https://api.lob.com/v1"
POSTCARD_SIZE = "6x11"

# ── Henrico Import ────────────────────────────────────────────────────────────
# URL pattern: swap {MON} = "JAN", {YEAR} = "2026"
HENRICO_EXCEL_URL = "https://www.henrico.us/files/pdf/building/{MON}{YEAR}_BuildingPermit.xlsx"

# Keywords to match in Henrico job descriptions (luxury residential signals)
HENRICO_KEYWORDS = [
    "single family", "new home", "new house", "addition", "renovation",
    "remodel", "pool", "deck", "accessory dwelling",
]

# ── Secrets (from .env) ───────────────────────────────────────────────────────
SHOVELS_API_KEY     = os.getenv("SHOVELS_API_KEY", "")
LOB_LIVE_KEY        = os.getenv("LOB_LIVE_KEY", "")
LOB_TEST_KEY        = os.getenv("LOB_TEST_KEY", "")

SMTP_HOST           = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT           = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER           = os.getenv("SMTP_USER", "")
SMTP_PASS           = os.getenv("SMTP_PASS", "")

PREVIEW_RECIPIENTS  = [e.strip() for e in os.getenv("PREVIEW_RECIPIENTS", "henry@getlivewire.com").split(",") if e.strip()]
DIGEST_RECIPIENTS   = [e.strip() for e in os.getenv("DIGEST_RECIPIENTS", "henry@getlivewire.com,sales@getlivewire.com").split(",") if e.strip()]
ALERT_RECIPIENTS    = [e.strip() for e in os.getenv("ALERT_RECIPIENTS", "henry@getlivewire.com").split(",") if e.strip()]

RETURN_NAME         = os.getenv("RETURN_NAME", "Livewire")
RETURN_ADDRESS      = os.getenv("RETURN_ADDRESS", "4900 W Clay St")
RETURN_CITY         = os.getenv("RETURN_CITY", "Richmond")
RETURN_STATE        = os.getenv("RETURN_STATE", "VA")
RETURN_ZIP          = os.getenv("RETURN_ZIP", "23230")

BASE_URL            = os.getenv("BASE_URL", "http://localhost:8000")
PURL_BASE_URL       = os.getenv("PURL_BASE_URL", "https://getlivewire.com/welcome")

LOB_TEMPLATE_FRONT_ID       = os.getenv("LOB_TEMPLATE_FRONT_ID", "")
LOB_TEMPLATE_BACK_ID        = os.getenv("LOB_TEMPLATE_BACK_ID", "")
LOB_DRIP_TEMPLATE_FRONT_ID  = os.getenv("LOB_DRIP_TEMPLATE_FRONT_ID", "") or LOB_TEMPLATE_FRONT_ID
LOB_DRIP_TEMPLATE_BACK_ID   = os.getenv("LOB_DRIP_TEMPLATE_BACK_ID", "") or LOB_TEMPLATE_BACK_ID

MODE                = os.getenv("MODE", "test")   # "test" | "live"
DB_PATH             = os.getenv("DB_PATH", "permit_miner.db")

# Resolved Lob key based on mode
LOB_API_KEY = LOB_LIVE_KEY if MODE == "live" else LOB_TEST_KEY

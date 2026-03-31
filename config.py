"""
config.py — Static Permit Miner configuration.
All dynamic / secret values live in .env. This module holds
constants that rarely change and are safe to commit.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Territory ─────────────────────────────────────────────────────────────────
# Richmond metro + extended territory ZIPs.
# Organized by county/area — scrapers use these lists to filter results.
ZIP_CODES = [
    # Henrico County (weekly Excel import)
    "23059", "23060", "23229", "23233", "23238",
    # Chesterfield County (Accela ELM scraper)
    "23113", "23114", "23146", "23838",
    # Goochland County (EnerGov scraper)
    "23103", "23129",
    # Powhatan County
    "23120", "23139", "23153",
    # Hanover County
    "23005", "23116",
    # New Kent / James City County
    "23089", "23168", "23188",
    # Williamsburg area
    "23185",
    # Charlottesville metro
    "22901", "22911", "22947",
    # Fredericksburg area
    "22406", "22407", "22553",
]

# Henrico ZIPs — sourced via weekly Excel import (portal scraping not needed)
HENRICO_ZIPS = {"23059", "23060", "23229", "23233", "23238"}

# Chesterfield ZIPs — Accela ELM portal
CHESTERFIELD_ZIPS = {"23113", "23114", "23146", "23838"}

# Goochland ZIPs — EnerGov portal
GOOCHLAND_ZIPS = {"23103", "23129"}

# Powhatan ZIPs
POWHATAN_ZIPS = {"23120", "23139", "23153"}

# Hanover ZIPs
HANOVER_ZIPS = {"23005", "23116"}

# ── Owner type detection ──────────────────────────────────────────────────────
# If any of these patterns appear in owner_name, skip — it's a company/LLC.
COMPANY_PATTERNS = [
    " LLC", " L.L.C", " INC", " CORP", " CORPORATION", " LP ", " L.P.",
    " LLP", " TRUST", " TRUSTEE", " TRUSTEES", " PROPERTIES", " REALTY",
    " HOLDINGS", " INVESTMENTS", " ENTERPRISES", " GROUP ", " ASSOCIATES",
    " PARTNERS", " DEVELOPMENT", " CONSTRUCTION", " BUILDERS", " HOMES",
    " ESTATES", " MANAGEMENT", " SERVICES", " SOLUTIONS", " VENTURES",
    "THE ESTATE OF", "ESTATE OF",
]

# ── Filtering ──────────────────────────────────────────────────────────────────
# Minimum job value in dollars to qualify (when assessed value unavailable).
MIN_JOB_VALUE_DOLLARS = 75_000

# Minimum assessed property value in dollars to qualify.
MIN_ASSESSED_VALUE_DOLLARS = 500_000

# Tags / permit type keywords that qualify a permit.
QUALIFYING_TAGS = [
    "new_construction", "new construction", "addition", "renovation", "remodel",
    "pool", "deck", "patio", "outdoor kitchen",
    "kitchen", "bathroom", "master suite", "master bedroom",
    "hvac", "electrical", "plumbing", "solar",
    "adu", "accessory dwelling", "detached garage",
    "single family", "residential",
]

NEW_CONSTRUCTION_KEYWORDS = [
    "new construction", "new build", "new home", "new house",
    "new single family", "single family new", "sfr new",
]

# ── Exclusion Learning ─────────────────────────────────────────────────────────
AUTO_BLOCK_THRESHOLD = 3

# ── Drip ──────────────────────────────────────────────────────────────────────
DRIP_DELAY_DAYS = 21
DRIP_MAX_TOUCHES = 2

# ── Lob API ───────────────────────────────────────────────────────────────────
LOB_BASE_URL = "https://api.lob.com/v1"
POSTCARD_SIZE = "6x11"

# ── Henrico Import ────────────────────────────────────────────────────────────
HENRICO_EXCEL_URL = "https://www.henrico.us/files/pdf/building/{MON}{YEAR}_BuildingPermit.xlsx"

HENRICO_KEYWORDS = [
    "single family", "new home", "new house", "addition", "renovation",
    "remodel", "pool", "deck", "accessory dwelling",
]

# ── Virginia State CSV ────────────────────────────────────────────────────────
# data.virginia.gov building permit dataset (may cover all counties)
VA_STATE_CSV_URL = "https://data.virginia.gov/api/views/5y87-nuwi/rows.csv?accessType=DOWNLOAD"

# ── WordPress endpoints ────────────────────────────────────────────────────────
WP_BASE_URL = "https://getlivewire.com"
WP_REGISTRY_ENDPOINT = f"{WP_BASE_URL}/wp-json/permit-miner/v1/registry"
WP_EXCLUSIONS_URL = f"{WP_BASE_URL}/wp-content/uploads/permit-miner/exclusions.json"
WP_SCANS_URL = f"{WP_BASE_URL}/wp-content/uploads/permit-miner/scans.json"

# ── Secrets (from .env) ───────────────────────────────────────────────────────
APOLLO_API_KEY          = os.getenv("APOLLO_API_KEY", "")
PERMIT_MINER_API_KEY    = os.getenv("PERMIT_MINER_API_KEY", "")  # shared secret for WP REST endpoint

LOB_LIVE_KEY            = os.getenv("LOB_LIVE_KEY", "")
LOB_TEST_KEY            = os.getenv("LOB_TEST_KEY", "")

SMTP_HOST               = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT               = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER               = os.getenv("SMTP_USER", "")
SMTP_PASS               = os.getenv("SMTP_PASS", "")

PREVIEW_RECIPIENTS      = [e.strip() for e in os.getenv("PREVIEW_RECIPIENTS", "henry@getlivewire.com").split(",") if e.strip()]
DIGEST_RECIPIENTS       = [e.strip() for e in os.getenv("DIGEST_RECIPIENTS", "henry@getlivewire.com,sales@getlivewire.com").split(",") if e.strip()]
ALERT_RECIPIENTS        = [e.strip() for e in os.getenv("ALERT_RECIPIENTS", "henry@getlivewire.com").split(",") if e.strip()]

RETURN_NAME             = os.getenv("RETURN_NAME", "Livewire")
RETURN_ADDRESS          = os.getenv("RETURN_ADDRESS", "4900 W Clay St")
RETURN_CITY             = os.getenv("RETURN_CITY", "Richmond")
RETURN_STATE            = os.getenv("RETURN_STATE", "VA")
RETURN_ZIP              = os.getenv("RETURN_ZIP", "23230")

PURL_BASE_URL           = os.getenv("PURL_BASE_URL", "https://getlivewire.com/welcome")

LOB_TEMPLATE_FRONT_ID       = os.getenv("LOB_TEMPLATE_FRONT_ID", "")
LOB_TEMPLATE_BACK_ID        = os.getenv("LOB_TEMPLATE_BACK_ID", "")
LOB_DRIP_TEMPLATE_FRONT_ID  = os.getenv("LOB_DRIP_TEMPLATE_FRONT_ID", "") or LOB_TEMPLATE_FRONT_ID
LOB_DRIP_TEMPLATE_BACK_ID   = os.getenv("LOB_DRIP_TEMPLATE_BACK_ID", "") or LOB_TEMPLATE_BACK_ID

MODE                    = os.getenv("MODE", "test")   # "test" | "live"
DB_PATH                 = os.getenv("DB_PATH", "permit_miner.db")

# Resolved Lob key based on mode
LOB_API_KEY = LOB_LIVE_KEY if MODE == "live" else LOB_TEST_KEY

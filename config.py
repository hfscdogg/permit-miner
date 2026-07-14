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
MIN_ASSESSED_VALUE_DOLLARS = 750_000

# Project keywords that qualify a permit. Deliberately excludes generic
# tokens like "residential"/"single family" — county permit types (e.g.
# Chesterfield's blanket "Residential Building") would auto-pass every
# record and let maintenance jobs through.
QUALIFYING_TAGS = [
    "new_construction", "new construction", "addition", "renovation", "remodel",
    "pool", "deck", "patio", "porch", "screened", "sunroom",
    "outdoor kitchen", "outdoor living",
    "kitchen", "bathroom", "bath", "master suite", "master bedroom",
    "basement", "rec room", "media room", "theater", "wine cellar", "elevator",
    "adu", "accessory dwelling", "detached garage", "pool house", "guest house",
]

# Maintenance/repair scopes that disqualify a permit even when a project
# keyword also matches (e.g. "replace all deck boards"). New construction
# is checked before this and always passes.
MAINTENANCE_KEYWORDS = [
    "crawl space", "crawlspace", "encapsulat", "repair", "replace",
    "re-roof", "reroof", "roofing", "shingle", "siding",
    "water heater", "foundation", "jack", "waterproof", "insulation",
    "mold", "remediation", "abatement", "carport", "above ground",
    "above-ground", "storage shed", "demolition", "tear off", "gutter",
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

# ── WordPress endpoints ───────────────────────────────────────────────────────
WP_BASE_URL             = os.getenv("WP_BASE_URL", "https://getlivewire.com")

# ── Secrets (from .env) ───────────────────────────────────────────────────────
APOLLO_API_KEY          = os.getenv("APOLLO_API_KEY", "")
PERMIT_MINER_HMAC_SECRET = os.getenv("PERMIT_MINER_HMAC_SECRET", "")  # HMAC secret for signing PURL/exclude URLs

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

# ── Per-permit-type Lob templates ─────────────────────────────────────────────
# Each key maps to a (front_id, back_id) tuple. Selection logic in tuesday_send.py.
LOB_TEMPLATES = {
    "new_construction": (
        os.getenv("LOB_TMPL_NEW_CONSTRUCTION_FRONT", "tmpl_b3c90f49418910b"),
        os.getenv("LOB_TMPL_NEW_CONSTRUCTION_BACK",  "tmpl_8207d53a9874956"),
    ),
    "kitchen_bath": (
        os.getenv("LOB_TMPL_KITCHEN_BATH_FRONT", "tmpl_2d12823f63a7889"),
        os.getenv("LOB_TMPL_KITCHEN_BATH_BACK",  "tmpl_424c156e3b13102"),
    ),
    "outdoor_living": (
        os.getenv("LOB_TMPL_OUTDOOR_LIVING_FRONT", "tmpl_1793ea84d4ba680"),
        os.getenv("LOB_TMPL_OUTDOOR_LIVING_BACK",  "tmpl_8d920e96a06b150"),
    ),
    "major_remodel": (
        os.getenv("LOB_TMPL_MAJOR_REMODEL_FRONT", "tmpl_345eb43a1f6a96f"),
        os.getenv("LOB_TMPL_MAJOR_REMODEL_BACK",  "tmpl_a4eb6a4b0622c88"),
    ),
    "generic": (
        os.getenv("LOB_TMPL_GENERIC_FRONT", "tmpl_efe31a0670c5331"),
        os.getenv("LOB_TMPL_GENERIC_BACK",  "tmpl_8da18f22b097c88"),
    ),
}

MODE                    = os.getenv("MODE", "test")   # "test" | "live"
DB_PATH                 = os.getenv("DB_PATH", "permit_miner.db")

# Resolved Lob key based on mode
LOB_API_KEY = LOB_LIVE_KEY if MODE == "live" else LOB_TEST_KEY

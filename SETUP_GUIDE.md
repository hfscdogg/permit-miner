# Permit Miner — Setup Guide (No-Shovels Edition)

**Stack:** GitHub Actions (scheduled pipelines) + WordPress (HTTP endpoints) + SQLite (committed to repo)

No Railway. No Shovels. No standalone web server.

---

## Prerequisites

- GitHub account with this repo
- WordPress at getlivewire.com (for PHP mu-plugin endpoints)
- Lob account (lob.com) — API keys + postcard templates
- Apollo API key (apollo.io) — contact enrichment
- Gmail App Password for SMTP

---

## Step 1 — WordPress mu-plugin

1. Copy `wordpress/permit-miner.php` to `wp-content/mu-plugins/permit-miner.php` on the server
2. SSH into server and set the API key in `wp-config.php`:
   ```php
   define( 'PERMIT_MINER_API_KEY', 'your_random_32char_secret' );
   ```
3. Flush rewrite rules: WordPress Admin → Settings → Permalinks → Save
4. Verify endpoints:
   ```bash
   curl "https://getlivewire.com/permit-exclude?pid=test&reason=existing_customer"
   # Expected: "Excluded. Close this tab." HTML page

   curl "https://getlivewire.com/permit-scan?pid=test"
   # Expected: {"status":"ok","permit_type":"","is_new_construction":false}
   ```

---

## Step 2 — GitHub repo secrets

In the GitHub repo → Settings → Secrets and variables → Actions, add:

| Secret | Value |
|---|---|
| `APOLLO_API_KEY` | From apollo.io dashboard |
| `PERMIT_MINER_API_KEY` | Same value as set in wp-config.php |
| `LOB_LIVE_KEY` | From lob.com |
| `LOB_TEST_KEY` | From lob.com |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | `henry@getlivewire.com` |
| `SMTP_PASS` | Gmail App Password |
| `PREVIEW_RECIPIENTS` | `henry@getlivewire.com` |
| `DIGEST_RECIPIENTS` | `henry@getlivewire.com,sales@getlivewire.com` |
| `ALERT_RECIPIENTS` | `henry@getlivewire.com` |
| `RETURN_NAME` | `Livewire` |
| `RETURN_ADDRESS` | `4900 W Clay St` |
| `RETURN_CITY` | `Richmond` |
| `RETURN_STATE` | `VA` |
| `RETURN_ZIP` | `23230` |
| `PURL_BASE_URL` | `https://getlivewire.com/welcome` |
| `LOB_TEMPLATE_FRONT_ID` | After Step 3 |
| `LOB_TEMPLATE_BACK_ID` | After Step 3 |
| `MODE` | `test` (change to `live` when ready) |

---

## Step 3 — Lob postcard templates

1. Log in to lob.com → Templates
2. Upload `lob/postcard_front.html` → note Template ID → add as `LOB_TEMPLATE_FRONT_ID` secret
3. Upload `lob/postcard_back.html` → note Template ID → add as `LOB_TEMPLATE_BACK_ID` secret
4. Order a proof → confirm 6x11 layout and merge variable rendering

---

## Step 4 — WordPress PURL landing page

See `purl/elementor_setup.md` for full Elementor instructions. Summary:

1. Create page at `/welcome` in WordPress
2. Build Elementor sections with IDs: `purl-headline`, `purl-subheadline`, `purl-body`, `purl-personalized`
3. Add `purl/purl_script.js` via Custom HTML widget or Code Snippets plugin
4. `WEBHOOK_URL` is already set to `https://getlivewire.com/permit-scan` — no changes needed
5. Test: `getlivewire.com/welcome?pid=test123` — no JS errors, page loads

---

## Step 5 — Test run (dry run)

Run the Monday workflow manually:
1. GitHub repo → Actions → Monday Pull → Run workflow
2. Watch the run logs
3. Check the preview email arrives at henry@getlivewire.com
4. Confirm the DB commit appears in the repo (commit "Monday pull YYYY-MM-DD")

If MODE=test, no Lob postcards will be sent and the preview email will list permits (or log "no permits" on first run with empty territory data).

---

## Step 6 — Go live

1. Change `MODE` secret from `test` to `live` in GitHub repo settings
2. Run Monday pull on a Monday — confirm preview email with real permits
3. Review preview email — click Exclude buttons for any non-qualifying records
4. Tuesday: confirm Tuesday send runs, postcards appear in Lob dashboard
5. Wait for postcard to arrive (3–5 business days) — scan QR code, confirm alert email

---

## Data flow summary

```
GitHub Actions (Monday):
  1. Checkout repo (includes permit_miner.db + data/scans.json)
  2. Read data/scans.json → mark Engaged in DB
  3. Read data/exclusions.json → mark Excluded in DB
  4. Pull county portals + Virginia state CSV
  5. Filter → Apollo enrich → insert Queued
  6. Write data/permit_registry.json
  7. Send preview email (Exclude links → getlivewire.com/permit-exclude?...)
  8. Commit permit_miner.db + data/permit_registry.json

WordPress (real-time):
  GET /permit-exclude?pid=xxx&reason=yyy → writes exclusions.json
  GET /permit-scan?pid=xxx → sends wp_mail() alert, writes scans.json

GitHub Actions (Tuesday):
  1. Checkout repo
  2. Fetch exclusions.json from WordPress → mark Excluded
  3. Send Lob postcards for Queued records
  4. POST registry to WordPress /wp-json/permit-miner/v1/registry
  5. Write data/permit_registry.json
  6. Send digest email
  7. Commit permit_miner.db + data/permit_registry.json
```

---

## File structure

```
permit-miner/
  config.py               # ZIP codes, filtering thresholds, Apollo/WP URLs
  db.py                   # SQLite schema + helpers + JSON file helpers
  .env.example            # Environment variable template
  requirements.txt        # Python dependencies
  permit_miner.db         # SQLite database (committed, updated by Actions)
  data/
    permit_registry.json  # {pid: {owner, phone, address, type}} — WordPress reads this
    exclusions.json       # [{pid, reason, timestamp}] — WordPress writes, Actions reads
    scans.json            # [{pid, timestamp}] — WordPress writes, Actions reads
  pipeline/
    monday_pull.py        # County scrapers + Apollo + preview email
    tuesday_send.py       # Lob send + WordPress registry push + digest email
    henrico_import.py     # Monthly Henrico County Excel import
    monthly_report.py     # Monthly learning report
    mailer.py             # Shared SMTP email sender
    scrapers/
      virginia_state.py   # data.virginia.gov CSV (primary fallback)
      chesterfield.py     # Accela ACA portal scraper
      goochland.py        # EnerGov portal scraper
      powhatan.py         # Stub (VA state CSV fallback)
      hanover.py          # Stub (VA state CSV fallback)
      assessor.py         # ArcGIS assessed value lookup
  wordpress/
    permit-miner.php      # mu-plugin: /permit-exclude, /permit-scan, /wp-json/registry
  lob/
    postcard_front.html   # 6x11 Lob front template
    postcard_back.html    # 6x11 Lob back template
  purl/
    purl_script.js        # WordPress PURL page JS (WEBHOOK_URL already set)
    elementor_setup.md    # WordPress/Elementor page build guide
  .github/workflows/
    monday_pull.yml       # Cron: 0 13 * * 1
    tuesday_send.yml      # Cron: 0 13 * * 2
    henrico_import.yml    # Cron: 0 13 5 * *
    monthly_report.yml    # Cron: 0 14 1 * *
  SETUP_GUIDE.md          # This file
  TEST_PROTOCOL.md        # 18-step validation checklist
```

---

## Scheduling (automatic once repo is on GitHub)

```
Monday    8:00 AM ET   Monday Pull workflow
Tuesday   8:00 AM ET   Tuesday Send workflow
5th/month 8:00 AM ET   Henrico Import workflow
1st/month 9:00 AM ET   Monthly Report workflow
```

All four workflows can also be triggered manually via Actions → Run workflow.

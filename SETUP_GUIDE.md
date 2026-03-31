# Permit Miner — Setup Guide

Standalone Python/SQLite stack. No Zoho. No n8n.

---

## Prerequisites

- Python 3.11+
- A server or VPS reachable from the internet (for Exclude buttons + PURL scan tracking)
- Shovels API key (obtain from shovels.ai)
- Lob account with API keys (lob.com) — postcard templates uploaded (see Step 5)
- SMTP credentials for outbound email (Gmail App Password works)
- WordPress site at getlivewire.com for the PURL landing page

---

## Step 1 — Clone repo and install dependencies

```bash
git clone <repo-url> permit-miner
cd permit-miner
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## Step 2 — Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in all values:

| Variable | Description |
|---|---|
| `SHOVELS_API_KEY` | From shovels.ai dashboard |
| `LOB_LIVE_KEY` / `LOB_TEST_KEY` | From lob.com dashboard |
| `SMTP_HOST/PORT/USER/PASS` | Outbound email credentials |
| `PREVIEW_RECIPIENTS` | Monday preview email — Henry's address |
| `DIGEST_RECIPIENTS` | Tuesday digest — Henry + sales |
| `ALERT_RECIPIENTS` | QR scan alerts |
| `RETURN_*` | Livewire return address for postcards |
| `BASE_URL` | Public URL of the FastAPI server (e.g. `https://permits.getlivewire.com`) |
| `PURL_BASE_URL` | `https://getlivewire.com/welcome` |
| `LOB_TEMPLATE_FRONT_ID` / `LOB_TEMPLATE_BACK_ID` | After Step 5 |
| `MODE` | `test` while validating, `live` for production |

---

## Step 3 — Initialize the database

```bash
python -c "import db; db.init_db(); print('DB initialized.')"
```

This creates `permit_miner.db` with all tables.

---

## Step 4 — Deploy the web server

The FastAPI server must be publicly reachable so Exclude button links
in emails work and so `purl_script.js` can call `/scan`.

**Option A — Railway (recommended, free tier)**
1. Push repo to GitHub
2. Connect repo to Railway → New Project → Deploy from GitHub
3. Set environment variables in Railway dashboard
4. Note the public URL — set as `BASE_URL` in `.env`

**Option B — Any Linux VPS ($5/mo Linode/DigitalOcean)**
```bash
# On server:
git clone <repo> permit-miner && cd permit-miner
pip install -r requirements.txt
cp .env.example .env  # fill in values
chmod +x run.sh
./run.sh
```
Point a subdomain (e.g. `permits.getlivewire.com`) at the server IP.
Use nginx as a reverse proxy with SSL (certbot).

**Option C — Local + ngrok (testing only)**
```bash
ngrok http 8000
# Copy the https URL → set as BASE_URL in .env
./run.sh
```

---

## Step 5 — Upload Lob postcard templates

1. Log in to lob.com → Templates
2. Create template → upload `lob/postcard_front.html` → note Template ID → set as `LOB_TEMPLATE_FRONT_ID`
3. Create template → upload `lob/postcard_back.html` → note Template ID → set as `LOB_TEMPLATE_BACK_ID`
4. (Optional) Create drip variants and set `LOB_DRIP_TEMPLATE_FRONT_ID` / `LOB_DRIP_TEMPLATE_BACK_ID`
5. Order a proof → confirm 6x11 size and merge variables render correctly

---

## Step 6 — Set up WordPress PURL page

See `purl/elementor_setup.md` for full instructions. Summary:

1. Create page at `/welcome` in WordPress
2. Build Elementor sections with IDs: `purl-headline`, `purl-subheadline`, `purl-body`, `purl-personalized`
3. Add `purl/purl_script.js` via Custom HTML widget or Code Snippets plugin
4. Update `WEBHOOK_URL` in the script to `{BASE_URL}/scan`
5. Test: visit `getlivewire.com/welcome?pid=test123` — confirm no JS errors

---

## Step 7 — Set up cron jobs

On your server (or Railway cron, GitHub Actions, etc.):

```bash
# Edit crontab: crontab -e
# Set timezone: TZ=America/New_York

# Monday 8:00 AM ET — Shovels pull + preview email
0 8 * * 1  cd /path/to/permit-miner && /path/to/venv/bin/python -m pipeline.monday_pull >> logs/monday.log 2>&1

# Tuesday 8:00 AM ET — Lob send + digest email
0 8 * * 2  cd /path/to/permit-miner && /path/to/venv/bin/python -m pipeline.tuesday_send >> logs/tuesday.log 2>&1

# 5th of each month, 8:00 AM ET — Henrico County import
0 8 5 * *  cd /path/to/permit-miner && /path/to/venv/bin/python -m pipeline.henrico_import >> logs/henrico.log 2>&1

# 1st of each month, 9:00 AM ET — Monthly learning report
0 9 1 * *  cd /path/to/permit-miner && /path/to/venv/bin/python -m pipeline.monthly_report >> logs/monthly.log 2>&1
```

Create the `logs/` directory:
```bash
mkdir -p logs
```

---

## Step 8 — (Optional) Consultation booking webhook

If using Zoho Bookings, Calendly, or similar:

- Set webhook URL to: `{BASE_URL}/booking`
- Method: `POST`
- Payload should include `pid`, `email`, and/or `phone`

Permits matched by any of those fields will be updated to `Consultation Scheduled`.

---

## Step 9 — Test run (dry run)

With `MODE=test` in `.env`:

```bash
# Manual Monday pull
python -m pipeline.monday_pull

# Check DB
python -c "import sqlite3; conn = sqlite3.connect('permit_miner.db'); print(conn.execute('SELECT COUNT(*) FROM permits').fetchone())"

# Manual Tuesday send (test mode — Lob won't print)
python -m pipeline.tuesday_send

# Test exclude endpoint
curl http://localhost:8000/exclude?pid=<id_from_db>

# Test scan endpoint
curl http://localhost:8000/scan?pid=<id_from_db>

# Health check
curl http://localhost:8000/health
```

---

## Step 10 — Go live

1. Set `MODE=live` in `.env`
2. Confirm `LOB_LIVE_KEY` is set
3. Run `python -m pipeline.monday_pull` on a Monday
4. Check preview email arrives with real permits and working Exclude buttons
5. Click an Exclude button — confirm form loads and status updates in DB
6. Tuesday: confirm digest email arrives and postcards show in Lob dashboard

---

## File structure

```
permit-miner/
  config.py               # Static config (ZIP codes, thresholds, tags)
  db.py                   # SQLite schema + helpers
  .env.example            # Environment variable template
  requirements.txt        # Python dependencies
  run.sh                  # Start web server
  pipeline/
    monday_pull.py        # Shovels pull + filter + enrich + preview email
    tuesday_send.py       # Lob send + sales digest
    henrico_import.py     # Monthly Henrico County Excel import
    monthly_report.py     # Monthly learning report
    mailer.py             # Shared SMTP email sender
  web/
    app.py                # FastAPI: /exclude, /scan, /booking, /health
    templates/
      exclude_form.html   # Exclude reason form
  lob/
    postcard_front.html   # 6x11 Lob front template
    postcard_back.html    # 6x11 Lob back template
  purl/
    purl_script.js        # WordPress PURL page JS
    elementor_setup.md    # WordPress/Elementor setup guide
  SETUP_GUIDE.md          # This file
  SPRINT_PLAN.md          # Build sprint sequence
  TEST_PROTOCOL.md        # 18-step validation checklist
```

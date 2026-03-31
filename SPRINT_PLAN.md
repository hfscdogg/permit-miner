# Permit Miner — Sprint Plan

Estimated: 4–5 days to live (code is already written — this is setup + validation).

---

## Day 1 — Environment + Infrastructure

- [ ] Clone repo, create virtualenv, `pip install -r requirements.txt`
- [ ] Copy `.env.example` → `.env`, fill in all API keys and SMTP credentials
- [ ] `python -c "import db; db.init_db()"` — confirm DB creates cleanly
- [ ] Deploy FastAPI server (Railway recommended) — note public URL
- [ ] Set `BASE_URL` in `.env`
- [ ] `curl {BASE_URL}/health` — confirm `{"status":"ok","mode":"test"}`

## Day 2 — Lob Templates + PURL Page

- [ ] Upload `lob/postcard_front.html` and `postcard_back.html` to lob.com
- [ ] Note Template IDs → set in `.env`
- [ ] Order a Lob proof — check 6x11 layout, merge variable rendering, QR code
- [ ] Create `/welcome` page in WordPress per `purl/elementor_setup.md`
- [ ] Update `WEBHOOK_URL` in `purl/purl_script.js` to `{BASE_URL}/scan`
- [ ] Test: `getlivewire.com/welcome?pid=test123` — no JS errors, page loads

## Day 3 — Monday Pipeline Validation

- [ ] Run `python -m pipeline.monday_pull` with `MODE=test`
- [ ] Confirm preview email arrives with permit table
- [ ] Confirm Exclude button links to `{BASE_URL}/exclude?pid=...`
- [ ] Click Exclude button — confirm form renders with permit address pre-filled
- [ ] Submit exclude form — confirm status changes to `Excluded` in DB
- [ ] Confirm exclusion rules created (address blocklisted, contractor incremented)

## Day 4 — Tuesday Pipeline Validation

- [ ] Add a test permit manually to DB with status `Queued`
- [ ] Run `python -m pipeline.tuesday_send` with `MODE=test`
- [ ] Confirm digest email arrives with permit listed
- [ ] Confirm DB status updated to `Sent`
- [ ] Run `python -m pipeline.monday_pull` again — confirm dedup skips seen addresses
- [ ] Test `/scan?pid={id}` — confirm status → `Engaged`, scan alert email fires

## Day 5 — Go Live

- [ ] Set `MODE=live` in `.env`
- [ ] Run Monday pull — confirm real permits in DB and preview email
- [ ] Review preview email — exclude any non-qualifying records
- [ ] Run Tuesday send — confirm postcards appear in Lob dashboard
- [ ] Confirm digest email with sent permits
- [ ] Wait for postcard to arrive (3–5 business days) — scan QR code, confirm scan alert fires and PURL page loads with correct content variant

## Day 6 (optional) — Henrico Import

- [ ] Run `python -m pipeline.henrico_import`
- [ ] Confirm Henrico permits (ZIPs 23229/23233/23238) inserted with `source='Henrico Direct'`
- [ ] These flow into Tuesday send automatically

## Day 7 (optional) — Monthly Report

- [ ] Run `python -m pipeline.monthly_report`
- [ ] Confirm report email with funnel metrics, exclusion reasons, ZIP performance

---

## Scheduling (after go-live)

```
Monday    8:00 AM ET   python -m pipeline.monday_pull
Tuesday   8:00 AM ET   python -m pipeline.tuesday_send
5th/month 8:00 AM ET   python -m pipeline.henrico_import
1st/month 9:00 AM ET   python -m pipeline.monthly_report
```

All logs go to `logs/` directory.

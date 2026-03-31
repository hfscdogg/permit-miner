# Permit Miner — Test Protocol

Run this checklist before going live. All 18 items must pass.

---

## Section 1 — Monday Morning (6 tests)

**1. Monday pull runs without errors**
```bash
python -m pipeline.monday_pull
# Expected: exits 0, INFO logs show ZIP iteration, final count logged
```

**2. Preview email arrives and is correctly formatted**
- Check: email received at `PREVIEW_RECIPIENTS`
- Check: permit table renders with owner name, address, type, value, contractor
- Check: NEW BUILD badge appears on new-construction permits
- Check: no broken HTML

**3. Exclude buttons link to correct URL**
- Click an Exclude button in the preview email
- Expected: browser opens `{BASE_URL}/exclude?pid={id}`
- Expected: form renders with permit address shown

**4. Exclude form submits correctly**
- Select a reason and submit
- Expected: confirmation page ("Excluded. You can close this tab.")
- Expected: DB record status = `Excluded`

**5. Exclusion learning fires**
```bash
python -c "
import db, sqlite3
conn = sqlite3.connect('permit_miner.db')
print(conn.execute('SELECT * FROM exclusion_rules').fetchall())
"
# Expected: address rule created; contractor count incremented if contractor present
```

**6. Dedup works — running Monday pull twice doesn't double-insert**
```bash
python -m pipeline.monday_pull   # run again
python -c "
import sqlite3
conn = sqlite3.connect('permit_miner.db')
print(conn.execute('SELECT COUNT(*) FROM permits WHERE status=\"Queued\"').fetchone())
"
# Expected: same count as after first run
```

---

## Section 2 — Tuesday Morning (6 tests)

**7. Tuesday send runs without errors**
```bash
python -m pipeline.tuesday_send
# Expected: exits 0, Lob calls logged (or test-mode log in MODE=test)
```

**8. Permits status updated to Sent**
```bash
python -c "
import sqlite3
conn = sqlite3.connect('permit_miner.db')
print(conn.execute('SELECT COUNT(*) FROM permits WHERE status=\"Sent\"').fetchone())
"
# Expected: count matches number of Queued records before send
```

**9. Sales digest email arrives**
- Check: email received at `DIGEST_RECIPIENTS`
- Check: sent permits listed with contact info (phone/email as clickable links)
- Check: Exclude buttons present (for post-send exclusions)

**10. Lob postcard appears in Lob dashboard**
- Log in to lob.com → Postcards
- Expected: new postcard(s) visible with correct recipient name and address
- Expected: merge variables rendered (name, QR URL)

**11. PURL scan endpoint works**
```bash
# Get a permit ID from the DB first
pid=$(python -c "import sqlite3; conn=sqlite3.connect('permit_miner.db'); row=conn.execute('SELECT id FROM permits WHERE status=\"Sent\" LIMIT 1').fetchone(); print(row[0] if row else 'none')")
curl "{BASE_URL}/scan?pid=$pid"
# Expected: {"status":"ok","permit_type":"...","is_new_construction":false,"tags":"..."}
```

**12. Scan alert email fires and status updates**
- After Step 11:
- Check: scan alert email received at `ALERT_RECIPIENTS` with owner name + phone
- Check: DB record status = `Engaged`, `qr_scanned=1`, `first_scan_date` set

---

## Section 3 — When Postcard Arrives (6 tests)

**13. QR code scans correctly**
- Scan QR code on physical postcard with phone
- Expected: browser opens `getlivewire.com/welcome?pid={id}`

**14. PURL landing page loads**
- Expected: page loads, no JS errors in browser console
- Expected: page content swaps to match permit type (pool/renovation/new construction/etc.)

**15. Scan alert received on phone**
- Expected: email alert arrives within 30 seconds of scanning
- Expected: owner name prominent, phone number large and tappable

**16. Scan recorded in DB**
```bash
python -c "
import sqlite3
conn = sqlite3.connect('permit_miner.db')
rows = conn.execute('SELECT id, owner_name, status, qr_scanned, scan_count FROM permits WHERE qr_scanned=1').fetchall()
for r in rows: print(dict(zip(['id','owner','status','scanned','count'], r)))
"
# Expected: record shows qr_scanned=1, scan_count>=1, status=Engaged
```

**17. Repeat scans increment count (no duplicate alerts)**
- Scan QR code a second time
- Expected: scan_count increments, but no second scan alert email
- Expected: status stays `Engaged` (not reset)

**18. Monthly report runs**
```bash
python -m pipeline.monthly_report
# Expected: report email with funnel metrics, exclusion reasons, ZIP table
# All zeros are acceptable on first run — confirms the query runs without error
```

---

## Pass criteria

All 18 checks green before flipping `MODE=live` and enabling production cron jobs.

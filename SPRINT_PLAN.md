# Permit Miner: Sprint Plan

Estimated total: 10 working days to live, plus Day 11 for Henrico import.

---

## Sprint 1: Core Data Pipeline (Days 1-2)

### Day 1
- [ ] Create Zoho Creator app "Permit Miner"
- [ ] Create Permit_Miner_Config table with all fields (see schema)
- [ ] Create Permit_Miner_Config Lob_Templates subform
- [ ] Create Permit_Miner_Leads table with all fields (see schema)
- [ ] Create Permit_Miner_Exclusion_Rules table with all fields
- [ ] Insert initial Livewire config record with API keys and ZIP codes
- [ ] Create Exclude_Permit form with predefined reasons

### Day 2
- [ ] Deploy `monday_pull.ds` as scheduled function (Monday 8:00 AM ET)
- [ ] Deploy `exclude_handler.ds` as form action
- [ ] Test: manually trigger Monday Pull for ZIP 23226 only
- [ ] Verify: permits saved to Leads table with correct field mapping
- [ ] Verify: dedup works (run again, no duplicates)
- [ ] Verify: owner_type filter (no company_owned records)
- [ ] Verify: new construction bypass (low-value new builds still qualify)
- [ ] Verify: preview email sends with Exclude buttons
- [ ] Test: click Exclude button, verify form works and status updates

---

## Sprint 2: Lob + CRM Integration (Day 3)

- [ ] Build 6x11 Lob HTML postcard template from `lob/postcard_front.html` and `lob/postcard_back.html`
- [ ] Upload Livewire logo and lifestyle image to hosted URLs
- [ ] Upload template to Lob, get template IDs
- [ ] Add template IDs to config Lob_Templates subform
- [ ] Deploy `tuesday_send.ds` as scheduled function (Tuesday 8:00 AM ET)
- [ ] Create 15 custom fields in Zoho CRM Leads module (see schema)
- [ ] Add "Permit Miner" to Lead Source picklist
- [ ] Add status values to Lead Status picklist
- [ ] Test: manually trigger Tuesday Send in test mode
- [ ] Verify: Lob test postcard created (check Lob dashboard)
- [ ] Verify: CRM Lead created with all custom fields populated
- [ ] Verify: sales digest email sends with correct data
- [ ] Verify: contact enrichment data (phone/email) present where available

---

## Sprint 3: PURL + Tracking (Day 4)

- [ ] Build WordPress page at getlivewire.com/welcome with Elementor
- [ ] Set up dynamic content sections with correct element IDs
- [ ] Add `purl_script.js` to the page
- [ ] Deploy `scan_webhook.ds` as REST API function
- [ ] Configure CORS for getlivewire.com domain
- [ ] Set up Google Analytics UTM tracking (verify existing GA code)
- [ ] Deploy `booking_webhook.ds`
- [ ] Configure Zoho Bookings webhook
- [ ] Test: visit PURL with test pid, verify webhook fires
- [ ] Verify: Creator record updates to "Engaged"
- [ ] Verify: CRM Lead updates with scan date
- [ ] Verify: scan alert email received by sales team
- [ ] Build scan alert email (design matches `emails/scan_alert.html`)

---

## Sprint 4: Settings, Dashboard, Error Handling (Day 5)

- [ ] Build Zoho Creator settings form (friendly UI on top of config table)
  - [ ] ZIP code tag-style multi-select
  - [ ] Value threshold sliders by permit type
  - [ ] Permit category checkboxes
  - [ ] Postcard template dropdown
  - [ ] Email recipient inputs
  - [ ] Exclusion rules table with Active toggle
  - [ ] Drip toggle and delay days
- [ ] Build Zoho Creator performance dashboard
  - [ ] Weekly summary widget
  - [ ] Scan rate chart
  - [ ] Exclusion trends
  - [ ] Pipeline by permit type
- [ ] Implement all error handling scenarios from spec
- [ ] Send test postcard to Henry's physical address

---

## Sprint 5: Polish + Wait for Test Postcard (Days 6-8)

- [ ] Refine exclusion form UX (one-tap reason selection from email)
- [ ] Test preview email Exclude buttons across email clients (Gmail, Apple Mail, Outlook)
- [ ] Verify CRM field mapping is correct on 5+ test records
- [ ] Test contact enrichment across multiple ZIP codes
- [ ] Review and refine email templates (preview + digest + scan alert)
- [ ] Document any Deluge quirks or workarounds discovered during testing
- [ ] Wait for test postcard physical delivery (3-5 business days)

---

## Sprint 6: End-to-End Validation (Days 8-9)

Run the full 18-step test protocol (see `TEST_PROTOCOL.md`):

- [ ] Monday morning tests (#1-6): preview email, data quality, Exclude button
- [ ] Tuesday morning tests (#7-12): Lob send, CRM leads, digest, excluded records
- [ ] Postcard arrival tests (#13-18): print quality, QR scan, PURL, CRM update, scan alert, booking test

**All 18 tests must pass before going live.**

---

## GO LIVE: Day 10

- [ ] Switch config Mode from "test" to "live"
- [ ] Verify all 11 ZIP codes active
- [ ] Let Monday scheduled function run on its natural schedule
- [ ] Monitor first real preview email
- [ ] Monitor first real Tuesday send
- [ ] Verify first batch of real postcards in Lob dashboard
- [ ] Watch for first real QR scans over the following week

---

## Phase 1b: Henrico County Import (Day 11)

- [ ] Deploy `henrico_import.ds` as scheduled function (5th of month, 8:00 AM ET)
- [ ] Run first import manually using most recent available Henrico data
- [ ] Verify Henrico records inserted with Source = "Henrico Direct"
- [ ] Verify Henrico records appear in Monday preview email
- [ ] Confirm downstream flow (Lob send, CRM lead) works for Henrico records

---

## Phase 2: Post-Launch (After 4-6 Weeks)

- [ ] Brian refines postcard creative (front + back)
- [ ] Brian refines PURL landing page design
- [ ] Enable multi-touch drip (set Drip_Enabled = true, monitor results)
- [ ] Deploy `monthly_report.ds` and verify first report
- [ ] Consider A/B test setup (add second template to Lob_Templates subform)
- [ ] Begin onboarding first IntegrateU beta customer (Phase 2 productization)

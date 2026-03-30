# Permit Miner: Setup Guide for Cowork / Zoho Developer

## Prerequisites

Before starting the build, Henry must complete these items:

- [ ] Shovels API key obtained and tested (DONE)
- [ ] Lob production + test API keys obtained (DONE)
- [ ] Zoho Creator admin access available
- [ ] WordPress admin access to getlivewire.com (grant to Cowork)
- [ ] Zoho CRM admin access for custom fields

---

## Step 1: Create Zoho Creator Application

1. Log into Zoho Creator as admin
2. Create new application: **"Permit Miner"**
3. Set application link name to `permit-miner`

## Step 2: Create Tables

Create these three tables using the schemas in `/schemas/`:

### Table 1: Permit_Miner_Config
- See `schemas/permit_miner_config.md` for complete field list
- Create a **subform** called `Lob_Templates` within this table for template management
- After creating the table, insert the initial Livewire config record (values listed at the bottom of the schema doc)
- Store API keys securely (Shovels key, Lob live key, Lob test key)

### Table 2: Permit_Miner_Leads
- See `schemas/permit_miner_leads.md` for complete field list
- This is the largest table (~35 fields)
- Set `Property_Address` as the dedup reference field
- Set `Status` picklist values: Queued, Excluded, Sent, Engaged, Consultation Scheduled, Converted, Drip Queued, Drip Sent, Lob Error

### Table 3: Permit_Miner_Exclusion_Rules
- See `schemas/permit_miner_exclusion_rules.md` for complete field list
- Set `Rule_Type` picklist values: Contractor, Keyword, Address, Owner_Name

## Step 3: Create the Exclusion Form

1. Create a new form called **Exclude_Permit** in the Permit Miner app
2. Accept URL parameter: `record_id` (pre-populates the form)
3. Fields:
   - Record ID (hidden, pre-filled from URL)
   - Exclude_Reason (radio buttons): Wrong contractor, Not luxury / too low-end, Commercial / not residential, Existing customer, Bad address / incomplete data, Custom
   - Custom_Reason (text field, shown only when "Custom" is selected)
4. On form submit: trigger `exclude_handler.ds` function

## Step 4: Deploy Deluge Functions

Create these functions in Zoho Creator. Copy code from the `/deluge/` directory.

### Scheduled Functions

| Function | File | Schedule | Notes |
|----------|------|----------|-------|
| Monday Pull + Preview | `monday_pull.ds` | Every Monday, 8:00 AM ET | Main pipeline. Largest function. |
| Tuesday Auto-Send | `tuesday_send.ds` | Every Tuesday, 8:00 AM ET | Lob + CRM integration |
| Henrico Import | `henrico_import.ds` | 5th of each month, 8:00 AM ET | Phase 1b |
| Monthly Report | `monthly_report.ds` | 1st of each month, 9:00 AM ET | Analytics |

### Form Action Functions

| Function | File | Trigger |
|----------|------|---------|
| Exclude Handler | `exclude_handler.ds` | On submit of Exclude_Permit form |

### REST API Functions (Custom API)

| Function | File | Endpoint | Auth |
|----------|------|----------|------|
| Scan Webhook | `scan_webhook.ds` | GET /scan?pid={id} | Public (no auth required) |
| Booking Webhook | `booking_webhook.ds` | POST /booking | Zoho Bookings webhook |

**For the Scan Webhook:** Configure it to accept unauthenticated requests (CORS enabled for getlivewire.com). This endpoint only updates scan data and is not sensitive.

## Step 5: Zoho CRM Custom Fields

See `schemas/zoho_crm_fields.md` for the complete list.

1. Go to Zoho CRM > Settings > Modules > Leads > Fields
2. Create all 15 custom fields listed in the schema
3. Add "Permit Miner" to the Lead Source picklist
4. Add "Postcard Sent", "Engaged", "Consultation Scheduled" to Lead Status picklist

## Step 6: Lob Account Setup

1. Log into lob.com
2. Note the test API key and live API key
3. Build the postcard template:
   - Use the HTML from `lob/postcard_front.html` and `lob/postcard_back.html`
   - Upload as a 6x11 postcard template
   - Replace the Livewire logo placeholder with the actual hosted logo URL
   - Replace the lifestyle image placeholder on the front
   - Test with Lob's template preview tool to verify safe area
4. Note the template IDs and add them to the Permit_Miner_Config Lob_Templates subform
5. Send one test postcard to Henry's address using the test API key

## Step 7: PURL Landing Page (WordPress)

Follow the instructions in `purl/elementor_setup.md`.

Summary:
1. Create page at getlivewire.com/welcome
2. Build with Elementor (full-width template)
3. Add sections: Hero, Personalized Content, CTA, Social Proof, Footer
4. Set element IDs: `purl-headline`, `purl-subheadline`, `purl-body`, `purl-personalized`
5. Add `purl/purl_script.js` via HTML widget or Code Snippets plugin
6. Update the `WEBHOOK_URL` in the script to match the actual Zoho Creator endpoint
7. Test with `getlivewire.com/welcome?pid=test123`

## Step 8: Zoho Bookings Integration

1. In Zoho Bookings, create a booking type: "Complimentary Smart Home Consultation"
2. Configure a webhook on booking confirmation that POSTs to the `booking_webhook.ds` endpoint
3. Include these fields in the webhook payload: customer_email, customer_phone, customer_name, booking_date, booking_time
4. Optional: pass `pid` through the booking URL if the PURL page appends it

## Step 9: Google Analytics

1. Verify GA tracking code is active on getlivewire.com
2. UTM parameters are embedded in the PURL URLs automatically
3. No additional GA setup needed — the UTMs flow through standard campaign tracking
4. To view: Acquisition > Campaigns > filter for "luxury_permits"

## Step 10: Initial Config Record

Verify the Livewire config record has all values populated:
- All 11 ZIP codes entered
- $500,000 assessed value threshold
- All qualifying tags listed
- Preview email: henry@getlivewire.com
- Sales digest: henry@getlivewire.com, sales@getlivewire.com
- Alert recipients: henry@getlivewire.com
- Return address: Livewire, 4900 W Clay St, Richmond VA 23230
- Mode: "test" (switch to "live" after validation)
- Drip: disabled (enable after first-touch performance is validated)

## Step 11: End-to-End Testing

Follow the 18-step test protocol in `TEST_PROTOCOL.md`.

Key sequence:
1. Set Mode = "test" in config
2. Manually trigger Monday Pull for one ZIP code (23226)
3. Verify preview email arrives
4. Click Exclude on one record
5. Manually trigger Tuesday Send
6. Check Lob dashboard for test postcard
7. Check CRM for new leads
8. Wait for postcard delivery (3-5 days)
9. Scan QR code
10. Verify full loop: Creator update → CRM update → scan alert → booking test

## Step 12: Go Live

1. Switch Mode to "live" in config
2. Verify all 11 ZIP codes are in the config
3. Let the Monday schedule run naturally
4. Monitor the first 2-3 weeks closely
5. After 8-12 weeks of baseline data, consider enabling drip

---

## Important Notes

- **Zoho invokeurl limits:** Zoho Creator has daily API call limits. Monitor usage during the first few weeks. With 11 ZIPs + pagination + resident lookups + contractor lookups, a single Monday run could consume 500-1000+ API calls.
- **Scheduled function timeout:** Zoho Creator functions have a 10-minute execution timeout. If the Monday Pull takes longer than this, split it into batches (e.g., 5 ZIPs per run, two runs per Monday).
- **Lob test vs live:** ALWAYS test with Lob's test key first. Test postcards don't actually print or mail.
- **Shovels data refresh:** Data updates on the 1st and 15th of each month. Monday pulls will always have fresh data.

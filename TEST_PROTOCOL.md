# Permit Miner: Week 1 Test Protocol

Run this checklist after Sprint 4 is complete. Every item must pass before going live.

---

## Monday Morning Tests

| # | Test | How to Verify | Pass/Fail |
|---|------|---------------|-----------|
| 1 | Preview email received | Check Henry's inbox by 8:30 AM ET. Email has "Permit Miner Preview" subject line with formatted permit table. | |
| 2 | Permit count is reasonable | Between 1-30 permits for 11 ZIP codes is expected for a weekly pull. Zero = possible API issue. Thousands = filter not working. | |
| 3 | No LLC/trust records | Every record in the preview shows property_owner_type = "individual". Zero entity-owned permits. | |
| 4 | New construction bypass works | If any new construction permits exist, they appear even if assessed value is low or $0. Look for the "NEW CONSTRUCTION" label. | |
| 5 | Exclude button works on mobile | Open preview email on iPhone. Tap Exclude on one permit. Zoho Creator form opens. Select a reason and submit. | |
| 6 | Exclusion recorded correctly | In Zoho Creator, check the excluded record: Status = "Excluded", Exclude_Reason populated, Excluded_By shows the email of who clicked. | |

## Tuesday Morning Tests

| # | Test | How to Verify | Pass/Fail |
|---|------|---------------|-----------|
| 7 | All non-excluded records changed to "Sent" | In Zoho Creator, query Status = "Queued" for today's batch. Should be zero. Everything either Sent or Excluded. | |
| 8 | Lob tracking IDs logged | Every Sent record has a Lob_Postcard_ID value. Open a few records and check. | |
| 9 | Postcards in Lob dashboard | Log into lob.com. Verify matching number of postcards in production/mailed status. Addresses match. | |
| 10 | CRM Leads created | In Zoho CRM, filter Leads by Lead Source = "Permit Miner". Count matches number of Sent records. All custom fields populated (Permit_Type, Contractor_Name, Assessed_Property_Value, etc.). | |
| 11 | Sales digest email received | Check inbox. Digest shows all Sent permits with owner name, address, value, contractor, phone, email. Excluded records are NOT in the digest. | |
| 12 | Excluded record has no CRM Lead | Check the record that was excluded in test #5. It should NOT have a CRM_Lead_ID. No corresponding Lead in CRM. | |

## When Postcard Arrives (3-5 Days Later)

| # | Test | How to Verify | Pass/Fail |
|---|------|---------------|-----------|
| 13 | Postcard print quality | Henry receives the test postcard. Verify: print quality is sharp, Livewire branding is correct, colors are accurate, address is correct, no content cut off in bleed area. | |
| 14 | QR code scans correctly | Open iPhone camera, point at QR code. Verify: PURL landing page opens at getlivewire.com/welcome with the correct permit record ID in the URL. | |
| 15 | Creator record updated to Engaged | In Zoho Creator, check the permit record. Status should change from "Sent" to "Engaged". First_Scan_Date populated. Scan_Count = 1. | |
| 16 | CRM Lead updated | In Zoho CRM, check the linked Lead. Lead Status should change to "Engaged". Activity note logged with scan date. QR_First_Scan_Date populated. | |
| 17 | Scan alert email received | Check inbox for real-time alert: "[Owner Name] at [Address] just scanned their postcard." Includes phone number, CRM link. | |
| 18 | Consultation booking works | On the PURL page, click "Book a Complimentary Consultation." Complete a test booking in Zoho Bookings. Verify: Creator record updates to "Consultation Scheduled". CRM Lead updates to "Consultation Scheduled" with activity note. | |

---

## Pass Criteria

**All 18 tests must pass before Sprint 5 begins.**

If any test fails:
1. Identify the root cause
2. Fix the specific issue
3. Re-run ONLY the failed test (and any downstream tests it affects)
4. Do not proceed to live until all 18 pass

## Common Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| No preview email | Scheduled function didn't fire | Check Creator schedule settings. Verify timezone is ET. Manually trigger the function. |
| Zero permits found | Date range too narrow or API key issue | Check Last_Monday_Run date in config. Verify Shovels API key is valid. Try a wider date range. |
| All permits filtered out | Value threshold too high or tags too restrictive | Check Min_Assessed_Value in config. Verify Qualifying_Tags includes expected tags. |
| Exclude button opens wrong form | Form link URL incorrect | Check the Creator form URL pattern in monday_pull.ds. Verify form accepts record_id parameter. |
| Lob returns errors | Bad address format or template issue | Check Lob error message in the record. Verify template IDs are correct. Test with Lob's address verification tool. |
| CRM Lead missing fields | Field API names don't match | Compare field API names in tuesday_send.ds against actual CRM field names. Zoho may have added suffixes. |
| QR scan doesn't update record | Webhook URL incorrect or CORS issue | Check browser console for errors. Verify webhook URL in purl_script.js. Check Creator API CORS settings. |
| Booking doesn't update record | Bookings webhook not configured | Verify Zoho Bookings has a webhook pointing to booking_webhook.ds endpoint. Check webhook payload fields. |

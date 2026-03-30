# Zoho CRM Custom Fields Setup

Create these custom fields in the **Leads** module before the system goes live.

## Custom Fields to Create

| Field Name | API Name | Type | Description |
|------------|----------|------|-------------|
| Permit Record ID | Permit_Record_ID | Single Line (Text) | Links CRM Lead back to Zoho Creator Permit_Miner_Leads record ID |
| Permit Value | Permit_Value | Currency | Job value from permit (when reported). Enables CRM reporting by permit value. |
| Permit Type | Permit_Type | Picklist | See values below. Categorizes the type of construction work. |
| Contractor Name | Contractor_Name | Single Line (Text) | Builder/contractor from the permit. Useful for sales context. |
| Assessed Property Value | Assessed_Property_Value | Currency | Tax-assessed market value. Primary qualification filter. |
| Permit Tags | Permit_Tags | Single Line (Text) | Comma-separated Shovels tags (e.g., "remodel,electrical") |
| Is New Construction | Is_New_Construction | Checkbox | true if permit is for new construction |
| PURL URL | PURL_URL | URL | Personalized landing page URL for this lead |
| Postcard Sent Date | Postcard_Sent_Date | Date | Date the postcard was submitted to Lob |
| QR First Scan Date | QR_First_Scan_Date | DateTime | Timestamp of first QR code scan |
| Permit Miner Lead ID | Permit_Miner_Lead_ID | Single Line (Text) | Creator record ID for cross-reference |
| Touch Number | Touch_Number | Number | 1 = first postcard, 2 = drip follow-up |
| Income Range | Income_Range | Single Line (Text) | From Shovels resident data (e.g., "$250,000+") |
| Net Worth | Net_Worth | Single Line (Text) | From Shovels resident data (e.g., "$750,000 to $999,999") |
| LinkedIn URL | LinkedIn_URL | URL | From Shovels resident data |

## Picklist Values to Add

### Permit_Type (new picklist)
- New Construction
- Renovation / Addition
- Pool
- Deck / Outdoor Living
- Kitchen / Bath
- HVAC / Electrical
- ADU
- Other

### Lead Source (add to existing picklist)
- **Permit Miner** (new value)

### Lead Status (add to existing picklist)
- **Postcard Sent** (new value) - Initial status when CRM lead is created
- **Engaged** (new value) - Updated when homeowner scans QR code
- **Consultation Scheduled** (new value) - Updated when booking is confirmed

## Field Mapping Reference

Used by `tuesday_send.ds` when calling `zoho.crm.createRecord("Leads", leadMap)`:

| CRM Field | Source | Notes |
|-----------|--------|-------|
| Last_Name | Property_Legal_Owner | Parse last name from owner string. If semicolon-separated, use first person. |
| First_Name | Property_Legal_Owner | Parse first name. May be blank if format is "LAST, FIRST". |
| Phone | Resident_Phone | From /residents endpoint. May be blank (~25% miss rate). |
| Email | Resident_Email | From /residents endpoint. May be blank. |
| Street | Property_Street_No + " " + Property_Street | Full street address |
| City | Property_City | From Shovels |
| State | Property_State | From Shovels |
| Zip_Code | Property_ZIP | From Shovels |
| Lead_Source | Static: "Permit Miner" | Always this value |
| Lead_Status | Static: "Postcard Sent" | Initial status at creation |
| Company | "Homeowner" | Default. Could use contractor name if preferred. |
| Description | Composite | "Permit type: {type}. Assessed value: ${value}. Contractor: {name}. Filed: {date}. Permit ID: {id}." |
| Permit_Record_ID | Creator record ID | Cross-reference back to Creator |
| Permit_Value | Permit_Job_Value_Cents / 100 | Convert cents to dollars |
| Permit_Type | Derived from tags | Map Shovels tags to picklist value |
| Contractor_Name | Contractor_Name | From /contractors endpoint |
| Assessed_Property_Value | Property_Assessed_Value_Cents / 100 | Convert cents to dollars |
| Permit_Tags | Permit_Tags | Pass through comma-separated |
| Is_New_Construction | Is_New_Construction | Boolean |
| PURL_URL | PURL_URL | Full personalized URL |
| Postcard_Sent_Date | Sent_Date | Date postcard went to Lob |
| Permit_Miner_Lead_ID | ID | Creator auto-number |
| Touch_Number | Touch_Number | 1 or 2 |
| Income_Range | Resident_Income_Range | Pass through |
| Net_Worth | Resident_Net_Worth | Pass through |
| LinkedIn_URL | Resident_LinkedIn | Pass through |

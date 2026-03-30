# Permit_Miner_Leads Table Schema

One record per qualifying permit. Central data table for the entire system.

## Fields

### Record Identity

| Field Name | Type | Required | Description |
|------------|------|----------|-------------|
| ID | Auto-number | Auto | Primary key |
| Customer_ID | Text (50) | Yes | Links to Permit_Miner_Config. "livewire" for now. |
| Source | Picklist | Yes | "Shovels API" or "Henrico Direct" |
| Batch_Date | Date | Yes | The Monday pull date (or Henrico import date) this record was created |

### Permit Data (from Shovels API)

| Field Name | Type | Required | Description |
|------------|------|----------|-------------|
| Permit_ID | Text (100) | Yes | Shovels permit ID. Used for deduplication. |
| Permit_Number | Text (100) | No | Jurisdiction permit number |
| Permit_Type | Text (200) | No | e.g., "Bldg prmt (residential) - addition" |
| Permit_Subtype | Text (200) | No | Shovels subtype field |
| Permit_Tags | Text (500) | No | Comma-separated tags (e.g., "remodel,electrical,plumbing") |
| Permit_Description | Multi-line Text | No | Mostly NULL in Richmond. Capture when available. |
| Permit_File_Date | Date | No | Filing date from Shovels |
| Permit_Job_Value_Cents | Number | No | Job value in cents. UNRELIABLE: 88% are $0. Capture when > 0. |
| Is_New_Construction | Boolean | Yes | true if tags contain "new_construction" or type contains "new" |

### Property Data

| Field Name | Type | Required | Description |
|------------|------|----------|-------------|
| Property_Address | Text (300) | Yes | Full formatted address. **Deduplication key.** |
| Property_Street_No | Text (20) | No | Street number |
| Property_Street | Text (200) | No | Street name |
| Property_City | Text (100) | No | City |
| Property_State | Text (2) | No | State code |
| Property_ZIP | Text (10) | No | ZIP code |
| Property_Assessed_Value_Cents | Number | No | Tax-assessed market value in CENTS. Divide by 100 for dollars. Primary filter. |
| Property_Owner_Type | Text (50) | No | "individual" or "company_owned". Only "individual" passes filter. |
| Property_Legal_Owner | Text (300) | Yes | Owner name(s). May contain semicolons for multiple owners. |

### Contractor Data

| Field Name | Type | Required | Description |
|------------|------|----------|-------------|
| Contractor_ID | Text (100) | No | Shovels contractor ID |
| Contractor_Name | Text (200) | No | Business name from /contractors endpoint |

### Contact Enrichment (from /addresses/{id}/residents)

| Field Name | Type | Required | Description |
|------------|------|----------|-------------|
| Address_Geo_ID | Text (100) | No | Shovels address_id for resident lookup |
| Resident_Name | Text (200) | No | Name from resident lookup |
| Resident_Phone | Phone | No | Phone number. ~75% hit rate. |
| Resident_Email | Email | No | Email address. ~75% hit rate. |
| Resident_LinkedIn | URL | No | LinkedIn profile URL |
| Resident_Income_Range | Text (100) | No | e.g., "$250,000+" |
| Resident_Net_Worth | Text (100) | No | e.g., "$750,000 to $999,999" |

### Status & Workflow

| Field Name | Type | Required | Default | Description |
|------------|------|----------|---------|-------------|
| Status | Picklist | Yes | "Queued" | Lifecycle: Queued > Sent > Engaged > Consultation Scheduled > Converted. Also: Excluded, Drip Queued, Drip Sent, Lob Error |
| Exclude_Reason | Text (500) | No | — | Predefined reason or custom text |
| Excluded_By | Email | No | — | Email of person who clicked Exclude |
| Value_Flag | Text (50) | No | — | "Value unknown" if assessed value is null/0 and not new construction. "Owner type unknown" if property_owner_type is null. |

### Lob Tracking

| Field Name | Type | Required | Description |
|------------|------|----------|-------------|
| Lob_Postcard_ID | Text (100) | No | Lob postcard ID from API response |
| Lob_Postcard_URL | URL | No | Digital proof link |
| Lob_Expected_Delivery | Date | No | Expected delivery date from Lob |
| Lob_Error_Message | Text (500) | No | Error message if Lob rejected the address |
| Sent_Date | DateTime | No | Timestamp when postcard was submitted to Lob |

### PURL / QR Tracking

| Field Name | Type | Required | Description |
|------------|------|----------|-------------|
| PURL_ID | Text (50) | No | Unique identifier for this record's QR/PURL |
| PURL_URL | URL | No | Full personalized URL passed to Lob as {{qr_url}} |
| QR_Scanned | Boolean | No | Flips to true on first scan |
| First_Scan_Date | DateTime | No | Timestamp of first QR scan |
| Scan_Count | Number | No | Total number of scans |
| Consultation_Booked | Boolean | No | true when booking is confirmed via Zoho Bookings |

### CRM Integration

| Field Name | Type | Required | Description |
|------------|------|----------|-------------|
| CRM_Lead_ID | Text (50) | No | Zoho CRM Lead ID. Populated after Tuesday send. |

### Drip / Multi-Touch

| Field Name | Type | Required | Default | Description |
|------------|------|----------|---------|-------------|
| Touch_Number | Number | Yes | 1 | 1 = first postcard, 2 = drip follow-up |
| Parent_Lead_ID | Number | No | — | For touch 2: links back to the original touch 1 record ID |

### Timestamps

| Field Name | Type | Required | Description |
|------------|------|----------|-------------|
| Created_Date | DateTime | Auto | Record creation timestamp |
| Modified_Date | DateTime | Auto | Last modification timestamp |

## Status Lifecycle

```
New permit found:          Queued
Henry excludes:            Queued → Excluded
Tuesday send succeeds:     Queued → Sent
Lob rejects address:       Queued → Lob Error
Homeowner scans QR:        Sent → Engaged
Consultation booked:       Engaged → Consultation Scheduled
Deal closes (manual):      Consultation Scheduled → Converted

Drip flow:
21+ days, no scan:         Sent → (new record created as Drip Queued)
Drip Tuesday send:         Drip Queued → Drip Sent
Drip QR scanned:           Drip Sent → Engaged (cancels any further drip)
```

## Deduplication Logic

Primary dedup key: `Property_Address` (full formatted address).
Before creating any new record, query: `Permit_Miner_Leads[Property_Address == newAddress && Customer_ID == customerId]`
If any record exists (regardless of status), skip. Never mail the same address twice.

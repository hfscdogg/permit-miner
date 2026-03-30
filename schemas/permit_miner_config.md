# Permit_Miner_Config Table Schema

Multi-tenant configuration table. One row per customer. Livewire is row #1.

## Fields

| Field Name | Type | Required | Default | Description |
|------------|------|----------|---------|-------------|
| Customer_ID | Text (50) | Yes | — | Unique tenant identifier (e.g., "livewire") |
| Customer_Name | Text (100) | Yes | — | Display name (e.g., "Livewire") |
| Active | Boolean | Yes | true | Master on/off toggle for this customer |
| Mode | Picklist | Yes | "test" | "test" (uses Lob test key) or "live" (uses Lob production key) |

### API Keys (store encrypted)

| Field Name | Type | Required | Description |
|------------|------|----------|-------------|
| Shovels_API_Key | Text (200) | Yes | Shovels V2 API key. Header: X-API-Key |
| Lob_Live_API_Key | Text (200) | Yes | Lob production API key |
| Lob_Test_API_Key | Text (200) | Yes | Lob test API key |

### Territory Configuration

| Field Name | Type | Required | Default | Description |
|------------|------|----------|---------|-------------|
| Target_ZIP_Codes | Multi-line Text | Yes | — | Comma-separated ZIP codes (e.g., "23226,23229,23233,23238,23113,23114,23059,23103,23831,23832,23836") |
| Min_Assessed_Value | Currency | Yes | 500000 | Minimum property assessed value in DOLLARS. Script converts to cents (*100) for Shovels API comparison. |
| Qualifying_Tags | Multi-line Text | Yes | "remodel,addition,adu,hvac,electrical,plumbing,gas,pool_and_hot_tub" | Comma-separated Shovels permit tags that qualify |
| New_Construction_Tags | Text (200) | Yes | "new_construction" | Tags that trigger new construction bypass |
| New_Construction_Type_Keywords | Text (200) | Yes | "new" | Substrings to match in permit type field for new construction detection |
| Exclusion_Threshold | Number | Yes | 3 | Number of manual exclusions before auto-blocklist rule is created |

### Email Recipients

| Field Name | Type | Required | Description |
|------------|------|----------|-------------|
| Preview_Recipients | Email (multi) | Yes | Monday preview email recipients (Henry only initially) |
| Sales_Digest_Recipients | Email (multi) | Yes | Tuesday sales digest recipients (Henry + sales team) |
| Alert_Recipients | Email (multi) | Yes | Scan alerts + error alerts recipients |

### Postcard Configuration

| Field Name | Type | Required | Description |
|------------|------|----------|-------------|
| Return_Address_Name | Text (100) | Yes | "Livewire" |
| Return_Address_Line1 | Text (200) | Yes | "4900 W Clay St" |
| Return_Address_City | Text (50) | Yes | "Richmond" |
| Return_Address_State | Text (2) | Yes | "VA" |
| Return_Address_ZIP | Text (10) | Yes | "23230" |
| Postcard_Size | Text (10) | Yes | "6x11" |
| Mail_Type | Text (20) | Yes | "usps_first_class" |

### Lob Templates (Subform)

Each row represents one postcard template. Supports A/B testing and seasonal rotation.

| Field Name | Type | Required | Description |
|------------|------|----------|-------------|
| Template_ID | Text (50) | Yes | Lob template ID (e.g., "tmpl_abc123") |
| Template_Label | Text (100) | Yes | Friendly name (e.g., "Spring 2026 - Building/Remodel") |
| Template_Side | Picklist | Yes | "front" or "back" |
| Date_Range_Start | Date | No | Start of active period. Null = always active. |
| Date_Range_End | Date | No | End of active period. Null = no end date. |
| Active | Boolean | Yes | true/false toggle |
| Is_Drip_Template | Boolean | Yes | false = first touch, true = second touch (drip) |

### PURL Configuration

| Field Name | Type | Required | Description |
|------------|------|----------|-------------|
| PURL_Base_URL | URL | Yes | "https://getlivewire.com/welcome" |
| PURL_UTM_Source | Text (50) | Yes | "permit_miner" |
| PURL_UTM_Medium | Text (50) | Yes | "direct_mail" |
| PURL_UTM_Campaign | Text (50) | Yes | "luxury_permits" |
| PURL_Drip_UTM_Campaign | Text (50) | Yes | "luxury_permits_drip" |

### Drip Settings

| Field Name | Type | Required | Default | Description |
|------------|------|----------|---------|-------------|
| Drip_Enabled | Boolean | Yes | false | Master toggle for second-touch postcards |
| Drip_Delay_Days | Number | Yes | 21 | Days after first send before drip triggers |

### Run Tracking

| Field Name | Type | Required | Description |
|------------|------|----------|-------------|
| Last_Monday_Run | DateTime | No | Timestamp of last successful Monday pull |
| Last_Tuesday_Run | DateTime | No | Timestamp of last successful Tuesday send |
| Last_Henrico_Import | DateTime | No | Timestamp of last Henrico County import |
| Last_Monthly_Report | DateTime | No | Timestamp of last monthly report |

## Initial Record for Livewire

```
Customer_ID: "livewire"
Customer_Name: "Livewire"
Active: true
Mode: "test"
Target_ZIP_Codes: "23226,23229,23233,23238,23113,23114,23059,23103,23831,23832,23836"
Min_Assessed_Value: 500000
Qualifying_Tags: "remodel,addition,adu,hvac,electrical,plumbing,gas,pool_and_hot_tub"
New_Construction_Tags: "new_construction"
New_Construction_Type_Keywords: "new"
Exclusion_Threshold: 3
Preview_Recipients: "henry@getlivewire.com"
Sales_Digest_Recipients: "henry@getlivewire.com,sales@getlivewire.com"
Alert_Recipients: "henry@getlivewire.com"
Return_Address_Name: "Livewire"
Return_Address_Line1: "4900 W Clay St"
Return_Address_City: "Richmond"
Return_Address_State: "VA"
Return_Address_ZIP: "23230"
Postcard_Size: "6x11"
Mail_Type: "usps_first_class"
PURL_Base_URL: "https://getlivewire.com/welcome"
PURL_UTM_Source: "permit_miner"
PURL_UTM_Medium: "direct_mail"
PURL_UTM_Campaign: "luxury_permits"
PURL_Drip_UTM_Campaign: "luxury_permits_drip"
Drip_Enabled: false
Drip_Delay_Days: 21
```

# Permit_Miner_Exclusion_Rules Table Schema

Grows automatically from exclusion patterns. Henry can also manually add/deactivate rules.

## Fields

| Field Name | Type | Required | Default | Description |
|------------|------|----------|---------|-------------|
| ID | Auto-number | Auto | — | Primary key |
| Customer_ID | Text (50) | Yes | — | Links to config table. Rules are per-customer. |
| Rule_Type | Picklist | Yes | — | "Contractor", "Keyword", "Address", "Owner_Name" |
| Rule_Value | Text (500) | Yes | — | The blocked value (contractor name, keyword, address, or owner name) |
| Match_Type | Picklist | Yes | "Exact" | "Exact" or "Contains" |
| Exclusion_Count | Number | Yes | 0 | How many times this entity was manually excluded. Increments on each new exclusion. |
| Auto_Generated | Boolean | Yes | false | true = system created this rule after hitting exclusion threshold |
| Active | Boolean | Yes | true | Henry can deactivate any rule without deleting it |
| Created_Date | DateTime | Auto | — | When the rule was created |
| Last_Triggered_Date | DateTime | No | — | Last time this rule auto-excluded a permit |
| Notes | Multi-line Text | No | — | Free text for context |

## Rule Types

### Contractor Blocklist
- **Trigger:** Same contractor_name excluded 3+ times (configurable via Config.Exclusion_Threshold)
- **Behavior:** Auto-exclude future permits from this contractor before they reach the Monday preview email
- **Match:** Exact match on Contractor_Name
- **Example:** Rule_Value = "ABC Budget Builders", Exclusion_Count = 4, Auto_Generated = true

### Keyword Blocklist
- **Trigger:** Manual creation or pattern detection in custom exclusion reasons
- **Behavior:** Auto-exclude permits where Permit_Description or Permit_Type contains the keyword
- **Match:** Contains match
- **Example:** Rule_Value = "storage shed", Match_Type = "Contains"

### Address Blocklist
- **Trigger:** Created when a specific address is excluded
- **Behavior:** Never surface this address again (merged with dedup logic)
- **Match:** Exact match on Property_Address
- **Example:** Rule_Value = "123 Main St, Richmond, VA 23226"

### Owner Name Blocklist
- **Trigger:** Created when an owner is excluded (e.g., existing customer)
- **Behavior:** Skip permits with this owner name
- **Match:** Contains match (handles partial name matches)
- **Example:** Rule_Value = "Clifford", Match_Type = "Contains"

## Exclusion Reasons (predefined picklist for the exclusion form)

| Reason | What the System Learns |
|--------|----------------------|
| Wrong contractor | Increments contractor exclusion count. Auto-blocklists at threshold. |
| Not luxury / too low-end | Flags for ZIP/permit type threshold review in monthly report. |
| Commercial / not residential | Adds keyword to blocklist if description pattern detected. |
| Existing customer | Adds address + owner name to blocklist. Future: cross-ref Zoho CRM. |
| Bad address / incomplete data | Logged. No learning action. |
| Custom reason (free text) | Logged for pattern analysis. Recurring reasons get promoted to predefined list. |

## How Learning Gets Applied (in monday_pull.ds)

```
// Pseudocode for exclusion rule check
exclusion_rules = Permit_Miner_Exclusion_Rules[Customer_ID == config.Customer_ID && Active == true];

for each rule in exclusion_rules {
    if (rule.Rule_Type == "Contractor" && rule.Match_Type == "Exact") {
        if (permit.contractor_name == rule.Rule_Value) { skip; }
    }
    if (rule.Rule_Type == "Keyword" && rule.Match_Type == "Contains") {
        if (permit.description.containsIgnoreCase(rule.Rule_Value)
            || permit.type.containsIgnoreCase(rule.Rule_Value)) { skip; }
    }
    if (rule.Rule_Type == "Address" && rule.Match_Type == "Exact") {
        if (permit.full_address == rule.Rule_Value) { skip; }
    }
    if (rule.Rule_Type == "Owner_Name" && rule.Match_Type == "Contains") {
        if (permit.owner_name.containsIgnoreCase(rule.Rule_Value)) { skip; }
    }
}
```

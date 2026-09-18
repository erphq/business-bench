# Moving billing customers to Stripe

Notes from Fatima (finance). The import file follows `stripe_customer_import_template.csv` exactly: same columns, same
order, one row per customer we still bill. Leave out cancelled accounts and our own QA/test accounts.

## Columns

- **email, name, phone**: billing email, the customer (company) name, billing phone.
- **description**: `Billing contact: <contact name>`.
- **currency**: the three-letter ISO code, lowercase, of the currency we bill them in. LedgerBell shows a bare `$` for
  US, Canadian and Australian dollars alike, so a `$` means the customer's own country's dollar. `US$` always means US
  dollars. If the currency is blank, they are billed in their country's currency (US usd, CA cad, AU aud, GB gbp,
  Germany / Ireland / Netherlands eur).
- **address_line1 / address_line2**: LedgerBell has one Street box. Suite, Ste, Unit, Flat, Floor and Level go in
  address_line2 exactly as written; the building number and street go in address_line1. (UK and Australian
  addresses put the flat or level in front of the street.)
- **address_city, address_postal_code**: as the customer's address has them. US ZIP codes are five digits.
- **address_state**: the postal abbreviation for the US, Canada and Australia (CO, ON, NSW). Leave it blank for
  every other country; Stripe does not need a county or Land.
- **address_country**: two-letter ISO code.
- **metadata[legacy_account]**: the LedgerBell account number, always six digits with its leading zeros
  (`001234`, not `1234`). We use it to match payments during the cutover.
- **metadata[plan]**: the plan code from our price list below.

## Price list codes

| Plan | Monthly | Annual |
|---|---|---|
| Starter | starter_monthly | starter_annual |
| Team | team_monthly | team_annual |
| Business | business_monthly | business_annual |

Business was called Pro until 2025 and some old accounts still say Pro.

Do not import card details; Stripe collects those from customers directly.

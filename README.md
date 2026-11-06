# Odoo Portal Open Items

Odoo 19.0 addon by **Biricon IT Services GmbH** (LGPL-3).

| Module | Description |
|---|---|
| [portal_open_items](portal_open_items/) | Shows the open items (unpaid invoices, credit notes, payments on account) of a customer's whole company in the portal, for any cut-off date, with PDF export. |

## What it does

A portal user whose contact has the option *Show open items in portal* gets the tile **Open items** in the customer
portal. The page lists all open receivable items of the commercial entity (all contacts of the company, archived ones
too), marks overdue items, and shows the balance per currency.

- **Cut-off date (Stichtag):** *Open items as of* shows the list for any day up to today. For a past date a payment
  counts from the day it was reconciled.
- **PDF:** *Download PDF* creates the list for the chosen date with the company's standard report layout; the page can
  also be printed.
- **Payment morale:** above the list (page and PDF) the share of invoices paid in term (green), within a week after the
  term (orange) and later (red, with the average days), the longest open time, a rating *good*/*poor* and the note that
  customers with poor payment morale are switched to prepayment.
- **Opt-in:** the option is off for everybody after the installation. Enable it on the contact (*Contacts* form, next to
  *Website*, users with the right *Billing*).
- **Access:** only the own company, only with the option. The generic report route is protected the same way.

## Requirements

- Odoo 19.0 with `account` and `portal`
- wkhtmltopdf for the PDF (as for every Odoo report)

## Installation

1. Put `portal_open_items` into the addons path.
2. Update the apps list and install *Portal Open Items List*.
3. Tick *Show open items in portal* on the contacts that should see the list.

German translation included.

## Notes

- A negative amount is a credit in favour of the customer, including payments that were not allocated to an invoice.
  Review the open items of a company before enabling the option.
- Posted entries are taken as they are now; for past dates only the reconciliation date is considered.
- On servers with several workers, PDF rendering fetches the page assets from the system parameter `report.url`;
  make sure it is reachable, otherwise the download can hang.

## Tests

```
odoo-bin -d <database> -i portal_open_items --test-tags /portal_open_items --stop-after-init
```

## License

LGPL-3.0 or later, see [LICENSE](LICENSE).

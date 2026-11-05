# Copyright 2026 Biricon IT Services GmbH
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "Portal Open Items List",
    "summary": "Lets selected portal users see the open items (unpaid invoices, credit notes, payments on account) "
    "of their whole company in the customer portal",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "author": "Biricon IT Services GmbH",
    "website": "https://github.com/Alex0176/odoo-portal-open-items",
    "license": "LGPL-3",
    "depends": ["account", "portal"],
    "data": ["views/res_partner_views.xml", "views/portal_templates.xml", "report/open_items_report.xml"],
    "installable": True,
}

from odoo import fields, models

LINK_TYPES = ("out_invoice", "out_refund")


class ResPartner(models.Model):
    _inherit = "res.partner"

    portal_open_items = fields.Boolean(
        "Show open items in portal",
        copy=False,
        help="If this contact logs into the portal, the list of open items of the whole company "
        "(all contacts of the commercial entity) is shown. Off by default.",
    )

    def _open_items_residual(self, line, stichtag):
        """Residual of a receivable line in its own currency as it was at the end of ``stichtag``."""
        residual = line.amount_currency
        for partial in line.matched_debit_ids:
            if partial.max_date <= stichtag:
                residual -= partial.debit_amount_currency
        for partial in line.matched_credit_ids:
            if partial.max_date <= stichtag:
                residual += partial.credit_amount_currency
        return residual

    def _open_items_data(self, stichtag=None, company_ids=None):
        """Open items of the commercial entity of ``self`` as of ``stichtag`` (default: today).

        Based on the posted entries as they are now; payments are counted from the date of their
        reconciliation, so the list shows what was unpaid on that day. Meant to be called with sudo.
        """
        self.ensure_one()
        today = fields.Date.context_today(self)
        stichtag = min(stichtag or today, today)
        is_today = stichtag == today
        domain = [
            ("partner_id.commercial_partner_id", "=", self.commercial_partner_id.id),
            ("parent_state", "=", "posted"),
            ("account_id.account_type", "=", "asset_receivable"),
        ]
        if company_ids is not None:
            domain.append(("company_id", "in", company_ids))
        if is_today:
            domain.append(("reconciled", "=", False))
        else:
            domain += [
                ("date", "<=", stichtag),
                "|", "|",
                ("reconciled", "=", False),
                ("matched_debit_ids.max_date", ">", stichtag),
                ("matched_credit_ids.max_date", ">", stichtag),
            ]
        lines = self.env["account.move.line"].search(domain, order="date_maturity, date, id")
        rows, totals = [], {}
        for line in lines:
            residual = line.amount_residual_currency if is_today else self._open_items_residual(line, stichtag)
            if line.currency_id.is_zero(residual):
                continue
            move = line.move_id
            overdue = bool(line.date_maturity and line.date_maturity < stichtag and residual > 0)
            rows.append({
                "date": line.date,
                "name": move.name,
                "ref": move.ref or move.payment_reference or "",
                "due": line.date_maturity,
                "amount": line.amount_currency,
                "residual": residual,
                "currency": line.currency_id,
                "overdue": overdue,
                "days": (stichtag - line.date_maturity).days if overdue else 0,
                "kind": {"out_invoice": "invoice", "out_refund": "credit"}.get(move.move_type, "payment"),
                "url": f"/my/invoices/{move.id}" if move.move_type in LINK_TYPES else False,
            })
            total = totals.setdefault(line.currency_id, {"residual": 0.0, "overdue": 0.0})
            total["residual"] += residual
            if overdue:
                total["overdue"] += residual
        return {
            "rows": rows,
            "totals": list(totals.items()),
            "company_partner": self.commercial_partner_id,
            "stichtag": stichtag,
            "today": today,
        }

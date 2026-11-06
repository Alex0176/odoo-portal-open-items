from dateutil.relativedelta import relativedelta

from odoo import fields, models

LINK_TYPES = ("out_invoice", "out_refund")
MORALE_MONTHS = 12          # paid invoices of this many months are rated (open ones always)
MORALE_TOLERANCE_DAYS = 7   # "a week over the payment term"
MORALE_GOOD_SHARE = 70.0    # % paid in term or within the tolerance needed for "good"
MORALE_MAX_OPEN_OVERDUE = 30  # an open invoice overdue longer than this makes the rating "poor"


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
        for partial in line.matched_credit_ids:
            if partial.max_date <= stichtag:
                residual -= partial.debit_amount_currency
        for partial in line.matched_debit_ids:
            if partial.max_date <= stichtag:
                residual += partial.credit_amount_currency
        return residual

    def _payment_morale(self, stichtag, company_ids=None):
        """Payment behaviour of the commercial entity as of ``stichtag`` (meant to be called with sudo).

        Rated are the customer invoices (one item per receivable line, so instalments count
        separately) of the last MORALE_MONTHS months plus every invoice still open at the
        stichtag. Paid items count by their last payment date, open items that are overdue count
        as of the stichtag, open items not yet due are not rated.
        """
        self.ensure_one()
        today = fields.Date.context_today(self)
        is_today = stichtag == today
        domain = [
            ("partner_id.commercial_partner_id", "=", self.commercial_partner_id.id),
            ("parent_state", "=", "posted"),
            ("account_id.account_type", "=", "asset_receivable"),
            ("move_id.move_type", "=", "out_invoice"),
            ("date", "<=", stichtag),
            "|", ("date", ">=", stichtag - relativedelta(months=MORALE_MONTHS)),
            "|", "|",
            ("reconciled", "=", False),
            ("matched_debit_ids.max_date", ">", stichtag),
            ("matched_credit_ids.max_date", ">", stichtag),
        ]
        if company_ids is not None:
            domain.append(("company_id", "in", company_ids))
        in_term = within_week = late = 0
        late_days, late_overdue, open_days, open_overdue = [], [], [], 0
        for line in self.env["account.move.line"].search(domain):
            residual = line.amount_residual_currency if is_today else self._open_items_residual(line, stichtag)
            billed = line.move_id.invoice_date or line.date
            due = line.date_maturity or line.date
            if line.currency_id.is_zero(residual):
                paid = [p.max_date for p in line.matched_debit_ids | line.matched_credit_ids if p.max_date <= stichtag]
                end = max(paid or [line.date])
            else:
                end = stichtag
                open_days.append((stichtag - billed).days)
                open_overdue = max(open_overdue, (stichtag - due).days)
                if end <= due:
                    continue
            overdue = (end - due).days
            if overdue <= 0:
                in_term += 1
            elif overdue <= MORALE_TOLERANCE_DAYS:
                within_week += 1
            else:
                late += 1
                late_days.append((end - billed).days)
                late_overdue.append(overdue)
        count = in_term + within_week + late
        result = {"count": count, "max_open_days": max(open_days or [0]), "max_open_overdue": max(open_overdue, 0),
                  "good": None, "in_term": 0, "within_week": 0, "late": 0, "late_days": 0, "late_overdue": 0}
        if count:
            within_week_pct = round(100.0 * within_week / count)
            in_term_pct = round(100.0 * in_term / count) if late else 100 - within_week_pct
            good = 100.0 * (in_term + within_week) / count >= MORALE_GOOD_SHARE and open_overdue <= MORALE_MAX_OPEN_OVERDUE
            result.update({
                "in_term": in_term_pct,
                "within_week": within_week_pct,
                "late": max(100 - in_term_pct - within_week_pct, 0) if late else 0,
                "late_days": round(sum(late_days) / late) if late else 0,
                "late_overdue": round(sum(late_overdue) / late) if late else 0,
                "good": good,
            })
        return result

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
            "morale": self._payment_morale(stichtag, company_ids),
        }

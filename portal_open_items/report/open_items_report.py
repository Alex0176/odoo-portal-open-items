from odoo import api, fields, models
from odoo.exceptions import AccessError


class ReportOpenItems(models.AbstractModel):
    _name = "report.portal_open_items.report_open_items"
    _description = "Open items report"

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        partner = self.env["res.partner"].browse(docids[:1]).commercial_partner_id
        user = self.env.user
        if not user.has_group("account.group_account_invoice"):
            # the generic /report/pdf route is reachable for any user: portal users only get their own company
            own = user.partner_id
            if not own.sudo().portal_open_items or own.commercial_partner_id != partner:
                raise AccessError(self.env._("You are not allowed to access these open items."))
            data = {**data, "company_ids": user.company_ids.ids}
        values = partner.sudo()._open_items_data(fields.Date.to_date(data.get("stichtag")), data.get("company_ids"))
        return {"doc_ids": partner.ids, "doc_model": "res.partner", "docs": partner, **values}

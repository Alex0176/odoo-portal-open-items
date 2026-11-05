import re

from odoo import fields, http
from odoo.http import content_disposition, request

from odoo.addons.portal.controllers.portal import CustomerPortal


class PortalOpenItems(CustomerPortal):
    def _prepare_portal_layout_values(self):
        values = super()._prepare_portal_layout_values()
        values["open_items_enabled"] = request.env.user.partner_id.sudo().portal_open_items
        return values

    def _open_items_stichtag(self, value):
        """Date from the query string; empty, invalid or future values mean today."""
        today = fields.Date.context_today(request.env["res.users"])
        try:
            stichtag = fields.Date.to_date(value) if value else today
        except ValueError:
            stichtag = today
        return min(stichtag or today, today)

    def _open_items_partner(self):
        partner = request.env.user.partner_id
        return partner if partner.sudo().portal_open_items else None

    @http.route("/my/open-items", type="http", auth="user", website=True)
    def portal_my_open_items(self, stichtag=None, **kw):
        partner = self._open_items_partner()
        if not partner:
            return request.redirect("/my")
        data = partner.sudo()._open_items_data(
            self._open_items_stichtag(stichtag), request.env.user.company_ids.ids)
        values = {**self._prepare_portal_layout_values(), **data, "page_name": "open_items"}
        return request.render("portal_open_items.portal_my_open_items", values)

    @http.route("/my/open-items/pdf", type="http", auth="user", website=True)
    def portal_my_open_items_pdf(self, stichtag=None, **kw):
        partner = self._open_items_partner()
        if not partner:
            return request.redirect("/my")
        stichtag = self._open_items_stichtag(stichtag)
        pdf, _type = request.env["ir.actions.report"].sudo()._render_qweb_pdf(
            "portal_open_items.action_report_open_items",
            [partner.commercial_partner_id.id],
            data={"stichtag": fields.Date.to_string(stichtag), "company_ids": request.env.user.company_ids.ids},
        )
        name = re.sub(r"[^\w.-]+", "_", partner.commercial_partner_id.name or "") or "customer"
        filename = f"Open_items_{name}_{stichtag}.pdf"
        return request.make_response(pdf, headers=[
            ("Content-Type", "application/pdf"),
            ("Content-Length", len(pdf)),
            ("Content-Disposition", content_disposition(filename)),
        ])

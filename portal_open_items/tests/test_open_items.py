from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestPortalOpenItems(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env["res.partner"]
        cls.company = Partner.create({"name": "Open Items Test GmbH", "is_company": True})
        cls.other_company = Partner.create({"name": "Fremdfirma Open Items AG", "is_company": True})
        cls.contact = Partner.create({"name": "Portal Chef", "parent_id": cls.company.id, "email": "chef@oi.test"})
        cls.colleague = Partner.create({"name": "Portal Kollege", "parent_id": cls.company.id, "email": "kollege@oi.test"})
        cls.archived = Partner.create({"name": "Ehemaliger", "parent_id": cls.company.id})
        portal = cls.env.ref("base.group_portal")
        Users = cls.env["res.users"].with_context(no_reset_password=True, mail_create_nolog=True)
        cls.user = Users.create({"login": "oi_chef", "password": "oi_chef_pw", "partner_id": cls.contact.id,
                                 "group_ids": [Command.set([portal.id])]})
        cls.user_plain = Users.create({"login": "oi_kollege", "password": "oi_kollege_pw", "partner_id": cls.colleague.id,
                                      "group_ids": [Command.set([portal.id])]})
        cls.inv_company = cls._invoice(cls.company, "Rechnung der Firma", 100.0)
        cls.inv_archived = cls._invoice(cls.archived, "Rechnung des Ehemaligen", 50.0)
        cls.inv_other = cls._invoice(cls.other_company, "Rechnung der Fremdfirma", 70.0)
        cls.inv_paid = cls._invoice(cls.company, "Bezahlte Rechnung", 30.0)
        cls._pay(cls.inv_paid)
        cls.archived.active = False

    @classmethod
    def _line(cls, label, price):
        account = cls.env["account.account"].search([("account_type", "=", "income")], limit=1)
        return {"name": label, "quantity": 1, "price_unit": price, "account_id": account.id, "tax_ids": [Command.clear()]}

    @classmethod
    def _invoice(cls, partner, label, price):
        move = cls.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "invoice_date": fields.Date.today(),
            "invoice_date_due": fields.Date.today(),
            "ref": label,
            "invoice_line_ids": [Command.create(cls._line(label, price))],
        })
        move.action_post()
        return move

    @classmethod
    def _pay(cls, move):
        cls.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=move.ids).create({}).action_create_payments()

    def _get(self, login, password, path="/my/open-items"):
        self.authenticate(login, password)
        return self.url_open(path, allow_redirects=False)

    def test_not_enabled_redirects_and_hides_tile(self):
        res = self._get("oi_chef", "oi_chef_pw")
        self.assertEqual(res.status_code, 303)
        self.assertTrue(res.headers["Location"].endswith("/my"))
        self.assertNotIn("/my/open-items", self._get("oi_chef", "oi_chef_pw", "/my").text)

    def test_enabled_shows_whole_company_only(self):
        self.contact.portal_open_items = True
        res = self._get("oi_chef", "oi_chef_pw")
        self.assertEqual(res.status_code, 200)
        text = res.text
        self.assertIn(self.inv_company.name, text)
        self.assertIn(self.inv_archived.name, text, "invoice of an archived colleague belongs to the company")
        self.assertNotIn(self.inv_other.name, text)
        self.assertNotIn(self.inv_paid.name, text)
        self.assertIn("/my/open-items", self._get("oi_chef", "oi_chef_pw", "/my").text)

    def test_option_is_per_user(self):
        self.contact.portal_open_items = True
        res = self._get("oi_kollege", "oi_kollege_pw")
        self.assertEqual(res.status_code, 303, "a colleague without the option sees nothing")

    def test_credit_note_is_listed_and_balance_shown(self):
        self.contact.portal_open_items = True
        credit = self.env["account.move"].create({
            "move_type": "out_refund", "partner_id": self.company.id, "invoice_date": fields.Date.today(),
            "invoice_line_ids": [Command.create(self._line("Gutschrift", 20.0))],
        })
        credit.action_post()
        text = self._get("oi_chef", "oi_chef_pw").text
        self.assertIn(credit.name, text)
        self.assertTrue("Credit note" in text or "Gutschrift" in text)
        self.assertTrue("Balance" in text or "Saldo" in text)
        self.assertIn("/my/invoices/%s" % credit.id, text)

    def _dated_invoice_paid_later(self):
        today = fields.Date.today()
        invoice_date = today - timedelta(days=20)
        move = self.env["account.move"].create({
            "move_type": "out_invoice", "partner_id": self.company.id, "invoice_date": invoice_date,
            "invoice_date_due": today - timedelta(days=10), "ref": "Stichtag-Rechnung",
            "invoice_line_ids": [Command.create(self._line("Stichtag", 80.0))],
        })
        move.action_post()
        self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=move.ids).create({"payment_date": today - timedelta(days=2)}).action_create_payments()
        return move

    def test_stichtag_uses_payment_date(self):
        move = self._dated_invoice_paid_later()
        today = fields.Date.today()
        before = self.company._open_items_data(today - timedelta(days=5))
        names = [r["name"] for r in before["rows"]]
        self.assertIn(move.name, names, "still open five days ago")
        row = next(r for r in before["rows"] if r["name"] == move.name)
        self.assertTrue(row["overdue"])
        self.assertEqual(row["days"], 5)
        after = [r["name"] for r in self.company._open_items_data(today)["rows"]]
        self.assertNotIn(move.name, after)
        paid_day = [r["name"] for r in self.company._open_items_data(today - timedelta(days=2))["rows"]]
        self.assertNotIn(move.name, paid_day, "the payment counts on its own day")
        early = [r["name"] for r in self.company._open_items_data(today - timedelta(days=30))["rows"]]
        self.assertNotIn(move.name, early, "not yet invoiced")

    def test_stichtag_route_and_future_date(self):
        self.contact.portal_open_items = True
        move = self._dated_invoice_paid_later()
        past = fields.Date.today() - timedelta(days=5)
        self.assertIn(move.name, self._get("oi_chef", "oi_chef_pw", f"/my/open-items?stichtag={past}").text)
        self.assertNotIn(move.name, self._get("oi_chef", "oi_chef_pw").text)
        res = self._get("oi_chef", "oi_chef_pw", "/my/open-items?stichtag=2999-01-01")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self._get("oi_chef", "oi_chef_pw", "/my/open-items?stichtag=quatsch").status_code, 200)

    def test_pdf_route_requires_option(self):
        self.assertEqual(self._get("oi_chef", "oi_chef_pw", "/my/open-items/pdf").status_code, 303)
        self.contact.portal_open_items = True
        res = self._get("oi_chef", "oi_chef_pw", "/my/open-items/pdf")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["Content-Type"], "application/pdf")
        self.assertIn(".pdf", res.headers["Content-Disposition"])

    def test_report_html_and_access(self):
        report = self.env.ref("portal_open_items.action_report_open_items")
        html, _t = report._render_qweb_html(report.report_name, [self.company.id], data={"stichtag": fields.Date.to_string(fields.Date.today())})
        self.assertIn(self.inv_company.name.encode(), html)
        self.assertNotIn(self.inv_other.name.encode(), html)
        # generic report route: a portal user may only see the own company, and only with the option
        with self.assertRaises(AccessError):
            report.with_user(self.user)._render_qweb_html(report.report_name, [self.company.id])
        self.contact.portal_open_items = True
        report.with_user(self.user)._render_qweb_html(report.report_name, [self.company.id])
        with self.assertRaises(AccessError):
            report.with_user(self.user)._render_qweb_html(report.report_name, [self.other_company.id])

import requests
from datetime import datetime
from odoo import _, api, fields, models


_HOST = "http://51.38.125.199"
_PORT = 8080

_URL = f"{_HOST}:{_PORT}"
_OWNERS = f"{_URL}/api/v1/owners"
_ADDRESS = f"{_URL}"


class AccountMove(models.Model):
    _inherit = ["account.move"]

    # Description : The covered month
    invoice_month = fields.Date(string="Invoice month")
    pricelist_id = fields.Many2one('product.pricelist', 'Pricelist')
    error_counter = fields.Integer(default=0)

    def _send_mail_error_api(self, error, exception, invoice_id, code=""):
        admin_id = self.env.ref('base.user_admin')
        mail = self.env['mail.mail'].sudo().create({
            'author_id': self.env.user.partner_id.id,
            'auto_delete': True,
            'body_html': f"Error {exception} on account.move {invoice_id}",
            'email_from': self.env.user.email_formatted or self.env.company.catchall_formatted,
            'email_to': admin_id.email,
            'subject': f"{error} {code}",
            'state': 'outgoing',
        }).send()

    def _update_invoices(self):
        # Description : Go through all the invoices that are in draft.
        # Send a request to matelso's API with right partner_id.owner_id
        # Check if invoice.invoice_month == api_result.month
        # Check invoice.invoice_line_ids for products that have a matelso_product_type
        # defined
        # Check in the api_result if the pushes, conversations or users are above the
        # amount defined on the line. If it is above -> add/edit invoice_line with
        # corresponding "usage surplus" product (using
        # self.env.ref("surplus_product_{pushes/users/conversations}") and set/update the
        # price accordingly based on the defined pricelist
        draft_invoice = self.env["account.move"].search([('state', '=', 'draft')])
        for inv in draft_invoice:
            if not inv.partner_id.owner_id:
                continue
            url = f"{_OWNERS}/{inv.partner_id.owner_id}/usage" #ADDED A 2 FOR TEST TO REMOVE
            try:
                answer = requests.get(url, timeout=5) if url else ""
                answer.raise_for_status()
                response = answer.json()
                inv.error_counter = 0
            except requests.HTTPError as e:
                code = e.response.status_code
                if code == 404 or inv.error_counter > 4:
                    self._send_mail_error_api("HTTP ERROR - API", e, inv.id, code)
                else:
                    inv.error_counter += 1
                continue
            except requests.ConnectionError as e:
                if inv.error_counter > 4:
                    self._send_mail_error_api("Connection ERROR - API", e, inv.id)
                continue
            except requests.Timeout as e:
                if inv.error_counter > 4:
                    self._send_mail_error_api("Timeout ERROR - API", e, inv.id)
                continue
            if not response:
                continue
            try:
                month = response["month"]
                if not isinstance(month, str):
                    continue
            except KeyError as e:
                continue
            month_api = datetime.strptime(month, "%Y-%m-%dT%H:%M:%S")
            if inv.invoice_month and month_api.month != inv.invoice_month.month:
                continue
            lines = inv.invoice_line_ids.filtered(lambda r: r.product_id.mtls_product_type != False and r.product_id.recurring_invoice != False)
            for line in lines:
                types = line.product_id.mtls_product_type
                try:
                    element_quantity = response['pushCount'] if types == "pushCount" else response['entities'][types]['peak']
                    if not isinstance(element_quantity, int):
                        continue
                except KeyError as e:
                    continue
                diff = line.quantity * line.product_uom_id.factor_inv - element_quantity
                line_supp = inv.invoice_line_ids.filtered(lambda r: r.product_id.mtls_product_type == types and r.product_id.recurring_invoice == False)
                diff = diff*-1 - sum([supp.quantity * supp.product_uom_id.factor_inv for supp in line_supp])
                if diff > 0:
                    product_to_add = self.env['product.product'].search([('mtls_product_type', '=', types), ('recurring_invoice', '=', False)])[0]
                    if product_to_add:
                        quantity = diff*line.product_uom_id.factor
                        price = inv.pricelist_id.get_products_price(product_to_add, [quantity], [inv.partner_id]).get(product_to_add.id, 0.0) if inv.pricelist_id else product_to_add.price
                        line.with_context(check_move_validity=False).create({
                            'move_id': line.move_id.id,
                            'account_id': line.account_id.id,
                            'partner_id': line.partner_id.id,
                            'product_id': product_to_add.id,
                            'product_uom_id': line.product_uom_id.id,
                            'quantity': quantity,
                            'tax_ids': line.tax_ids,
                            'price_unit': price,
                            'name': product_to_add.description_sale if product_to_add.description_sale else product_to_add.name,
                        })

    def _cron_update_invoices(self):
        res = self._update_invoices()
        return res

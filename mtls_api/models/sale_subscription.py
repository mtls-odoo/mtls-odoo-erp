from odoo import _, api, fields, models


class SaleSubscription(models.Model):
    _inherit = "sale.subscription"

    def _prepare_invoice_data(self):
        res = super()._prepare_invoice_data()
        res['invoice_month'] = self.date_start
        res['pricelist_id'] = self.pricelist_id
        return res

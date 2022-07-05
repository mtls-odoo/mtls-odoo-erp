from odoo import _, api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    # Description : id to use for matelso's API
    owner_id = fields.Char(string="Owner")

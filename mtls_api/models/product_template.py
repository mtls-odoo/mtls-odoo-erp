from odoo import _, api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    mtls_product_type = fields.Selection(
        string="Matelso product type",
        selection=[("pushCount", "Pushes"), ("Users", "Users"), ("Conversation", "Conversations")],
    )

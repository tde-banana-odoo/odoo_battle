from odoo import fields, models


class BattleUnitTemplate(models.Model):
    _name = 'battle.unit.template'
    _inherit = ['battle.unit.stats.mixin']
    _description = "Unit Template"
    _order = 'sequence asc, id asc'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer()
    battle_unit_ids = fields.One2many('battle.unit', 'battle_unit_template_id', string="Units")

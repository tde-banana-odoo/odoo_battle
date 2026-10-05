from odoo import fields, models

from odoo.addons.odoo_battle.const import POSITIONS, SIDE_SELECTION, WOUND_STATES


class BattleResultLine(models.Model):
    """ Unit taking part in a battle: position, damage and wounds received,
    and its state before the battle (to revert it) """
    _name = 'battle.result.line'
    _description = "Battle Result Unit"
    _order = 'battle_result_id, side, position, id'

    battle_result_id = fields.Many2one('battle.result', string="Result", required=True, index=True, ondelete='cascade')
    battle_unit_id = fields.Many2one('battle.unit', string="Unit", required=True, ondelete='cascade')
    side = fields.Selection(SIDE_SELECTION, string="Side", required=True)
    position = fields.Selection(POSITIONS, string="Position", required=True, default='frontline')
    damage = fields.Integer("Damage Received")
    wounds = fields.Integer("Wounds", help="Wounds received (negative when healed)")
    damage_counter_before = fields.Integer("Damage Before")
    wound_state_before = fields.Selection(WOUND_STATES, string="Wounds Before")

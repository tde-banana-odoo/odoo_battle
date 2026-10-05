from odoo import api, fields, models

from odoo.addons.odoo_battle.const import CAMPS, COMMAND_TYPES


class BattleCommandAction(models.Model):
    """ Command action picked by a camp for a round in a location, thanks to
    its leadership successes: Location Support (+1 bonus), Hold On (more
    resistance, less damage), Full Attack (more damage, less resistance),
    Retreat (no battle effect, resolved by the DM), Unstoppable Attack (more
    damage when attacking, allowed by role-play only). """
    _name = 'battle.command.action'
    _description = "Command Action"
    _order = 'battle_round_id, camp, id'

    battle_round_id = fields.Many2one('battle.round', string="Round", required=True, index=True, ondelete='cascade')
    camp = fields.Selection(CAMPS, string="Camp", required=True)
    command_type = fields.Selection(COMMAND_TYPES, string="Action", required=True)
    note = fields.Char("Note", help="e.g. why a role-play action was allowed.")
    battle_location_id = fields.Many2one(
        'battle.location', string="Location", required=True, domain="[('is_external', '=', False)]",
    )

    @api.depends('command_type', 'battle_location_id')
    def _compute_display_name(self):
        types = dict(self._fields['command_type']._description_selection(self.env))
        for action in self:
            action.display_name = f"{types.get(action.command_type, '')} ({action.battle_location_id.name or ''})"

    @api.constrains('battle_round_id', 'camp')
    def _check_command_action_count(self):
        self.battle_round_id._check_command_action_count()

from odoo import api, fields, models

from odoo.addons.odoo_battle.const import CAMPS, COMMAND_BONUS, COMMAND_BONUS_MAX, COMMAND_RATES, COMMAND_STANCES, COMMAND_TYPES

# printed after the rule of some actions, in French
COMMAND_NOTES = {
    'retreat': "les unités quittent ensuite la zone",
    'attack_unstoppable': "accordée en jeu de rôle",
}


class BattleCommandAction(models.Model):
    """ Command action picked by a camp for a round in a location, thanks to
    its leadership successes: Battle Support (+1 bonus, +2 at most per
    side), Hold On (more resistance, less damage), Full Attack (more damage,
    less resistance), Retreat (covered retreat: no damage dealt, doubled
    resistance; the DM then moves units out), Unstoppable Attack (more
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

    @api.model
    def _get_command_rule(self, command_type: str) -> str:
        """ Effect of a command action, in French, from the rules constants,
        e.g. '+1 au bonus par action (+2 max par camp)' """
        parts = []
        if command_type in COMMAND_BONUS:
            rule = f"+{COMMAND_BONUS[command_type]} au bonus par action"
            if command_type in COMMAND_BONUS_MAX:
                rule += f" (+{COMMAND_BONUS_MAX[command_type]} max par camp)"
            parts.append(rule)
        rates = COMMAND_RATES.get(command_type, {})
        for stat, label in (('damage', "dégâts"), ('resistance', "résistance")):
            if rates.get(stat, 100) != 100:
                parts.append(f"{label} ×{rates[stat]} %")
        rule = ', '.join(parts)
        if COMMAND_STANCES.get(command_type) == 'attack':
            rule = f"en attaque : {rule}"
        if command_type in COMMAND_NOTES:
            rule += f" ; {COMMAND_NOTES[command_type]}"
        return rule

    @api.constrains('battle_round_id', 'camp')
    def _check_command_action_count(self):
        self.battle_round_id._check_command_action_count()

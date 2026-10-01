from odoo import fields, models


class BattleLeader(models.Model):
    """ Important character on the map, mainly followed for narrative """
    _name = 'battle.leader'
    _inherit = ['mail.thread']
    _description = "Character"
    _order = 'battle_faction_sequence asc, name asc, id asc'

    name = fields.Char(required=True, translate=True)
    battle_faction_id = fields.Many2one('battle.faction', string="Faction", tracking=True)
    battle_faction_sequence = fields.Integer("Faction Sequence", related='battle_faction_id.sequence', store=True)
    battle_location_id = fields.Many2one('battle.location', string="Location", tracking=True)
    state = fields.Selection(
        [('alive', 'Alive'), ('routing', 'Routing'), ('dead', 'Dead'), ('mia', 'Missing')],
        string="Status", default='alive', required=True, tracking=True,
        help="Missing: missing in action.",
    )

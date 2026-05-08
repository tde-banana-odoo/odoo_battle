from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BattleFaction(models.Model):
    _name = 'battle.faction'
    _description = "Faction"
    _order = 'sequence asc, id asc'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer()
    leader_name = fields.Char("Leader")
    # diplomacy
    role = fields.Selection(
        [('aggressor', 'Aggressor'), ('defender', 'Defender'), ('neutral', 'Neutral')],
        string="Role", default='neutral', required=True,
    )
    allied_faction_id = fields.Many2one(
        'battle.faction', string="Ally",
        help="Faction a neutral faction supports in battles.",
    )
    # statistics
    morale = fields.Integer(default=3)
    # units
    battle_unit_ids = fields.One2many(
        'battle.unit', 'battle_faction_id', string="Units",
    )
    battle_unit_count = fields.Integer(
        "Unit Count", compute='_compute_battle_unit_count',
    )

    @api.depends('battle_unit_ids')
    def _compute_battle_unit_count(self):
        for faction in self:
            faction.battle_unit_count = len(faction.battle_unit_ids)

    @api.constrains('role', 'allied_faction_id')
    def _check_allied_faction_id(self):
        for faction in self.filtered('allied_faction_id'):
            if faction.role != 'neutral':
                raise ValidationError(_("Only neutral factions have allies, %s is not neutral.", faction.name))
            if faction.allied_faction_id == faction:
                raise ValidationError(_("Faction %s cannot be allied to itself.", faction.name))

    def _get_camp(self):
        """ Factions fighting together with ``self``: the factions they are
        allied to (if neutral), and all neutral factions allied to those. """
        leaders = self | self.allied_faction_id
        return leaders | self.search([('role', '=', 'neutral'), ('allied_faction_id', 'in', leaders.ids)])

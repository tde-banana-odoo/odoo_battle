from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

# from best to worst, integer-like keys ease comparisons
MORALES = [('4', 'Outstanding'), ('3', 'Steady'), ('2', 'Shaken'), ('1', 'Wavering'), ('0', 'Routing')]


class BattleFaction(models.Model):
    _name = 'battle.faction'
    _description = "Faction"
    _order = 'sequence asc, id asc'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer()
    leader_id = fields.Many2one('battle.leader', string="Leader", domain="[('battle_faction_id', '=', id)]")
    # diplomacy
    role = fields.Selection(
        [('aggressor', 'Aggressor'), ('defender', 'Defender'), ('neutral', 'Neutral')],
        string="Role", default='neutral', required=True,
    )
    allied_faction_id = fields.Many2one(
        'battle.faction', string="Ally",
        help="Faction a neutral faction supports in battles.",
    )
    # current round morale
    morale = fields.Selection(
        MORALES, string="Morale", compute='_compute_morale', inverse='_inverse_morale',
        help="Morale for the current round, see leadership rolls.",
    )
    # units
    battle_unit_ids = fields.One2many(
        'battle.unit', 'battle_faction_id', string="Units",
    )
    battle_unit_count = fields.Integer(
        "Unit Count", compute='_compute_battle_unit_count', help="Alive units",
    )

    @api.depends('battle_unit_ids.is_dead')
    def _compute_battle_unit_count(self):
        for faction in self:
            faction.battle_unit_count = len(faction.battle_unit_ids.filtered(lambda unit: not unit.is_dead))

    def _compute_morale(self):
        lines = self.env['battle.round']._get_current().battle_round_leadership_ids
        for faction in self:
            faction.morale = lines.filtered(lambda line: line.battle_faction_id == faction)[:1].morale or '3'

    def _inverse_morale(self):
        current = self.env['battle.round']._get_current()
        for faction in self:
            line = current.battle_round_leadership_ids.filtered(lambda line: line.battle_faction_id == faction)
            if line:
                line.morale = faction.morale
            elif current:
                current.battle_round_leadership_ids = [(0, 0, {'battle_faction_id': faction.id, 'morale': faction.morale})]

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

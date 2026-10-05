from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from odoo.addons.odoo_battle.const import FACTION_ROLES


class BattleFaction(models.Model):
    """ Faction of the war: aggressors, defenders (holding locations by
    default), or neutrals allied to one of them. Leadership (morale, command
    actions) is managed per camp on rounds. """
    _name = 'battle.faction'
    _description = "Faction"
    _order = 'sequence asc, id asc'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer()
    color = fields.Integer("Color", help="Color of the faction tags, e.g. in the battle solver.")
    leader_id = fields.Many2one('battle.leader', string="Leader", domain="[('battle_faction_id', '=', id)]")
    # diplomacy
    role = fields.Selection(
        FACTION_ROLES, string="Role", default='neutral', required=True,
        help="Aggressors and defenders lead their camp; neutral factions fight along their ally.",
    )
    allied_faction_id = fields.Many2one(
        'battle.faction', string="Ally",
        help="Faction a neutral faction supports in battles.",
    )
    # units
    battle_unit_ids = fields.One2many(
        'battle.unit', 'battle_faction_id', string="Units",
    )
    battle_unit_count = fields.Integer(
        "Unit Count", compute='_compute_battle_unit_count', help="Alive units",
    )

    @api.constrains('role', 'allied_faction_id')
    def _check_allied_faction_id(self):
        for faction in self.filtered('allied_faction_id'):
            if faction.role != 'neutral':
                raise ValidationError(_("Only neutral factions have allies, %(faction_name)s is not neutral.", faction_name=faction.name))
            if faction.allied_faction_id == faction:
                raise ValidationError(_("Faction %(faction_name)s cannot be allied to itself.", faction_name=faction.name))

    @api.depends('battle_unit_ids.is_dead')
    def _compute_battle_unit_count(self):
        for faction in self:
            faction.battle_unit_count = len(faction.battle_unit_ids.filtered(lambda unit: not unit.is_dead))

    def _get_camp(self):
        """ Factions fighting together with ``self``: the factions they are
        allied to (if neutral), and all neutral factions allied to those. """
        leaders = self | self.allied_faction_id
        return leaders | self.search([('role', '=', 'neutral'), ('allied_faction_id', 'in', leaders.ids)])

    def _get_camp_role(self):
        """ Camp ('aggressor' or 'defender') the faction fights for: its role,
        or the role of its ally if neutral; False for unallied neutrals """
        self.ensure_one()
        faction = self.allied_faction_id if self.role == 'neutral' else self
        return faction.role if faction.role in ('aggressor', 'defender') else False

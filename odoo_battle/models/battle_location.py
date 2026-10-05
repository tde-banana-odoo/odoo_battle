from __future__ import annotations

import typing

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from odoo.addons.odoo_battle.const import LOCATION_STATUSES

if typing.TYPE_CHECKING:
    from odoo.addons.odoo_battle.models.battle_faction import BattleFaction
    from odoo.addons.odoo_battle.models.battle_location_effect import BattleLocationEffect


class BattleLocation(models.Model):
    """ Place of the battlefield (or external one, e.g. for reserves), free,
    contested or held by a faction. Battles are solved where opposing camps
    meet; their outcome may shift the status, and grant effects to factions
    for the next round. """
    _name = 'battle.location'
    _description = "Location"
    _order = 'sequence asc, id desc'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer()
    # realm / umbra twin, kept in sync both ways
    linked_location_id = fields.Many2one(
        'battle.location', string="Linked Location",
        help="Twin location, e.g. the Umbra counterpart of a physical location.",
    )
    # control
    status = fields.Selection(
        LOCATION_STATUSES, string="Status", default='free', required=True,
    )
    held_by_faction_id = fields.Many2one(
        'battle.faction', string="Held By",
        compute='_compute_held_by_faction_id', store=True, readonly=False,
    )
    # properties
    is_umbra = fields.Boolean("Umbra", help="Spirit world: battles use Gnosis instead of Rage or Willpower.")
    is_external = fields.Boolean(
        "External", help="Off the battlefield (not available in the battle solver), e.g. to prepare reserves.",
    )
    battle_trait_ids = fields.Many2many(
        'battle.trait', string="Traits", domain="[('target', '=', 'location')]",
    )
    battle_location_effect_ids = fields.One2many(
        'battle.location.effect', 'battle_location_id', string="Faction Effects",
        help="Traits factions benefit from (or suffer) here for a given round, e.g. granted by battle outcomes.",
    )
    # units
    battle_unit_ids = fields.One2many(
        'battle.unit', 'battle_location_id', string="Units",
    )
    forces_summary = fields.Char(
        "Forces", compute='_compute_forces_summary',
        help="Fighting units per faction, with their menace, e.g. 'Kiker (9, M23)'",
    )

    @api.constrains('status', 'held_by_faction_id')
    def _check_held_by_faction_id(self):
        for location in self:
            if location.status == 'held' and not location.held_by_faction_id:
                raise ValidationError(_("Location %(location_name)s is held: please set the faction holding it.", location_name=location.name))

    @api.constrains('linked_location_id')
    def _check_linked_location_id(self):
        for location in self:
            if location.linked_location_id == location:
                raise ValidationError(_("Location %(location_name)s cannot be linked to itself.", location_name=location.name))

    @api.depends('status')
    def _compute_held_by_faction_id(self):
        self.filtered(lambda loc: loc.status == 'free').held_by_faction_id = False

    @api.depends('battle_unit_ids.is_fighting', 'battle_unit_ids.battle_faction_id', 'battle_unit_ids.menace')
    def _compute_forces_summary(self):
        for location in self:
            location.forces_summary = ', '.join(
                f"{faction.name} ({count}, M{menace})" for faction, count, menace in location._get_forces()
            )

    @api.depends('name', 'is_external')
    @api.depends_context('battle_round_id')
    def _compute_display_name(self):
        """ External locations are flagged; with a round in context (e.g. in
        the battle solver), locations where a battle is solved are flagged """
        solved = self.env['battle.result'].search([
            ('battle_round_id', '=', self.env.context['battle_round_id']), ('state', '=', 'done'),
        ]).battle_location_id if self.env.context.get('battle_round_id') else self.browse()
        for location in self:
            name = _("%(location_name)s (External)", location_name=location.name) if location.is_external else location.name
            location.display_name = _("%(location_name)s (Solved)", location_name=name) if location in solved else name

    @api.model_create_multi
    def create(self, vals_list):
        locations = super().create(vals_list)
        locations.filtered('linked_location_id')._update_linked_location(self.browse())
        return locations

    def write(self, vals):
        if 'linked_location_id' not in vals:
            return super().write(vals)
        previous = {location: location.linked_location_id for location in self}
        res = super().write(vals)
        for location in self:
            location._update_linked_location(previous[location])
        return res

    def _get_battle_sides(self) -> tuple[BattleFaction, BattleFaction]:
        """ Factions fighting in the location, as (initiators, responders).
        Responders: holders and their allies, or the defender camp if not
        held. Initiators: other factions present. """
        self.ensure_one()
        factions = self.battle_unit_ids.filtered('is_fighting').battle_faction_id
        holders = self.held_by_faction_id or self.env['battle.faction'].search([('role', '=', 'defender')])
        camp = holders._get_camp()
        return factions - camp, factions & camp

    def _get_shifted_status(self, factions: BattleFaction, main_faction: BattleFaction, steps: int = 1) -> tuple[str, BattleFaction]:
        """ Status and holder after moving ``steps`` times towards
        ``factions`` (a battle side), e.g. after an attacking victory: a
        location held by another camp becomes contested, then held by
        ``main_faction``; a contested location held by ``factions`` becomes
        held again. Returns (status, holding faction). """
        self.ensure_one()
        status, holder = self.status, self.held_by_faction_id
        for _step in range(steps):
            if holder and holder in factions:
                status = 'held'
            elif status == 'held':
                status = 'contested'
            else:
                status, holder = 'held', main_faction
        return status, holder

    def _get_round_effects(self, round_number: int) -> BattleLocationEffect:
        """ Effects applying in the location during the round ``round_number`` """
        self.ensure_one()
        return self.battle_location_effect_ids.filtered(lambda effect: effect.round_number == round_number)

    def _get_forces(self) -> list[tuple[BattleFaction, int, int]]:
        """ Fighting units per faction, as a list of (faction, count, menace) """
        self.ensure_one()
        units = self.battle_unit_ids.filtered(lambda unit: unit.is_fighting and unit.battle_faction_id)
        return [
            (faction, len(faction_units), sum(faction_units.mapped('menace')))
            for faction, faction_units in units.grouped('battle_faction_id').items()
        ]

    def _update_linked_location(self, previous):
        """ Keep links symmetric: unlink the ``previous`` twin, link the new
        twin back """
        for location in self:
            twin = location.linked_location_id
            if previous and previous != twin and previous.linked_location_id == location:
                previous.linked_location_id = False
            if twin and twin.linked_location_id != location:
                twin.linked_location_id = location

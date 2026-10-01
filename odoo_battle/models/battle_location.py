from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BattleLocation(models.Model):
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
        [('free', 'Free'), ('contested', 'Contested'), ('held', 'Held')],
        string="Status", default='free', required=True,
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
    # units
    battle_unit_ids = fields.One2many(
        'battle.unit', 'battle_location_id', string="Units",
    )

    @api.depends('status')
    def _compute_held_by_faction_id(self):
        self.filtered(lambda loc: loc.status == 'free').held_by_faction_id = False

    @api.constrains('status', 'held_by_faction_id')
    def _check_held_by_faction_id(self):
        for location in self:
            if location.status == 'held' and not location.held_by_faction_id:
                raise ValidationError(_("Location %s is held: please set the faction holding it.", location.name))

    @api.constrains('linked_location_id')
    def _check_linked_location_id(self):
        for location in self:
            if location.linked_location_id == location:
                raise ValidationError(_("Location %s cannot be linked to itself.", location.name))

    def _get_battle_sides(self):
        """ Factions fighting in the location, as (initiators, responders).
        Responders: holders and their allies, or the defender camp if not
        held. Initiators: other factions present. """
        self.ensure_one()
        factions = self.battle_unit_ids.battle_faction_id
        holders = self.held_by_faction_id or self.env['battle.faction'].search([('role', '=', 'defender')])
        camp = holders._get_camp()
        return factions - camp, factions & camp

    @api.model_create_multi
    def create(self, vals_list):
        locations = super().create(vals_list)
        locations.filtered('linked_location_id')._sync_linked_location(self.browse())
        return locations

    def write(self, vals):
        if 'linked_location_id' not in vals:
            return super().write(vals)
        previous = {location: location.linked_location_id for location in self}
        res = super().write(vals)
        for location in self:
            location._sync_linked_location(previous[location])
        return res

    def _sync_linked_location(self, previous):
        """ Keep links symmetric: unlink previous twin, link new twin back """
        for location in self:
            twin = location.linked_location_id
            if previous and previous != twin and previous.linked_location_id == location:
                previous.linked_location_id = False
            if twin and twin.linked_location_id != location:
                twin.linked_location_id = location

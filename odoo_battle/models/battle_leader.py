from odoo import api, fields, models
from odoo.tools import BinaryBytes

from odoo.addons.odoo_battle.const import NARRATIVE_STATES, UNIT_TYPES, WOUND_STATES
from odoo.addons.odoo_battle.models.battle_unit_stats_mixin import GLYPH_BACKGROUND, get_unit_type_glyph

# unit type glyphs have a square background, replaced by a gold ringed circle for leaders
LEADER_BACKGROUND = b'<circle cx="90" cy="90" r="84" fill="%s" stroke="#c9a227" stroke-width="10"/><g transform="translate(27 27) scale(0.7)">'


class BattleLeader(models.Model):
    """ Leader on the map, mainly followed for narrative: faction leaders,
    champions (heroes within units, allowing duels), players, menacing
    figures... Wounds and narrative status are tracked manually. """
    _name = 'battle.leader'
    _inherit = ['avatar.mixin', 'mail.thread']
    _description = "Leader"
    _order = 'battle_faction_sequence asc, is_faction_leader desc, name asc, id asc'

    name = fields.Char(required=True, translate=True)
    unit_type = fields.Selection(UNIT_TYPES, string="Type", tracking=True)
    image_1920 = fields.Image(compute='_compute_image_1920', store=True, readonly=False)
    battle_faction_id = fields.Many2one('battle.faction', string="Faction", tracking=True)
    battle_faction_sequence = fields.Integer("Faction Sequence", related='battle_faction_id.sequence', store=True)
    battle_location_id = fields.Many2one('battle.location', string="Location", tracking=True)
    # role
    led_faction_ids = fields.One2many('battle.faction', 'leader_id', string="Led Factions")
    is_faction_leader = fields.Boolean("Faction Leader", compute='_compute_is_faction_leader', store=True)
    is_champion = fields.Boolean("Champion", tracking=True, help="Hero fighting within a unit, allowing duels.")
    # state, tracked manually
    wound_state = fields.Selection(WOUND_STATES, string="Wounds", default='4', required=True, tracking=True)
    narrative_state = fields.Selection(
        NARRATIVE_STATES, string="Narrative Status", default='alive', required=True, tracking=True,
        help="Missing: missing in action.",
    )

    @api.depends('unit_type')
    def _compute_image_1920(self):
        for leader in self:
            leader.image_1920 = leader._get_leader_glyph()

    @api.depends('led_faction_ids')
    def _compute_is_faction_leader(self):
        for leader in self:
            leader.is_faction_leader = bool(leader.led_faction_ids)

    def _track_log_get_default_body(self, track_init_values):
        return self.env['battle.round']._get_tracking_body() or super()._track_log_get_default_body(track_init_values)

    def _get_leader_glyph(self):
        """ Unit type glyph, with a gold ringed circle instead of the square
        background: a leader, not a unit """
        if not self.unit_type:
            return False
        glyph = get_unit_type_glyph(self.unit_type)
        match = GLYPH_BACKGROUND.search(glyph)
        if match:
            glyph = glyph.replace(match.group(0), LEADER_BACKGROUND % match.group(1)).replace(b'</svg>', b'</g></svg>')
        return BinaryBytes(glyph, filename=f'{self.unit_type}_leader.svg')

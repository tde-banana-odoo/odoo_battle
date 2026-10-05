import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import BinaryBytes
from odoo.tools.misc import file_open

from odoo.addons.odoo_battle.const import UNIT_TYPES


# unit type glyphs: a colored square background, a light drawing
GLYPH_BACKGROUND = re.compile(rb'<rect width="180" height="180" fill="(#[0-9a-fA-F]{6})"/>')
GLYPH_DRAWING_COLOR = b'#f3ead8'


def get_unit_type_glyph(unit_type: str) -> bytes:
    """ SVG glyph of a unit type (square, colored background) """
    with file_open(f'odoo_battle/static/img/unit_type/{unit_type}.svg', 'rb') as glyph:
        return glyph.read()


def get_unit_type_print_glyph(unit_type: str) -> bytes:
    """ SVG glyph of a unit type for black and white printing: no
    background, dark drawing """
    glyph = GLYPH_BACKGROUND.sub(b'', get_unit_type_glyph(unit_type))
    return glyph.replace(GLYPH_DRAWING_COLOR, b'#222222')


class BattleUnitStatsMixin(models.AbstractModel):
    """ Type, image, statistics and traits of units, shared by units and
    templates. Image defaults to the unit type glyph. """
    _name = 'battle.unit.stats.mixin'
    _inherit = ['avatar.mixin']
    _description = "Unit Statistics"

    unit_type = fields.Selection(UNIT_TYPES, string="Unit Type", required=True)
    image_1920 = fields.Image(compute='_compute_image_1920', store=True, readonly=False)
    menace = fields.Integer()
    size = fields.Integer()
    rage = fields.Integer()
    willpower = fields.Integer()
    gnosis = fields.Integer()
    damage = fields.Integer()
    resistance = fields.Integer()
    battle_trait_ids = fields.Many2many('battle.trait', string="Traits", domain="[('target', '=', 'unit')]")

    @api.constrains('battle_trait_ids')
    def _check_battle_trait_ids(self):
        for record in self:
            if any(trait.target != 'unit' for trait in record.battle_trait_ids):
                raise ValidationError(_("%(unit_name)s can only have unit traits.", unit_name=record.display_name))

    @api.depends('unit_type')
    def _compute_image_1920(self):
        for record in self:
            record.image_1920 = record._get_unit_type_glyph()

    def _get_unit_type_glyph(self):
        if not self.unit_type:
            return False
        return BinaryBytes(get_unit_type_glyph(self.unit_type), filename=f'{self.unit_type}.svg')

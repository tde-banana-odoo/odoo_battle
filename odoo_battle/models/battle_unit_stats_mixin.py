from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import BinaryBytes
from odoo.tools.misc import file_open


class BattleUnitStatsMixin(models.AbstractModel):
    """ Type, image, statistics and traits of units, shared by units and
    templates. Image defaults to the unit type glyph. """
    _name = 'battle.unit.stats.mixin'
    _inherit = ['avatar.mixin']
    _description = "Unit Statistics"

    unit_type = fields.Selection(
        [
            ('werewolf', 'Werewolf'),
            ('bsd', 'Black Spiral Dancer'),
            ('vampire', 'Vampire'),
            ('ghoul', 'Ghoul'),
            ('human', 'Human'),
            ('human_armored', 'Armored Human'),
            ('spirit', 'Spirit'),
            ('possessed', 'Possessed'),
            ('fomori', 'Fomori'),
        ], string="Unit Type", required=True,
    )
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
            if len(record.battle_trait_ids) > 3:
                raise ValidationError(_("%(unit_name)s cannot have more than 3 traits.", unit_name=record.display_name))
            if any(trait.target != 'unit' for trait in record.battle_trait_ids):
                raise ValidationError(_("%(unit_name)s can only have unit traits.", unit_name=record.display_name))

    @api.depends('unit_type')
    def _compute_image_1920(self):
        for record in self:
            record.image_1920 = record._get_unit_type_glyph()

    def _get_unit_type_glyph(self):
        if not self.unit_type:
            return False
        with file_open(f'odoo_battle/static/img/unit_type/{self.unit_type}.svg', 'rb') as glyph:
            return BinaryBytes(glyph.read(), filename=f'{self.unit_type}.svg')

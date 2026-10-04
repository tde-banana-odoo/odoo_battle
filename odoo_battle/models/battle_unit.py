from odoo import api, fields, models


def _compute_from_template(fname):
    """ One compute per field: values given explicitly (e.g. at create or in
    data files) take precedence field by field, other values follow the
    template. Changing template resets values. """
    @api.depends('battle_unit_template_id')
    def _compute(self):
        for unit in self:
            template = unit.battle_unit_template_id
            unit[fname] = template[fname] if template else unit[fname]
    return _compute


def _template_field(field_type, fname):
    return field_type(compute=_compute_from_template(fname), store=True, readonly=False, precompute=True)


class BattleUnit(models.Model):
    _name = 'battle.unit'
    _inherit = ['battle.unit.stats.mixin', 'mail.thread']
    _description = "Unit"
    _order = 'battle_faction_sequence asc, unit_type asc, id asc'

    name = fields.Char(required=True, translate=True)
    origin = fields.Char(translate=True)
    is_dead = fields.Boolean("Dead", tracking=True, help="Dead units do not take part in battles anymore.")
    wound_state = fields.Selection(
        [('4', 'Unhurt'), ('3', 'Wounded'), ('2', 'Badly Wounded'), ('1', 'Critical'), ('0', 'Out of Combat')],
        string="Wounds", default='4', required=True, tracking=True,
        help="From 4 (unhurt) to 0: out of combat units do not take part in battles.",
    )
    is_fighting = fields.Boolean("Fighting", compute='_compute_is_fighting', store=True, help="Alive and not out of combat")
    battle_unit_template_id = fields.Many2one('battle.unit.template', string="Template", tracking=True)
    # type, statistics and traits: from template, editable
    unit_type = _template_field(fields.Selection, 'unit_type')
    menace = _template_field(fields.Integer, 'menace')
    size = _template_field(fields.Integer, 'size')
    rage = _template_field(fields.Integer, 'rage')
    willpower = _template_field(fields.Integer, 'willpower')
    gnosis = _template_field(fields.Integer, 'gnosis')
    damage = _template_field(fields.Integer, 'damage')
    resistance = _template_field(fields.Integer, 'resistance')
    battle_trait_ids = _template_field(fields.Many2many, 'battle_trait_ids')
    # ownership
    battle_faction_id = fields.Many2one('battle.faction', string="Faction", tracking=True)
    battle_faction_sequence = fields.Integer(
        "Faction Sequence", related='battle_faction_id.sequence', store=True,
    )
    # localization
    battle_location_id = fields.Many2one('battle.location', string="Location", tracking=True)

    @api.depends('is_dead', 'wound_state')
    def _compute_is_fighting(self):
        for unit in self:
            unit.is_fighting = not unit.is_dead and unit.wound_state != '0'

    @api.depends('battle_unit_template_id', 'unit_type')
    def _compute_image_1920(self):
        """ Template image, or unit type glyph """
        for unit in self:
            unit.image_1920 = unit.battle_unit_template_id.image_1920 or unit._get_unit_type_glyph()

    @api.depends('name', 'is_dead')
    def _compute_display_name(self):
        for unit in self:
            unit.display_name = f"{unit.name} †" if unit.is_dead else unit.name

    def _load_records(self, data_list, update=False):
        """ Data files (e.g. csv) only set values they fill: empty cells are
        loaded as False (while '0' gives 0) and skipped. New units then get
        template or default values, existing ones keep their current values
        (e.g. wounds updated during the game). """
        for data in data_list:
            data['values'] = {fname: value for fname, value in data['values'].items() if value is not False}
        return super()._load_records(data_list, update=update)

    def write(self, vals):
        # rewriting the same template (e.g. data update) should not reset tweaked values
        if 'battle_unit_template_id' in vals and all(
            unit.battle_unit_template_id.id == (vals['battle_unit_template_id'] or False) for unit in self
        ):
            vals = {fname: value for fname, value in vals.items() if fname != 'battle_unit_template_id'}
        return super().write(vals)

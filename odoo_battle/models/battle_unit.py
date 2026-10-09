from __future__ import annotations

import typing

from odoo import api, fields, models

from odoo.addons.odoo_battle.const import DAMAGE_PER_WOUND, WOUND_MALUSES, WOUND_STATES

if typing.TYPE_CHECKING:
    from odoo.addons.odoo_battle.const import UnitState


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
    """ Unit fighting for a faction in a location: statistics and traits
    (from its template, tweakable), wounds and damage counter evolving with
    battles. """
    _name = 'battle.unit'
    _inherit = ['battle.unit.stats.mixin', 'mail.thread']
    _description = "Unit"
    _order = 'battle_faction_sequence asc, unit_type asc, id asc'

    name = fields.Char(required=True, translate=True)
    origin = fields.Char(translate=True)
    is_dead = fields.Boolean("Dead", tracking=True, help="Dead units do not take part in battles anymore.")
    wound_state = fields.Selection(
        WOUND_STATES, string="Wounds", default='4', required=True, tracking=True,
        help="From 4 (unhurt) to 0: out of combat units do not take part in battles.",
    )
    damage_counter = fields.Integer(
        "Damage Counter", tracking=True,
        help=f"Accumulated damage (battles, fatigue, ...): every {DAMAGE_PER_WOUND} points, a wound is added.",
    )
    is_fighting = fields.Boolean("Fighting", compute='_compute_is_fighting', store=True, help="Alive and not out of combat")
    battle_unit_template_id = fields.Many2one('battle.unit.template', string="Template", tracking=True)
    template_short_name = fields.Char("Template Code", related='battle_unit_template_id.short_name', store=True)
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
        if 'battle_unit_template_id' in vals:
            template_id = vals['battle_unit_template_id'] or False
            if all(unit.battle_unit_template_id.id == template_id for unit in self):
                vals = {fname: value for fname, value in vals.items() if fname != 'battle_unit_template_id'}
        return super().write(vals)

    def _track_log_get_default_body(self, track_init_values):
        return self.env['battle.round']._get_tracking_body() or super()._track_log_get_default_body(track_init_values)

    def _update_damage_and_wounds(self, damage: int = 0, wounds: int = 0, heal: bool = False, mend: bool = False) -> None:
        """ Apply ``damage``, ``wounds``, then heal and mend on units, see
        ``_get_state_after`` """
        for unit in self:
            counter, wound_state = unit._get_state_after(unit.damage_counter, unit.wound_state, damage, wounds, heal, mend)
            if (counter, wound_state) != (unit.damage_counter, unit.wound_state):
                unit.write({'damage_counter': counter, 'wound_state': wound_state})

    def _get_wound_malus(self, stat: typing.Literal['characteristic', 'damage', 'resistance']) -> int:
        """ Battle malus given by the unit wounds on ``stat``, see
        WOUND_MALUSES; damage and resistance never go below 0 """
        self.ensure_one()
        malus = WOUND_MALUSES.get(self.wound_state, {}).get(stat, 0)
        if stat in ('damage', 'resistance'):
            return min(malus, max(self[stat], 0))
        return malus

    @api.model
    def _get_state_after(
        self, damage_counter: int, wound_state: str, damage: int = 0, wounds: int = 0, heal: bool = False, mend: bool = False,
    ) -> UnitState:
        """ (damage counter, wound state) after, in this order: receiving
        ``damage`` (every DAMAGE_PER_WOUND points add a wound and reset the
        counter), ``wounds`` (direct ones), then ``heal`` (one wound less) and
        ``mend`` (damage counter reset). Wounds go from unhurt (4) to out of
        combat (0). """
        damage_wounds, counter = divmod(max(0, damage_counter + damage), DAMAGE_PER_WOUND)
        state = max(0, min(4, int(wound_state) - damage_wounds))
        state = max(0, min(4, state - wounds))
        if heal:
            state = min(4, state + 1)
        if mend:
            counter = 0
        return counter, str(state)

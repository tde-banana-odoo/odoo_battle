import itertools
import random
from collections import Counter

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from odoo.addons.odoo_battle.models.battle_outcome import OUTCOME_SCORE_MAX, OUTCOME_SCORE_MIN
from odoo.addons.odoo_battle.models.battle_result import STANCES

# a battle is solved using a single throw of DICE_COUNT dice, each giving one of DICE_FACES
DICE_FACES = (-1, 0, 1)
DICE_COUNT = 3

SIDES = ('initiator', 'responder')


class BattleSolver(models.TransientModel):
    """ Solve a battle in a location between two sides: initiators, and
    responders (holders of the location and their allies). Each side chooses
    a stance (attack or defend). Results are given from initiators point of
    view. """
    _name = 'battle.solver'
    _description = "Battle Solver"

    battle_round_id = fields.Many2one(
        'battle.round', string="Round",
        default=lambda self: self.env['battle.round']._get_current(),
    )
    # localization
    battle_location_id = fields.Many2one(
        'battle.location', string="Location", required=True,
        default=lambda self: self._default_battle_location_id(),
        domain="[('is_external', '=', False)]",
    )
    battle_location_summary = fields.Html(
        "Location Summary", compute='_compute_battle_location_summary',
        sanitize=False,
    )
    # sides
    initiator_faction_ids = fields.Many2many(
        'battle.faction', 'battle_solver_initiator_faction_rel', 'solver_id', 'faction_id',
        string="Initiators", compute='_compute_faction_ids', store=True, readonly=False,
    )
    responder_faction_ids = fields.Many2many(
        'battle.faction', 'battle_solver_responder_faction_rel', 'solver_id', 'faction_id',
        string="Responders", compute='_compute_faction_ids', store=True, readonly=False,
    )
    initiator_stance = fields.Selection(STANCES, string="Initiators Stance", default='attack', required=True)
    responder_stance = fields.Selection(STANCES, string="Responders Stance", default='defense', required=True)
    # units
    initiator_unit_ids = fields.Many2many(
        'battle.unit', 'battle_solver_initiator_unit_rel', 'solver_id', 'unit_id',
        string="Initiator Units",
        compute='_compute_initiator_unit_ids', store=True, readonly=False,
        domain="[('battle_location_id', '=', battle_location_id), ('battle_faction_id', 'in', initiator_faction_ids), ('is_fighting', '=', True)]",
    )
    responder_unit_ids = fields.Many2many(
        'battle.unit', 'battle_solver_responder_unit_rel', 'solver_id', 'unit_id',
        string="Responder Units",
        compute='_compute_responder_unit_ids', store=True, readonly=False,
        domain="[('battle_location_id', '=', battle_location_id), ('battle_faction_id', 'in', responder_faction_ids), ('is_fighting', '=', True)]",
    )
    initiator_menace = fields.Integer("Initiators Menace", compute='_compute_menace')
    responder_menace = fields.Integer("Responders Menace", compute='_compute_menace')
    # bonuses
    initiator_bonus = fields.Integer("Initiators Bonus", compute='_compute_bonus')
    responder_bonus = fields.Integer("Responders Bonus", compute='_compute_bonus')
    bonus = fields.Integer(
        "Bonus", compute='_compute_bonus',
        help="Initiators bonus minus responders bonus, added to the dice roll.",
    )
    bonus_summary = fields.Html("Bonus Summary", compute='_compute_bonus', sanitize=False)
    simulation_summary = fields.Html("Simulation", compute='_compute_simulation_summary', sanitize=False)
    # result
    mode = fields.Selection(
        [('simulate', 'Simulation'), ('battle', 'Battle')],
        string="Mode", compute='_compute_result', store=True, readonly=False,
    )
    dice_roll = fields.Char("Dice Roll", compute='_compute_result', store=True, readonly=False)
    result_score = fields.Integer("Score", compute='_compute_result', store=True, readonly=False)
    battle_outcome_id = fields.Many2one(
        'battle.outcome', string="Outcome",
        compute='_compute_result', store=True, readonly=False,
    )
    damage_to_initiators = fields.Integer("Damage to Initiators", compute='_compute_result', store=True, readonly=False)
    damage_to_responders = fields.Integer("Damage to Responders", compute='_compute_result', store=True, readonly=False)
    result_message = fields.Text(
        "Result", compute='_compute_result', store=True, readonly=False,
    )
    result_summary = fields.Html("Result Summary", compute='_compute_result_summary', sanitize=False)
    battle_result_id = fields.Many2one('battle.result', string="Logged Result", readonly=True)
    existing_battle_result_id = fields.Many2one(
        'battle.result', string="Existing Result", compute='_compute_existing_battle_result_id',
        help="Battle already solved in this location for this round, replaced if battling again.",
    )

    def _default_battle_location_id(self):
        if self.env.context.get('active_model') == 'battle.location':
            return self.env.context.get('active_id')
        return False

    @api.depends('battle_location_id')
    def _compute_battle_location_summary(self):
        for solver in self:
            solver.battle_location_summary = self.env['ir.qweb']._render(
                'odoo_battle.battle_solver_location_summary',
                {'location': solver.battle_location_id},
            ) if solver.battle_location_id else False

    @api.depends('battle_round_id', 'battle_location_id', 'battle_result_id')
    def _compute_existing_battle_result_id(self):
        for solver in self:
            solver.existing_battle_result_id = self.env['battle.result'].search([
                ('battle_round_id', '=', solver.battle_round_id.id),
                ('battle_location_id', '=', solver.battle_location_id.id),
                ('state', '=', 'done'),
            ], limit=1) if solver.battle_round_id and solver.battle_location_id else False

    @api.depends('battle_location_id')
    def _compute_faction_ids(self):
        for solver in self:
            if solver.battle_location_id:
                solver.initiator_faction_ids, solver.responder_faction_ids = solver.battle_location_id._get_battle_sides()
            else:
                solver.initiator_faction_ids = solver.responder_faction_ids = False

    @api.depends('battle_location_id', 'initiator_faction_ids')
    def _compute_initiator_unit_ids(self):
        for solver in self:
            solver.initiator_unit_ids = solver._get_location_units(solver.initiator_faction_ids)

    @api.depends('battle_location_id', 'responder_faction_ids')
    def _compute_responder_unit_ids(self):
        for solver in self:
            solver.responder_unit_ids = solver._get_location_units(solver.responder_faction_ids)

    def _get_location_units(self, factions):
        """ Fighting units of ``factions`` in the location """
        self.ensure_one()
        if not self.battle_location_id or not factions:
            return self.env['battle.unit']
        return self.env['battle.unit'].search([
            ('battle_location_id', '=', self.battle_location_id.id),
            ('battle_faction_id', 'in', factions.ids),
            ('is_fighting', '=', True),
        ])

    @api.depends('initiator_unit_ids.menace', 'responder_unit_ids.menace')
    def _compute_menace(self):
        for solver in self:
            solver.initiator_menace = sum(solver.initiator_unit_ids.mapped('menace'))
            solver.responder_menace = sum(solver.responder_unit_ids.mapped('menace'))

    # note: changes on regular models (units, factions, location) do not
    # trigger recomputation on transient models, only a new request does
    @api.depends(
        'battle_location_id',
        'initiator_faction_ids', 'initiator_unit_ids', 'initiator_stance',
        'responder_faction_ids', 'responder_unit_ids', 'responder_stance',
    )
    def _compute_bonus(self):
        for solver in self:
            lines = solver._get_bonus_lines()
            solver.initiator_bonus = sum(line['initiator'] for line in lines)
            solver.responder_bonus = sum(line['responder'] for line in lines)
            solver.bonus = solver.initiator_bonus - solver.responder_bonus
            solver.bonus_summary = self.env['ir.qweb']._render(
                'odoo_battle.battle_solver_bonus_summary', {'solver': solver, 'lines': lines},
            )

    @api.depends('bonus')
    def _compute_simulation_summary(self):
        outcomes = self.env['battle.outcome'].search([])
        for solver in self:
            chances = solver._get_score_chances()
            solver.simulation_summary = self.env['ir.qweb']._render(
                'odoo_battle.battle_solver_simulation_summary',
                {'rows': [
                    (outcome, chances.get(outcome.score, 0), *solver._get_damage(outcome))
                    for outcome in outcomes
                ]},
            )

    @api.depends(
        'battle_location_id', 'initiator_unit_ids', 'responder_unit_ids',
        'initiator_stance', 'responder_stance',
    )
    def _compute_result(self):
        """ Changing sides invalidates any previous result """
        self.update(self._get_result_reset_values())

    @api.depends('mode', 'battle_outcome_id', 'result_message')
    def _compute_result_summary(self):
        for solver in self:
            solver.result_summary = self.env['ir.qweb']._render(
                'odoo_battle.battle_solver_result_summary', {'solver': solver},
            ) if solver.mode == 'battle' else False

    @api.model
    def _get_result_reset_values(self):
        return {
            'mode': False,
            'dice_roll': False,
            'result_score': 0,
            'battle_outcome_id': False,
            'damage_to_initiators': 0,
            'damage_to_responders': 0,
            'result_message': False,
        }

    # ------------------------------------------------------------
    # SIDES
    # ------------------------------------------------------------

    @api.model
    def _get_side_result(self, side, score):
        """ Result of ``side`` given the ``score`` (initiators point of view) """
        if score is None:
            return None
        if score == 0:
            return 'tie'
        return 'win' if (score > 0) == (side == 'initiator') else 'lose'

    # ------------------------------------------------------------
    # BONUSES
    # ------------------------------------------------------------

    def _get_bonus_lines(self):
        """ Bonus lines, each being a dict with category, name, detail, and
        bonus for initiators and responders. """
        self.ensure_one()
        initiators, responders = self.initiator_unit_ids, self.responder_unit_ids

        # opposing forces: Gnosis in Umbra, otherwise Rage when attacking and
        # Willpower when defending
        stat_initiator, stat_responder = (
            'gnosis' if self.battle_location_id.is_umbra
            else 'rage' if self[f'{side}_stance'] == 'attack' else 'willpower'
            for side in SIDES
        )
        stat_labels = {'gnosis': _("Gnosis"), 'rage': _("Rage"), 'willpower': _("Willpower")}
        value_initiator = sum(initiators.mapped(stat_initiator))
        value_responder = sum(responders.mapped(stat_responder))
        size_initiator, size_responder = sum(initiators.mapped('size')), sum(responders.mapped('size'))
        # leadership
        morale_initiator = self._get_side_morale(initiators, self.initiator_faction_ids)
        morale_responder = self._get_side_morale(responders, self.responder_faction_ids)
        morale_labels = dict(self.env['battle.faction']._fields['morale']._description_selection(self.env))

        return [
            self._bonus_line(
                'forces', _("Characteristics"),
                _("%(stat_initiator)s %(initiator)s vs %(stat_responder)s %(responder)s",
                  stat_initiator=stat_labels[stat_initiator], initiator=value_initiator,
                  stat_responder=stat_labels[stat_responder], responder=value_responder),
                *self._bonus_more_or_double(value_initiator, value_responder),
            ),
            self._bonus_line(
                'forces', _("Size"),
                _("%(initiator)s vs %(responder)s", initiator=size_initiator, responder=size_responder),
                *self._bonus_per_half_more(size_initiator, size_responder),
            ),
            self._bonus_line(
                'leadership', _("Morale"),
                _("%(initiator)s vs %(responder)s", initiator=morale_labels[str(morale_initiator)], responder=morale_labels[str(morale_responder)]),
                -1 if morale_initiator <= 2 else 0, -1 if morale_responder <= 2 else 0,
            ),
        ] + self._get_trait_bonus_lines()

    def _get_trait_bonus_lines(self):
        """ One line per trait giving a battle bonus to at least one side,
        location traits first """
        traits_by_side = {side: self._get_side_traits(side) for side in SIDES}
        traits = self.env['battle.trait'].union(*traits_by_side['initiator'], *traits_by_side['responder'])
        lines = []
        for trait in traits.sorted(lambda trait: (trait.target != 'location', trait.sequence, trait.id)):
            if trait.effect != 'bonus':
                continue
            values = [self._get_trait_value(trait, side, traits_by_side[side].get(trait, 0)) for side in SIDES]
            if any(values):
                lines.append(self._bonus_line(
                    'location' if trait.target == 'location' else 'traits', trait.name,
                    _("%(initiator)s vs %(responder)s",
                      initiator=traits_by_side['initiator'].get(trait, 0),
                      responder=traits_by_side['responder'].get(trait, 0)),
                    *values,
                ))
        return lines

    @api.model
    def _bonus_line(self, category, name, detail, initiator, responder):
        return {'category': category, 'name': name, 'detail': detail, 'initiator': initiator, 'responder': responder}

    @api.model
    def _bonus_more_or_double(self, initiator, responder):
        """ +1 to the side having more, +2 if more than double. A positive
        value is considered more than double a null or negative one. """
        if initiator == responder:
            return 0, 0
        high, low = max(initiator, responder), min(initiator, responder)
        bonus = 2 if (high > 2 * low if low > 0 else high > 0) else 1
        return (bonus, 0) if initiator > responder else (0, bonus)

    @api.model
    def _bonus_per_half_more(self, initiator, responder):
        """ +1 per 50% more to the side having more, max +2 """
        if initiator == responder:
            return 0, 0
        high, low = max(initiator, responder), min(initiator, responder)
        bonus = min(2, (2 * (high - low)) // low) if low > 0 else 2
        return (bonus, 0) if initiator > responder else (0, bonus)

    @api.model
    def _get_side_morale(self, units, factions):
        """ Morale (0 to 4) of the faction having most units in the side
        (first faction in case of tie), defaulting to the first side faction. """
        counts = Counter(unit.battle_faction_id for unit in units if unit.battle_faction_id)
        faction = max(units.battle_faction_id.sorted(), key=lambda f: counts[f]) if counts else factions.sorted()[:1]
        return int(faction.morale or 3)

    # ------------------------------------------------------------
    # TRAITS AND DAMAGE
    # ------------------------------------------------------------

    def _get_side_traits(self, side):
        """ Traits of a side ('initiator' or 'responder'): its units traits,
        and location traits. Returns a Counter {trait: number of holders}. """
        self.ensure_one()
        traits = Counter(trait for unit in self[f'{side}_unit_ids'] for trait in unit.battle_trait_ids)
        traits.update(self.battle_location_id.battle_trait_ids)
        return traits

    def _get_trait_value(self, trait, side, count, score=None):
        """ Value given by ``count`` holders of ``trait`` for ``side``,
        given the battle ``score`` if known. """
        self.ensure_one()
        if not count or not trait._applies(side, self[f'{side}_stance'], self._get_side_result(side, score)):
            return 0
        return trait.value * (1 if trait.is_unique else count)

    def _get_side_trait_value(self, side, effect, score=None):
        return sum(
            self._get_trait_value(trait, side, count, score)
            for trait, count in self._get_side_traits(side).items()
            if trait.effect == effect
        )

    def _get_side_damage(self, side, outcome):
        """ Damage dealt by a side: its units damage when attacking (nothing
        when defending), plus outcome and traits. """
        base = sum(self[f'{side}_unit_ids'].mapped('damage')) if self[f'{side}_stance'] == 'attack' else 0
        return base + outcome[f'{side}_damage'] + self._get_side_trait_value(side, 'damage', outcome.score)

    def _get_side_resistance(self, side, outcome):
        return sum(self[f'{side}_unit_ids'].mapped('resistance')) + outcome[f'{side}_resistance']

    def _get_damage(self, outcome):
        """ Damage dealt for a given outcome, as (to responders, to initiators):
        damage of a side minus resistance of the other side, at least 0. """
        self.ensure_one()
        return (
            max(0, self._get_side_damage('initiator', outcome) - self._get_side_resistance('responder', outcome)),
            max(0, self._get_side_damage('responder', outcome) - self._get_side_resistance('initiator', outcome)),
        )

    # ------------------------------------------------------------
    # DICE
    # ------------------------------------------------------------

    @api.model
    def _get_roll_chances(self):
        """ Probability of each dice roll total """
        totals = Counter(sum(roll) for roll in itertools.product(DICE_FACES, repeat=DICE_COUNT))
        count = len(DICE_FACES) ** DICE_COUNT
        return {total: occurrences / count for total, occurrences in totals.items()}

    def _get_score_chances(self):
        """ Probability of each final score, given current bonus """
        self.ensure_one()
        chances = Counter()
        for total, chance in self._get_roll_chances().items():
            chances[self._get_score(total)] += chance
        return dict(chances)

    def _get_score(self, roll_total):
        self.ensure_one()
        return max(OUTCOME_SCORE_MIN, min(OUTCOME_SCORE_MAX, self.bonus + roll_total))

    @api.model
    def _roll_dice(self):
        return [random.choice(DICE_FACES) for _dice in range(DICE_COUNT)]

    # ------------------------------------------------------------
    # ACTIONS
    # ------------------------------------------------------------

    def action_simulate(self):
        """ Display every possible outcome with its probability """
        self._check_battle()
        self.write({**self._get_result_reset_values(), 'mode': 'simulate'})
        return self._action_reopen()

    def action_battle(self):
        """ Roll the dice """
        # TDE TODO: apply battle consequences on units
        self._check_battle()
        if any(not solver.battle_round_id for solver in self):
            raise UserError(_("Battles are logged in a round: please create one first."))
        outcomes = self.env['battle.outcome'].search([])
        for solver in self:
            roll = solver._roll_dice()
            score = solver._get_score(sum(roll))
            outcome = outcomes.filtered(lambda o: o.score == score)
            to_responders, to_initiators = solver._get_damage(outcome)
            dice_roll = ' '.join(f'{value:+d}' for value in roll)
            solver.write({
                'mode': 'battle',
                'dice_roll': dice_roll,
                'result_score': score,
                'battle_outcome_id': outcome.id,
                'damage_to_initiators': to_initiators,
                'damage_to_responders': to_responders,
                'result_message': _(
                    "Roll %(roll)s (%(total)+d), bonus %(bonus)+d, score %(score)+d. "
                    "Damage: %(to_responders)s to %(responders)s, %(to_initiators)s to %(initiators)s.",
                    roll=dice_roll, total=sum(roll), bonus=solver.bonus, score=score,
                    initiators=', '.join(solver.initiator_faction_ids.sorted().mapped('name')),
                    responders=', '.join(solver.responder_faction_ids.sorted().mapped('name')),
                    to_responders=to_responders, to_initiators=to_initiators,
                ),
            })
            # replace result already solved for this round, if any
            solver.existing_battle_result_id.action_cancel()
            self.env['battle.result'].flush_model(['state'])
            solver.battle_result_id = self.env['battle.result'].create(solver._prepare_battle_result_values())
        return self._action_reopen()

    def _prepare_battle_result_values(self):
        self.ensure_one()
        return {
            'battle_round_id': self.battle_round_id.id,
            'battle_location_id': self.battle_location_id.id,
            **{
                fname: self[fname].ids if self._fields[fname].type == 'many2many' else self[fname]
                for side in SIDES
                for fname in (f'{side}_faction_ids', f'{side}_stance', f'{side}_unit_ids')
            },
            'bonus': self.bonus,
            'dice_roll': self.dice_roll,
            'result_score': self.result_score,
            'battle_outcome_id': self.battle_outcome_id.id,
            'damage_to_initiators': self.damage_to_initiators,
            'damage_to_responders': self.damage_to_responders,
            'result_message': self.result_message,
        }

    def _check_battle(self):
        for solver in self:
            if solver.battle_location_id.is_external:
                raise UserError(_("No battle can take place in %s, which is off the battlefield.", solver.battle_location_id.name))
            if not solver.initiator_faction_ids or not solver.responder_faction_ids:
                raise UserError(_("A battle requires initiator and responder factions."))
            if solver.initiator_faction_ids & solver.responder_faction_ids:
                raise UserError(_("A faction cannot fight on both sides."))
            if not solver.initiator_unit_ids or not solver.responder_unit_ids:
                raise UserError(_("A battle requires units on both sides."))
            if solver.initiator_unit_ids & solver.responder_unit_ids:
                raise UserError(_("A unit cannot fight on both sides."))

    def _action_reopen(self):
        """ Keep the wizard open to display the result """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Battle Solver"),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

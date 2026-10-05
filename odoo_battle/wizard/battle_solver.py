from __future__ import annotations

import itertools
import random
import typing
from collections import Counter

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.fields import Command

from odoo.addons.odoo_battle.const import (
    COMMAND_BONUS,
    COMMAND_RATES,
    COMMAND_STANCES,
    DAMAGE_PER_WOUND,
    DICE_COUNT,
    DICE_FACES,
    LOCATION_STATUSES,
    OUTCOME_SCORE_MAX,
    OUTCOME_SCORE_MIN,
    SIDE_SELECTION,
    SIDES,
    STANCES,
)

if typing.TYPE_CHECKING:
    from odoo.addons.odoo_battle.const import Camp, Side, SideResult, UnitState
    from odoo.addons.odoo_battle.models.battle_command_action import BattleCommandAction
    from odoo.addons.odoo_battle.models.battle_faction import BattleFaction
    from odoo.addons.odoo_battle.models.battle_outcome import BattleOutcome
    from odoo.addons.odoo_battle.models.battle_trait import BattleTrait
    from odoo.addons.odoo_battle.models.battle_unit import BattleUnit
    from odoo.addons.odoo_battle.wizard.battle_solver_line import BattleSolverLine

    # units state, simulated while computing consequences
    type LinesState = dict[BattleSolverLine, UnitState]
    # why a line is out of the battle (or False): manually excluded, ambushed, killed by an assassin
    type OutReason = typing.Literal['excluded', 'ambushed', 'killed', False]

# lines changes impacting sides: units, positions, units out of the battle (manually, ambushed or killed)
LINES_DEPENDS = [
    f'{side}_line_ids.{fname}'
    for side in SIDES
    for fname in ('battle_unit_id', 'position', 'is_excluded', 'target_unit_id')
]


class StatBreakdown(typing.TypedDict):
    """ How a side damage or resistance is computed, e.g. damage
    9 x 150% (Victory, Attack) x 150% (Full Attack) = 20, +6 Fureur -> 26 """
    frontline: int  # frontline units total, minus wounds maluses
    wound_malus: int  # wounds maluses of frontline units
    rates: list[tuple[str, int]]  # (label, rate %) applied on frontline: outcome, command actions
    base: int  # frontline after rates
    bonuses: list[tuple[str, int]]  # (label, value) added after rates: traits, support damage / resistance
    total: int


class BonusLine(typing.TypedDict):
    """ Line of the bonus summary, e.g. 'Size', '10 vs 5', +1 / 0 """
    category: str  # forces, leadership, location or traits
    name: str
    detail: str
    initiator: int
    responder: int


class BattleSolver(models.TransientModel):
    """ Solve a battle in a location between two sides: initiators, and
    responders (holders of the location and their allies, or the defender
    camp). Each side chooses a stance (attack or defend), and its units are in
    frontline or in support (second line), or out of the battle.

    Before rolling, characteristics (minus wounds maluses, plus a DM bonus),
    size, camp leadership (morale, command actions) and traits give each side
    a bonus; their difference is added to the dice roll, giving a score (from
    initiators point of view) and its outcome. Each side reads its own outcome
    (initiators the score, responders its opposite) for its stance: rates of
    its damage and resistance, traits granted for the next round.

    Flow: simulate (chances of each outcome), launch (roll, compute outcome
    and consequences on units and location, to check and tweak), then apply
    (update units and location, log a ``battle.result``). """
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
    battle_location_traits = fields.Html(
        "Location Traits", compute='_compute_battle_location_summary',
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
    initiator_characteristic_bonus = fields.Integer(
        "Initiators Characteristic Bonus",
        help="Bonus given by the DM to the compared characteristic of the side, e.g. +2 Willpower for a good defense idea.",
    )
    responder_characteristic_bonus = fields.Integer(
        "Responders Characteristic Bonus",
        help="Bonus given by the DM to the compared characteristic of the side, e.g. +2 Willpower for a good defense idea.",
    )
    # units, each in frontline or support
    initiator_line_ids = fields.One2many(
        'battle.solver.line', 'battle_solver_id', string="Initiator Units", domain=[('side', '=', 'initiator')],
        compute='_compute_initiator_line_ids', store=True, readonly=False,
    )
    responder_line_ids = fields.One2many(
        'battle.solver.line', 'battle_solver_id', string="Responder Units", domain=[('side', '=', 'responder')],
        compute='_compute_responder_line_ids', store=True, readonly=False,
    )
    initiator_menace = fields.Integer("Initiators Menace", compute='_compute_menace')
    responder_menace = fields.Integer("Responders Menace", compute='_compute_menace')
    initiator_folded = fields.Boolean("Fold Initiators")
    responder_folded = fields.Boolean("Fold Responders")
    initiator_lines_summary = fields.Char("Initiators Units", compute='_compute_lines_summary')
    responder_lines_summary = fields.Char("Responders Units", compute='_compute_lines_summary')
    # bonuses
    initiator_bonus = fields.Integer("Initiators Bonus", compute='_compute_bonus')
    responder_bonus = fields.Integer("Responders Bonus", compute='_compute_bonus')
    bonus = fields.Integer(
        "Bonus", compute='_compute_bonus',
        help="Initiators bonus minus responders bonus, added to the dice roll.",
    )
    bonus_summary = fields.Html("Bonus Summary", compute='_compute_bonus', sanitize=False)
    simulation_summary = fields.Html("Simulation", compute='_compute_simulation_summary', sanitize=False)
    initiator_rerolls = fields.Integer("Initiators Rerolls", compute='_compute_bonus', help="Dice the side may reroll (e.g. Tactique)")
    responder_rerolls = fields.Integer("Responders Rerolls", compute='_compute_bonus', help="Dice the side may reroll (e.g. Tactique)")
    initiator_forced_rerolls = fields.Integer(
        "Initiators Forced Rerolls", compute='_compute_bonus',
        help="Highest dice to reroll (e.g. Moral Vacillant), applied when the solver rolls.",
    )
    responder_forced_rerolls = fields.Integer(
        "Responders Forced Rerolls", compute='_compute_bonus',
        help="Lowest dice to reroll (e.g. Moral Vacillant), applied when the solver rolls.",
    )
    # dice, entered from the table or rolled
    dice_input = fields.Char(
        "Dice", help=f"{DICE_COUNT} dice values among {', '.join(f'{face:+d}' for face in DICE_FACES)}, e.g. '-1 0 +1'. "
                     "Leave empty to roll when launching the battle.",
    )
    dice_input_preview = fields.Char("Dice Preview", compute='_compute_dice_input_preview')
    # result
    mode = fields.Selection(
        [('simulate', 'Simulation'), ('launched', 'Launched'), ('done', 'Applied')],
        string="Mode",
        help="Launched: outcome and consequences computed, to check (and tweak) before applying them.",
    )
    dice_roll = fields.Char("Dice Roll")
    result_score = fields.Integer("Score")
    battle_outcome_id = fields.Many2one(
        'battle.outcome', string="Outcome",
    )
    damage_to_initiators = fields.Integer("Damage to Initiators")
    damage_to_responders = fields.Integer("Damage to Responders")
    result_message = fields.Text("Result")
    # what the battle looked like when simulated / launched: changing it afterwards outdates them
    battle_signature = fields.Char("Battle Signature")
    is_outdated = fields.Boolean(
        "Outdated", compute='_compute_is_outdated',
        help="Sides, stances or units changed since the battle was simulated or launched: do it again.",
    )
    result_summary = fields.Html("Result Summary", compute='_compute_result_summary', sanitize=False)
    # consequences on the location, computed when launching, applied with units ones
    location_status_after = fields.Selection(LOCATION_STATUSES, string="Location Status After")
    held_by_faction_after_id = fields.Many2one('battle.faction', string="Held By After")
    initiator_granted_trait_ids = fields.Many2many(
        'battle.trait', 'battle_solver_initiator_granted_trait_rel', 'solver_id', 'trait_id',
        string="Initiators Granted Traits", domain="[('target', '=', 'location')]",
        help="Location traits granted to initiators factions here for the next round.",
    )
    responder_granted_trait_ids = fields.Many2many(
        'battle.trait', 'battle_solver_responder_granted_trait_rel', 'solver_id', 'trait_id',
        string="Responders Granted Traits", domain="[('target', '=', 'location')]",
        help="Location traits granted to responders factions here for the next round.",
    )
    # units healed (one wound less) and mended (damage counter reset) after the battle, prefilled when launching
    battle_unit_ids = fields.Many2many('battle.unit', string="Units in Battle", compute='_compute_battle_unit_ids')
    heal_unit_ids = fields.Many2many(
        'battle.unit', 'battle_solver_heal_unit_rel', 'solver_id', 'unit_id', string="Heal",
        help="Units with one wound less after the battle: prefilled from Heal Self traits, change at will (e.g. role-play).",
    )
    mend_unit_ids = fields.Many2many(
        'battle.unit', 'battle_solver_mend_unit_rel', 'solver_id', 'unit_id', string="Mend",
        help="Units with their damage counter reset after the battle: prefilled from Mend Self traits, change at will.",
    )
    # logged result, and results already logged here for this round
    battle_result_id = fields.Many2one('battle.result', string="Logged Result", readonly=True)
    existing_battle_result_id = fields.Many2one(
        'battle.result', string="Existing Result", compute='_compute_existing_battle_result_id',
        help="Battle already solved in this location for this round: cancel it to battle again.",
    )
    cancelled_result_count = fields.Integer("Cancelled Results", compute='_compute_existing_battle_result_id')

    def _default_battle_location_id(self):
        if self.env.context.get('active_model') == 'battle.location':
            return self.env.context.get('active_id')
        return False

    @api.depends('battle_location_id', 'battle_round_id')
    def _compute_battle_location_summary(self):
        """ Location status (holder, Umbra, twin), next to the location; then
        its traits with their rules, and effects applying this round """
        for solver in self:
            location = solver.battle_location_id
            if not location:
                solver.battle_location_summary = solver.battle_location_traits = False
                continue
            values = {
                'location': location,
                'effects': location._get_round_effects(solver.battle_round_id.round_number),
            }
            solver.battle_location_summary = self.env['ir.qweb']._render('odoo_battle.battle_solver_location_summary', values)
            solver.battle_location_traits = self.env['ir.qweb']._render('odoo_battle.battle_solver_location_traits', values)

    @api.depends('battle_location_id', 'battle_round_id')
    def _compute_faction_ids(self):
        """ Sides from the location, or from the battle already solved here
        (as the location may have shifted since) """
        for solver in self:
            if solver.existing_battle_result_id:
                solver.initiator_faction_ids = solver.existing_battle_result_id.initiator_faction_ids
                solver.responder_faction_ids = solver.existing_battle_result_id.responder_faction_ids
            elif solver.battle_location_id:
                solver.initiator_faction_ids, solver.responder_faction_ids = solver.battle_location_id._get_battle_sides()
            else:
                solver.initiator_faction_ids = solver.responder_faction_ids = False

    @api.depends('battle_location_id', 'initiator_faction_ids')
    def _compute_initiator_line_ids(self):
        for solver in self:
            solver.initiator_line_ids = solver._get_line_commands('initiator')

    @api.depends('battle_location_id', 'responder_faction_ids')
    def _compute_responder_line_ids(self):
        for solver in self:
            solver.responder_line_ids = solver._get_line_commands('responder')

    @api.depends(*LINES_DEPENDS)
    def _compute_menace(self):
        for solver in self:
            for side in SIDES:
                solver[f'{side}_menace'] = sum(solver._get_units(side).mapped('menace'))

    @api.depends('initiator_line_ids.battle_unit_id', 'responder_line_ids.battle_unit_id')
    def _compute_battle_unit_ids(self):
        for solver in self:
            solver.battle_unit_ids = (solver.initiator_line_ids + solver.responder_line_ids).battle_unit_id

    @api.depends(*LINES_DEPENDS)
    def _compute_lines_summary(self):
        """ One line summary of each side units, displayed when folded """
        for solver in self:
            for side in SIDES:
                lines = solver[f'{side}_line_ids']
                active = solver._get_lines(side)
                support = active.filtered(lambda line: line.position == 'support')
                out = lines - active
                waiting = lines.filtered('needs_target')
                parts = [_("%(count)s units", count=len(lines))]
                if support:
                    parts.append(_("%(count)s in support", count=len(support)))
                if out:
                    parts.append(_("%(count)s out", count=len(out)))
                if waiting:
                    parts.append(_("%(count)s waiting for a target", count=len(waiting)))
                solver[f'{side}_lines_summary'] = ', '.join(parts)

    # note: changes on regular models (units, factions, location) do not
    # trigger recomputation on transient models, only a new request does
    @api.depends(
        'battle_location_id', 'initiator_faction_ids', 'initiator_stance', 'responder_faction_ids', 'responder_stance',
        'initiator_characteristic_bonus', 'responder_characteristic_bonus', *LINES_DEPENDS,
    )
    def _compute_bonus(self):
        for solver in self:
            lines = solver._get_bonus_lines()
            solver.initiator_bonus = sum(line['initiator'] for line in lines)
            solver.responder_bonus = sum(line['responder'] for line in lines)
            solver.bonus = solver.initiator_bonus - solver.responder_bonus
            for side in SIDES:
                solver[f'{side}_rerolls'] = solver._get_side_trait_value(side, 'reroll')
                solver[f'{side}_forced_rerolls'] = solver._get_side_trait_value(side, 'forced_reroll')
            solver.bonus_summary = self.env['ir.qweb']._render(
                'odoo_battle.battle_solver_bonus_summary', {'solver': solver, 'lines': lines},
            )

    @api.depends('bonus', *LINES_DEPENDS)
    def _compute_simulation_summary(self):
        outcomes = self.env['battle.outcome'].search([])  # all, ordered by score
        for solver in self:
            chances = solver._get_score_chances()
            rows = [(outcome, chances.get(outcome.score, 0), *solver._get_damage(outcome)) for outcome in outcomes]
            solver.simulation_summary = self.env['ir.qweb']._render(
                'odoo_battle.battle_solver_simulation_summary', {'rows': rows},
            )

    @api.depends(
        'mode', 'battle_signature', 'battle_location_id', 'initiator_stance', 'responder_stance',
        'initiator_characteristic_bonus', 'responder_characteristic_bonus', *LINES_DEPENDS,
    )
    def _compute_is_outdated(self):
        """ A simulation or launched battle is outdated when sides, stances or
        units changed since; tweaking consequences (damage, wounds, heal,
        mend) does not outdate it """
        for solver in self:
            solver.is_outdated = solver.mode in ('simulate', 'launched') and solver.battle_signature != solver._get_battle_signature()

    @api.depends('mode', 'battle_outcome_id', 'result_message', 'battle_result_id')
    def _compute_result_summary(self):
        for solver in self:
            if solver.mode in ('launched', 'done'):
                solver.result_summary = self.env['ir.qweb']._render('odoo_battle.battle_solver_result_summary', {
                    'solver': solver,
                    'lore_reminders': solver._get_lore_reminders(),
                    'heal_mend_reminders': solver._get_heal_mend_reminders(),
                })
            else:
                solver.result_summary = False

    @api.depends('dice_input', 'bonus')
    def _compute_dice_input_preview(self):
        outcomes = self.env['battle.outcome']._get_by_score()
        for solver in self:
            if not solver.dice_input:
                solver.dice_input_preview = False
                continue
            try:
                score = solver._get_score(sum(solver._parse_dice(solver.dice_input)))
            except UserError as error:
                solver.dice_input_preview = str(error)
            else:
                outcome_name = outcomes[score].name if score in outcomes else ''
                solver.dice_input_preview = _("Score %(score)+d: %(outcome)s", score=score, outcome=outcome_name)

    @api.depends('battle_round_id', 'battle_location_id', 'battle_result_id')
    def _compute_existing_battle_result_id(self):
        for solver in self:
            results = self.env['battle.result']
            if solver.battle_round_id and solver.battle_location_id:
                results = results.search([
                    ('battle_round_id', '=', solver.battle_round_id.id),
                    ('battle_location_id', '=', solver.battle_location_id.id),
                ])
            solver.existing_battle_result_id = results.filtered(lambda result: result.state == 'done')[:1]
            solver.cancelled_result_count = len(results.filtered(lambda result: result.state == 'cancel'))

    # ------------------------------------------------------------
    # ACTIONS
    # ------------------------------------------------------------

    def action_simulate(self):
        """ Display every possible outcome with its probability """
        self._check_battle()
        for solver in self:
            solver.write({**self._get_result_reset_values(), 'mode': 'simulate', 'battle_signature': solver._get_battle_signature()})
        return self._get_reopen_action()

    def action_roll(self):
        """ Roll the dice (applying forced rerolls) and fill them, so they can
        be checked (and some of them rerolled, e.g. Tactique) before launching
        the battle """
        for solver in self:
            solver.dice_input = solver._format_dice(solver._roll_battle_dice())
        return self._get_reopen_action()

    def action_launch(self):
        """ Launch the battle with entered dice (rolled if not given): compute
        its score, outcome and damage, then its consequences on units (damage
        and wounds of each line) and location (status after, granted traits),
        stored on the solver to be checked (and tweaked) before applying them
        (see ``action_apply``). Can be launched again until applied. """
        self._check_battle()
        self._check_launch()
        outcomes = self.env['battle.outcome']._get_by_score()
        for solver in self:
            if solver.dice_input:
                roll = solver._parse_dice(solver.dice_input)
            else:
                roll = solver._roll_battle_dice()
            score = solver._get_score(sum(roll))
            outcome = outcomes[score]
            to_responders, to_initiators = solver._get_damage(outcome)
            dice_roll = solver._format_dice(roll)
            solver.write({
                'mode': 'launched',
                'battle_signature': solver._get_battle_signature(),
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
                ) + '\n' + '\n'.join(solver._get_damage_details(outcome)),
                **solver._get_location_consequences(outcome),
            })
            consequences = solver._get_unit_consequences(outcome)
            heal_lines, mend_lines = solver._get_heal_mend_prefill(outcome, consequences)
            solver.write({
                'heal_unit_ids': [Command.set(heal_lines.battle_unit_id.ids)],
                'mend_unit_ids': [Command.set(mend_lines.battle_unit_id.ids)],
            })
            for line, (damage, wounds) in consequences.items():
                line.write({'damage_received': damage, 'wounds_received': wounds})
        return self._get_reopen_action()

    def action_apply(self):
        """ Apply the launched battle consequences, as checked (and tweaked):
        damage and wounds on units, location status, then log the result with
        units state before the battle and effects granted for the next round,
        allowing to cancel (revert) it. """
        self._check_apply()
        for solver in self:
            result_values = solver._prepare_battle_result_values()  # before updating, to log states before the battle
            solver._update_units()
            solver._update_location()
            result = self.env['battle.result'].create(result_values)
            solver.write({'mode': 'done', 'battle_result_id': result.id})
        return self._get_reopen_action()

    def action_cancel_existing_result(self):
        """ Cancel the battle already solved here for this round (reverting
        its consequences on units and location), and start again with a fresh
        solver """
        self.ensure_one()
        self.existing_battle_result_id.action_cancel()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Battle Solver"),
            'res_model': self._name,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_model': 'battle.location',
                'active_id': self.battle_location_id.id,
                'default_battle_round_id': self.battle_round_id.id,
            },
        }

    # ------------------------------------------------------------
    # CHECKS
    # ------------------------------------------------------------

    def _check_battle(self):
        """ A battle requires a location on the battlefield, two complete and
        distinct sides, and for each side a support not larger (in size) than
        its frontline """
        for solver in self:
            if solver.battle_location_id.is_external:
                raise UserError(_("No battle can take place in %(location_name)s, which is off the battlefield.", location_name=solver.battle_location_id.name))
            if not solver.initiator_faction_ids or not solver.responder_faction_ids:
                raise UserError(_("A battle requires initiator and responder factions."))
            if solver.initiator_faction_ids & solver.responder_faction_ids:
                raise UserError(_("A faction cannot fight on both sides."))
            if not solver._get_units('initiator') or not solver._get_units('responder'):
                raise UserError(_("A battle requires units on both sides."))
            if solver._get_units('initiator') & solver._get_units('responder'):
                raise UserError(_("A unit cannot fight on both sides."))
            for side in SIDES:
                lines = solver._get_lines(side)
                support = sum(lines.filtered(lambda line: line.position == 'support').battle_unit_id.mapped('size'))
                frontline = sum(lines.filtered(lambda line: line.position == 'frontline').battle_unit_id.mapped('size'))
                if support > frontline:
                    raise UserError(_(
                        "%(side)s: support size (%(support)s) cannot exceed frontline size (%(frontline)s).",
                        side=dict(SIDE_SELECTION)[side], support=support, frontline=frontline,
                    ))

    def _check_launch(self):
        """ A battle is launched in a round, once per location: an already
        applied battle, or a result already logged here, prevent it """
        for solver in self:
            if not solver.battle_round_id:
                raise UserError(_("Battles are logged in a round: please create one first."))
            if solver.mode == 'done':
                raise UserError(_("This battle is already applied."))
            if solver.existing_battle_result_id:
                raise UserError(_("A battle has already been solved here for this round: cancel it first."))

    def _check_apply(self):
        """ Only a launched battle can be applied, if not outdated (sides or
        units changed since) and if no result has been logged here
        meanwhile """
        for solver in self:
            if solver.mode != 'launched':
                raise UserError(_("Launch the battle first, to check its consequences before applying them."))
            if solver.is_outdated:
                raise UserError(_("Sides, stances or units changed since the battle was launched: launch it again."))
            if solver.existing_battle_result_id:
                raise UserError(_("A battle has already been solved here for this round: cancel it first."))

    # ------------------------------------------------------------
    # CONSEQUENCES
    # ------------------------------------------------------------

    def _get_unit_consequences(self, outcome: BattleOutcome) -> dict[BattleSolverLine, tuple[int, int]]:
        """ Consequences of ``outcome`` on units, without applying them, as
        {line: (damage, wounds)} for all lines (out of battle ones included):
        assassinations first, then damage spread evenly on frontline units
        first, wound traits on enemy units the same way. Wounds are direct
        ones, damage adding its own every DAMAGE_PER_WOUND points. Heal and
        mend come after, see ``_get_heal_mend_prefill``.

        Units state is simulated along the way, as each step depends on the
        previous ones (e.g. a unit put out of combat is not hit anymore). """
        self.ensure_one()
        Unit = self.env['battle.unit']
        all_lines = self.initiator_line_ids + self.responder_line_ids
        state = self._get_lines_state(all_lines)
        damage, wounds = Counter(), Counter()

        def hurt(line: BattleSolverLine, line_damage: int = 0, line_wounds: int = 0) -> None:
            state[line] = Unit._get_state_after(*state[line], line_damage, line_wounds)
            damage[line] += line_damage
            wounds[line] += line_wounds

        # everything is computed before hurting, as wounds change active units
        assassinations = {line: pre_wounds for line, (pre_wounds, _reason) in self._get_line_states().items() if pre_wounds}
        side_lines = {side: self._get_lines(side) for side in SIDES}
        to_responders, to_initiators = self._get_damage(outcome)
        trait_wounds = {side: self._get_side_trait_value(side, 'wound_enemy', outcome.score) for side in SIDES}

        for line, pre_wounds in assassinations.items():
            hurt(line, line_wounds=pre_wounds)
        for side, enemy, side_damage in (('responder', 'initiator', to_responders), ('initiator', 'responder', to_initiators)):
            lines = side_lines[side]
            for line, line_damage in self._get_damage_distribution(lines, side_damage, state).items():
                hurt(line, line_damage=line_damage)
            for _wound in range(trait_wounds[enemy]):
                targets = self._get_wound_targets(lines, state)
                if targets:
                    hurt(targets[0], line_wounds=1)
        return {line: (damage[line], wounds[line]) for line in all_lines}

    def _get_heal_mend_prefill(
        self, outcome: BattleOutcome, consequences: dict[BattleSolverLine, tuple[int, int]],
    ) -> tuple[BattleSolverLine, BattleSolverLine]:
        """ Lines to heal (one wound less) and to mend (damage counter reset)
        after the battle, as asked by the Heal Self / Mend Self traits of each
        side, one unit per value point: most wounded / most damaged ones
        after the battle ``consequences`` first. A prefill, changed at will
        in the solver (e.g. role-play). """
        self.ensure_one()
        Unit = self.env['battle.unit']
        heal_lines = mend_lines = self.env['battle.solver.line']
        for side in SIDES:
            lines = self._get_lines(side)
            after = {
                line: Unit._get_state_after(line.battle_unit_id.damage_counter, line.battle_unit_id.wound_state, *consequences[line])
                for line in lines
            }
            wounded = sorted((line for line in lines if after[line][1] != '4'), key=lambda line: int(after[line][1]))
            damaged = sorted((line for line in lines if after[line][0] > 0), key=lambda line: -after[line][0])
            for line in wounded[:self._get_side_trait_value(side, 'heal_self', outcome.score)]:
                heal_lines |= line
            for line in damaged[:self._get_side_trait_value(side, 'mend_self', outcome.score)]:
                mend_lines |= line
        return heal_lines, mend_lines

    def _get_heal_mend_reminders(self) -> list[str]:
        """ Heal Self / Mend Self traits applying in the launched battle, for
        the solver to tell what was prefilled, e.g. 'Régénération: 2 heals
        (Initiators)' """
        self.ensure_one()
        side_labels = dict(SIDE_SELECTION)
        reminders = []
        for side in SIDES:
            for effect, label in (('heal_self', _("heals")), ('mend_self', _("mends"))):
                for trait, value in self._get_side_trait_values(side, effect, self.result_score):
                    if value:
                        reminders.append(f"{trait.name}: {value} {label} ({side_labels[side]})")
        return reminders

    def _get_lore_reminders(self) -> list[str]:
        """ Lore traits applying in the launched battle (stance, position and
        result), to resolve manually: traits of units taking part, location
        traits and effects of the round, e.g. 'Fanatique (Coterie du Vieux)' """
        self.ensure_one()
        location = self.battle_location_id
        effects = location._get_round_effects(self.battle_round_id.round_number) if location else self.env['battle.location.effect']
        side_labels = dict(SIDE_SELECTION)
        reminders = []
        location_sides = {}  # location lore trait: sides it applies to
        for side in SIDES:
            stance, result = self[f'{side}_stance'], self._get_side_result(side, self.result_score)
            for line in self._get_lines(side):
                traits = line.battle_unit_id.battle_trait_ids._applies(side, stance, result, line.position)
                for trait in traits.filtered(lambda trait: trait.effect == 'lore'):
                    reminders.append(f"{trait.name} ({line.battle_unit_id.name})")
            side_effects = effects.filtered(lambda effect: effect.battle_faction_id in self[f'{side}_faction_ids'])
            location_traits = (location.battle_trait_ids | side_effects.battle_trait_id)._applies(side, stance, result)
            for trait in location_traits.filtered(lambda trait: trait.effect == 'lore'):
                location_sides.setdefault(trait, []).append(side)
        for trait, sides in location_sides.items():
            if len(sides) == 1:
                reminders.append(f"{trait.name} ({location.name}, {side_labels[sides[0]]})")
            else:
                reminders.append(f"{trait.name} ({location.name})")
        return reminders

    def _get_location_consequences(self, outcome: BattleOutcome) -> dict:
        """ Consequences of ``outcome`` on the location, without applying
        them: status after the battle (an attacking winner shifts it towards
        its side, see outcome location shift), and traits granted by each side
        outcome (depending on its stance) for the next round. Returns solver
        values. """
        self.ensure_one()
        location = self.battle_location_id
        status, holder = location.status, location.held_by_faction_id
        winner = self._get_winner(outcome.score)
        if winner and self[f'{winner}_stance'] == 'attack':
            steps = self._get_side_outcome(winner, outcome).location_shift
            if steps:
                factions = self[f'{winner}_faction_ids']
                main_faction = self._get_side_main_faction(self._get_units(winner), factions)
                status, holder = location._get_shifted_status(factions, main_faction, steps)
        values = {'location_status_after': status, 'held_by_faction_after_id': holder.id}
        for side in SIDES:
            granted_traits = self._get_side_outcome(side, outcome)[f"{self[f'{side}_stance']}_trait_ids"]
            values[f'{side}_granted_trait_ids'] = granted_traits.ids
        return values

    def _get_location_values_after(self) -> dict:
        """ Location values to write when applying the battle (status after
        and holder), or an empty dict if unchanged """
        self.ensure_one()
        location = self.battle_location_id
        status, holder = self.location_status_after, self.held_by_faction_after_id
        if not status or (status, holder) == (location.status, location.held_by_faction_id):
            return {}
        return {'status': status, 'held_by_faction_id': holder.id}

    def _prepare_battle_result_values(self) -> dict:
        """ Result of the launched battle, to call before applying it: sides,
        roll and outcome, units consequences with their current state (before
        the battle), location state before the battle if it changes, and
        effects granted to each side factions in the location for the next
        round. """
        self.ensure_one()
        lines = self.initiator_line_ids + self.responder_line_ids
        location = self.battle_location_id
        values = {
            'battle_round_id': self.battle_round_id.id,
            'battle_location_id': location.id,
            'initiator_faction_ids': self.initiator_faction_ids.ids,
            'initiator_stance': self.initiator_stance,
            'responder_faction_ids': self.responder_faction_ids.ids,
            'responder_stance': self.responder_stance,
            'bonus': self.bonus,
            'dice_roll': self.dice_roll,
            'result_score': self.result_score,
            'battle_outcome_id': self.battle_outcome_id.id,
            'damage_to_initiators': self.damage_to_initiators,
            'damage_to_responders': self.damage_to_responders,
            'result_message': self.result_message,
            'battle_result_line_ids': [Command.create({
                'battle_unit_id': line.battle_unit_id.id,
                'side': line.side,
                'position': line.position,
                'damage': line.damage_received,
                'wounds': int(line.wound_state) - int(line.wound_state_after),
                'damage_counter_before': line.damage_counter,
                'wound_state_before': line.wound_state,
            }) for line in lines],
            'battle_location_effect_ids': [Command.create({
                'battle_faction_id': faction.id,
                'battle_trait_id': trait.id,
            }) for side in SIDES for trait in self[f'{side}_granted_trait_ids'] for faction in self[f'{side}_faction_ids']],
        }
        if self._get_location_values_after():
            values['location_status_before'] = location.status
            values['held_by_faction_before_id'] = location.held_by_faction_id.id
        return values

    def _update_units(self):
        """ Apply damage and wounds received in the launched battle on units,
        then heal and mend """
        for solver in self:
            for line in solver.initiator_line_ids + solver.responder_line_ids:
                unit = line.battle_unit_id
                unit._update_damage_and_wounds(
                    line.damage_received, line.wounds_received, unit in solver.heal_unit_ids, unit in solver.mend_unit_ids,
                )

    def _update_location(self):
        """ Apply the location status after the launched battle, if changed """
        for solver in self:
            location_values = solver._get_location_values_after()
            if location_values:
                solver.battle_location_id.write(location_values)

    # ------------------------------------------------------------
    # SIDES
    # ------------------------------------------------------------

    def _get_location_units(self, factions: BattleFaction) -> BattleUnit:
        """ Fighting units of ``factions`` in the location """
        self.ensure_one()
        if not self.battle_location_id or not factions:
            return self.env['battle.unit']
        return self.env['battle.unit'].search([
            ('battle_location_id', '=', self.battle_location_id.id),
            ('battle_faction_id', 'in', factions.ids),
            ('is_fighting', '=', True),
        ])

    def _get_line_commands(self, side: Side) -> list:
        """ Default units of a side, all in frontline """
        units = self._get_location_units(self[f'{side}_faction_ids'])
        return [Command.clear()] + [Command.create({'side': side, 'battle_unit_id': unit.id}) for unit in units]

    def _get_lines(self, side: Side) -> BattleSolverLine:
        """ Lines of units taking part in the battle (not out of it) """
        states = self._get_line_states()
        return self[f'{side}_line_ids'].filtered(lambda line: not states[line][1])

    def _get_line_states(self) -> dict[BattleSolverLine, tuple[int, OutReason]]:
        """ State of each line before rolling, as {line: (pre-battle wounds,
        reason for being out of the battle or False)}: assassins (frontline)
        wound their target, ambushers (responders in support) put their target
        out of the battle; units can also be put out manually (e.g. scouts). """
        self.ensure_one()
        lines = self.initiator_line_ids + self.responder_line_ids
        pre_wounds, ambushed = Counter(), set()
        for holder in lines.filtered(lambda line: line.target_unit_id and not line.is_excluded):
            targets = lines.filtered(lambda line: line.side != holder.side and line.battle_unit_id == holder.target_unit_id)
            traits = holder.battle_unit_id.battle_trait_ids._applies(holder.side, self[f'{holder.side}_stance'], None, holder.position)
            for trait in traits:
                if trait.effect == 'assassin':
                    for target in targets:
                        pre_wounds[target] += trait.value
                elif trait.effect == 'ambush':
                    ambushed.update(targets)

        states = {}
        for line in lines:
            if line.is_excluded:
                reason = 'excluded'
            elif line in ambushed:
                reason = 'ambushed'
            elif int(line.battle_unit_id.wound_state) - pre_wounds[line] <= 0:
                reason = 'killed'
            else:
                reason = False
            states[line] = (pre_wounds[line], reason)
        return states

    def _get_battle_signature(self) -> str:
        """ What the battle looks like before rolling: location, stances, DM
        bonuses, and units (side, position, out of the battle, target) """
        self.ensure_one()
        lines = sorted(
            (line.side, line.battle_unit_id.id, line.position, line.is_excluded, line.target_unit_id.id)
            for line in self.initiator_line_ids + self.responder_line_ids
        )
        return repr((
            self.battle_location_id.id, self.initiator_stance, self.responder_stance,
            self.initiator_characteristic_bonus, self.responder_characteristic_bonus, lines,
        ))

    def _get_lines_state(self, lines: BattleSolverLine) -> LinesState:
        """ Current state of ``lines`` units, as {line: (damage counter, wound state)} """
        return {line: (line.battle_unit_id.damage_counter, line.battle_unit_id.wound_state) for line in lines}

    def _get_units(self, side: Side) -> BattleUnit:
        """ Units of a side taking part in the battle """
        return self._get_lines(side).battle_unit_id

    def _get_frontline_units(self, side: Side) -> BattleUnit:
        """ Units of a side taking part in the battle in frontline """
        return self._get_lines(side).filtered(lambda line: line.position == 'frontline').battle_unit_id

    @api.model
    def _get_side_main_faction(self, units: BattleUnit, factions: BattleFaction) -> BattleFaction:
        """ Faction having most units in the side (first faction in case of
        tie), defaulting to the first side faction """
        if not units.battle_faction_id:
            return factions.sorted()[:1]
        counts = Counter(unit.battle_faction_id for unit in units if unit.battle_faction_id)
        return max(units.battle_faction_id.sorted(), key=lambda faction: counts[faction])

    @api.model
    def _get_side_result(self, side: Side, score: int | None) -> SideResult | None:
        """ Result of ``side`` given the ``score`` (initiators point of view) """
        if score is None:
            return None
        if score == 0:
            return 'tie'
        winner = self._get_winner(score)
        return 'win' if side == winner else 'lose'

    @api.model
    def _get_winner(self, score: int) -> Side | None:
        """ Side winning given the ``score`` (initiators point of view), None
        on tie """
        if score > 0:
            return 'initiator'
        if score < 0:
            return 'responder'
        return None

    # ------------------------------------------------------------
    # BONUSES
    # ------------------------------------------------------------

    def _get_bonus_lines(self) -> list[BonusLine]:
        """ Bonus of each side, line by line: opposing forces (characteristic
        depending on stance or Umbra, size), leadership (low morale malus,
        command actions), then bonus traits (see ``_get_trait_bonus_lines``) """
        self.ensure_one()
        morale_labels = dict(self.env['battle.round']._fields['aggressor_morale']._description_selection(self.env))

        # opposing forces: characteristics and size
        value_initiator, detail_initiator = self._get_side_compared_characteristic('initiator')
        value_responder, detail_responder = self._get_side_compared_characteristic('responder')
        characteristics_detail = _("%(initiator)s vs %(responder)s", initiator=detail_initiator, responder=detail_responder)
        size_initiator, size_detail_initiator = self._get_side_size('initiator')
        size_responder, size_detail_responder = self._get_side_size('responder')
        size_detail = _("%(initiator)s vs %(responder)s", initiator=size_detail_initiator, responder=size_detail_responder)
        # leadership: low morale is a malus
        morale_initiator = self._get_side_morale('initiator')
        morale_responder = self._get_side_morale('responder')
        morale_detail = _(
            "%(initiator)s vs %(responder)s",
            initiator=morale_labels[str(morale_initiator)], responder=morale_labels[str(morale_responder)],
        )

        return [
            self._prepare_bonus_line(
                'forces', _("Characteristics"), characteristics_detail,
                *self._get_bonus_more_or_double(value_initiator, value_responder),
            ),
            self._prepare_bonus_line(
                'forces', _("Size"), size_detail,
                *self._get_bonus_per_half_more(size_initiator, size_responder),
            ),
            self._prepare_bonus_line(
                'leadership', _("Morale"), morale_detail,
                -1 if morale_initiator <= 2 else 0, -1 if morale_responder <= 2 else 0,
            ),
            *self._get_command_bonus_lines(),
            *self._get_trait_bonus_lines(),
        ]

    def _get_command_bonus_lines(self) -> list[BonusLine]:
        """ One line per command action picked in the location by at least
        one side: its bonus (e.g. Location Support), or its effect on damage
        and resistance as detail (e.g. Hold On) """
        types = dict(self.env['battle.command.action']._fields['command_type']._description_selection(self.env))
        actions = {side: self._get_side_command_actions(side) for side in SIDES}
        lines = []
        for command_type, label in types.items():
            counts = [len(actions[side].filtered(lambda action: action.command_type == command_type)) for side in SIDES]
            if not any(counts):
                continue
            detail = _("%(initiator)s vs %(responder)s", initiator=counts[0], responder=counts[1])
            if command_type in COMMAND_RATES:
                detail = f"{self._format_command_rates(command_type)} ({detail})"
            bonus = COMMAND_BONUS.get(command_type, 0)
            lines.append(self._prepare_bonus_line('leadership', label, detail, bonus * counts[0], bonus * counts[1]))
        return lines

    @api.model
    def _format_command_rates(self, command_type: str) -> str:
        """ Effect of a command action on damage and resistance, only what
        changes, e.g. 'Damage +25% when attacking' """
        rates = COMMAND_RATES[command_type]
        parts = []
        if rates['damage'] != 100:
            parts.append(_("Damage %(rate)+d%%", rate=rates['damage'] - 100))
        if rates['resistance'] != 100:
            parts.append(_("Resistance %(rate)+d%%", rate=rates['resistance'] - 100))
        text = ', '.join(parts)
        if COMMAND_STANCES.get(command_type) == 'attack':
            text += ' ' + _("when attacking")
        elif COMMAND_STANCES.get(command_type) == 'defense':
            text += ' ' + _("when defending")
        return text

    def _get_trait_bonus_lines(self) -> list[BonusLine]:
        """ One line per trait giving a battle bonus to at least one side,
        location traits first """
        traits = self.env['battle.trait']
        for side in SIDES:
            for trait, _position in self._get_side_traits(side):
                traits |= trait
        bonus_traits = traits.filtered(lambda trait: trait.effect == 'bonus').sorted(
            lambda trait: (trait.target != 'location', trait.sequence, trait.id)
        )
        lines = []
        for trait in bonus_traits:
            initiator, responder = (self._get_trait_value(trait, side) for side in SIDES)
            if not initiator and not responder:
                continue
            detail = _(
                "%(initiator)s vs %(responder)s",
                initiator=self._get_trait_count(trait, 'initiator'), responder=self._get_trait_count(trait, 'responder'),
            )
            category = 'location' if trait.target == 'location' else 'traits'
            lines.append(self._prepare_bonus_line(category, trait.name, detail, initiator, responder))
        return lines

    def _get_side_stat(self, side: Side) -> typing.Literal['gnosis', 'rage', 'willpower']:
        """ Characteristic compared between sides: Gnosis in Umbra, otherwise
        Rage when attacking and Willpower when defending """
        if self.battle_location_id.is_umbra:
            return 'gnosis'
        return 'rage' if self[f'{side}_stance'] == 'attack' else 'willpower'

    def _get_side_compared_characteristic(self, side: Side) -> tuple[int, str]:
        """ Characteristic compared between sides (see ``_get_side_stat``):
        units characteristic, minus their wounds maluses and the enemy
        Diversion traits, plus the DM bonus. Returns its value and detail,
        e.g. 'Willpower 6 (wounds -1, diversion -2, bonus +2)' """
        stat = self._get_side_stat(side)
        enemy = 'responder' if side == 'initiator' else 'initiator'
        stat_labels = {'gnosis': _("Gnosis"), 'rage': _("Rage"), 'willpower': _("Willpower")}
        malus = sum(line.battle_unit_id._get_wound_malus('characteristic') for line in self._get_lines(side))
        diversion = self._get_side_trait_value(enemy, 'diversion')
        bonus = self[f'{side}_characteristic_bonus']
        value = self._get_side_characteristic(side, stat) - malus - diversion + bonus
        detail = f"{stat_labels[stat]} {value}"
        parts = []
        if malus:
            parts.append(_("wounds %(malus)+d", malus=-malus))
        if diversion:
            parts.append(_("diversion %(diversion)+d", diversion=-diversion))
        if bonus:
            parts.append(_("bonus %(bonus)+d", bonus=bonus))
        if parts:
            detail += f" ({', '.join(parts)})"
        return value, detail

    def _get_side_size(self, side: Side) -> tuple[int, str]:
        """ Size of the units of a side taking part in the battle, changed by
        size rate traits (e.g. Obstacles -25% when attacking), rounded down.
        Returns its value and detail, e.g. '3 (Obstacles -25%)' """
        size = sum(self._get_units(side).mapped('size'))
        rates = [(trait, value) for trait, value in self._get_side_trait_values(side, 'size_rate') if value]
        if not rates:
            return size, str(size)
        numerator, denominator = size, 1
        for _trait, value in rates:
            numerator *= max(0, 100 + value)
            denominator *= 100
        value = numerator // denominator
        return value, f"{value} ({', '.join(f'{trait.name} {rate:+d}%' for trait, rate in rates)})"

    def _get_side_characteristic(self, side: Side, stat: str) -> int:
        """ Sum of ``stat`` of the units of a side taking part in the battle """
        return sum(self._get_units(side).mapped(stat))

    def _get_side_camp(self, side: Side) -> Camp | typing.Literal[False]:
        """ Camp ('aggressor' or 'defender') a side fights for: the camp of its
        main faction (neutral factions following their ally), False if none """
        main_faction = self._get_side_main_faction(self._get_units(side), self[f'{side}_faction_ids'])
        return main_faction._get_camp_role() if main_faction else False

    def _get_side_morale(self, side: Side) -> int:
        """ Morale (0 to 4) of the side camp for the round, steady (3) by
        default """
        camp = self._get_side_camp(side)
        if not camp or not self.battle_round_id:
            return 3
        return int(self.battle_round_id[f'{camp}_morale'])

    @api.model
    def _get_bonus_more_or_double(self, initiator: int, responder: int) -> tuple[int, int]:
        """ +1 to the side having more, +2 if more than double. A positive
        value is considered more than double a null or negative one. """
        if initiator == responder:
            return 0, 0
        high, low = max(initiator, responder), min(initiator, responder)
        if low > 0:
            more_than_double = high > 2 * low
        else:
            more_than_double = high > 0
        bonus = 2 if more_than_double else 1
        return (bonus, 0) if initiator > responder else (0, bonus)

    @api.model
    def _get_bonus_per_half_more(self, initiator: int, responder: int) -> tuple[int, int]:
        """ +1 to the side having at least 50% more; limited to +1 so that
        hordes do not cumulate size and characteristics bonuses too much """
        if initiator == responder:
            return 0, 0
        high, low = max(initiator, responder), min(initiator, responder)
        if low > 0 and 2 * high < 3 * low:
            return 0, 0
        return (1, 0) if initiator > responder else (0, 1)

    @api.model
    def _prepare_bonus_line(self, category: str, name: str, detail: str, initiator: int, responder: int) -> BonusLine:
        return {'category': category, 'name': name, 'detail': detail, 'initiator': initiator, 'responder': responder}

    # ------------------------------------------------------------
    # TRAITS AND DAMAGE
    # ------------------------------------------------------------

    def _get_side_traits(self, side: Side) -> list[tuple[BattleTrait, str | None]]:
        """ Traits of a side ('initiator' or 'responder'), as a list of
        (trait, holder position): its units traits, location traits and
        location effects of its factions for the round (without position). """
        self.ensure_one()
        location_traits = self.battle_location_id.battle_trait_ids
        if self.battle_location_id and self.battle_round_id:
            effects = self.battle_location_id._get_round_effects(self.battle_round_id.round_number)
            side_effects = effects.filtered(lambda effect: effect.battle_faction_id in self[f'{side}_faction_ids'])
            location_traits |= side_effects.battle_trait_id
        unit_traits = [(trait, line.position) for line in self._get_lines(side) for trait in line.battle_unit_id.battle_trait_ids]
        return unit_traits + [(trait, None) for trait in location_traits]

    def _get_trait_count(self, trait: BattleTrait, side: Side, score: int | None = None) -> int:
        """ Number of holders of ``trait`` for which it applies for ``side``,
        given the battle ``score`` if known """
        stance, result = self[f'{side}_stance'], self._get_side_result(side, score)
        return sum(
            1 for holder_trait, position in self._get_side_traits(side)
            if holder_trait == trait and trait._applies(side, stance, result, position)
        )

    def _get_trait_value(self, trait: BattleTrait, side: Side, score: int | None = None) -> int:
        """ Value given by ``trait`` to ``side``, given the battle ``score``
        if known: counted once per side if unique, once per holder otherwise """
        self.ensure_one()
        count = self._get_trait_count(trait, side, score)
        if not count:
            return 0
        if trait.is_unique:
            return trait.value
        return trait.value * count

    def _get_side_trait_values(self, side: Side, effect: str, score: int | None = None) -> list[tuple[BattleTrait, int]]:
        """ Value of each side trait having ``effect`` (e.g. 'damage',
        'reroll'), given the battle ``score`` if known, as [(trait, value)] """
        traits = self.env['battle.trait']
        for trait, _position in self._get_side_traits(side):
            if trait.effect == effect:
                traits |= trait
        return [(trait, self._get_trait_value(trait, side, score)) for trait in traits]

    def _get_side_trait_value(self, side: Side, effect: str, score: int | None = None) -> int:
        """ Total value of the side traits having ``effect`` """
        return sum(value for _trait, value in self._get_side_trait_values(side, effect, score))

    def _get_support_value(self, side: Side, effect: str, score: int | None = None) -> int:
        """ Damage of support units having a support ``effect`` trait
        ('support_damage' or 'support_resistance') applying, minus their
        wounds maluses """
        stance, result = self[f'{side}_stance'], self._get_side_result(side, score)
        total = 0
        for line in self._get_lines(side).filtered(lambda line: line.position == 'support'):
            traits = line.battle_unit_id.battle_trait_ids.filtered(lambda trait: trait.effect == effect)
            if traits._applies(side, stance, result, 'support'):
                total += line.battle_unit_id.damage - line.battle_unit_id._get_wound_malus('damage')
        return total

    def _get_side_command_actions(self, side: Side) -> BattleCommandAction:
        """ Command actions picked by the side camp in the location for the
        round """
        self.ensure_one()
        camp = self._get_side_camp(side)
        if not self.battle_location_id or not self.battle_round_id or not camp:
            return self.env['battle.command.action']
        return self.env['battle.command.action'].search([
            ('battle_location_id', '=', self.battle_location_id.id),
            ('battle_round_id', '=', self.battle_round_id.id),
            ('camp', '=', camp),
        ])

    def _get_side_outcome(self, side: Side, outcome: BattleOutcome) -> BattleOutcome:
        """ Outcome of a side: ``outcome`` (initiators point of view) for
        initiators, its opposite for responders """
        if side == 'initiator':
            return outcome
        return self.env['battle.outcome']._get_by_score().get(-outcome.score, self.env['battle.outcome'])

    def _get_side_rate(self, side: Side, outcome: BattleOutcome, stat: typing.Literal['damage', 'resistance']) -> int:
        """ Rate (%) of frontline ``stat`` given by the side outcome,
        depending on its stance """
        stance = self[f'{side}_stance']
        return self._get_side_outcome(side, outcome)[f'{stance}_{stat}_rate']

    def _get_side_stat_breakdown(self, side: Side, outcome: BattleOutcome, stat: typing.Literal['damage', 'resistance']) -> StatBreakdown:
        """ Damage or resistance of a side, step by step: frontline units
        total (minus wounds maluses), multiplied by the side outcome rate (depending on its stance),
        command actions rates (e.g. Full Attack) and traits rates (e.g. -25%
        damage), then traits and support (Appui adds to damage, Couverture
        to resistance) added. """
        stance = self[f'{side}_stance']
        stance_labels = dict(self._fields['initiator_stance']._description_selection(self.env))
        command_labels = dict(self.env['battle.command.action']._fields['command_type']._description_selection(self.env))
        trait_effect = stat  # 'damage' and 'resistance' trait effects are added to the matching stat
        rate_effect = f'{stat}_rate'  # 'damage_rate' and 'resistance_rate' trait effects change it by a percentage
        support_effect = 'support_damage' if stat == 'damage' else 'support_resistance'
        support_labels = dict(self.env['battle.trait']._fields['effect']._description_selection(self.env))

        # frontline (minus wounds maluses), with rates
        frontline_units = self._get_frontline_units(side)
        wound_malus = sum(unit._get_wound_malus(stat) for unit in frontline_units)
        frontline = sum(frontline_units.mapped(stat)) - wound_malus
        side_outcome = self._get_side_outcome(side, outcome)
        outcome_rate = self._get_side_rate(side, outcome, stat)
        rates = [(f"{side_outcome.name}, {stance_labels[stance]}", outcome_rate)]
        for command_type in sorted(set(self._get_side_command_actions(side).mapped('command_type'))):
            if command_type not in COMMAND_RATES or COMMAND_STANCES.get(command_type, stance) != stance:
                continue
            if COMMAND_RATES[command_type][stat] != 100:
                rates.append((command_labels[command_type], COMMAND_RATES[command_type][stat]))
        for trait, value in self._get_side_trait_values(side, rate_effect, outcome.score):
            if value:
                rates.append((trait.name, max(0, 100 + value)))
        # all rates multiplied, rounded down once
        numerator, denominator = frontline, 1
        for _label, rate in rates:
            numerator *= rate
            denominator *= 100
        base = numerator // denominator

        # then traits and support
        bonuses = [
            (trait.name, value)
            for trait, value in self._get_side_trait_values(side, trait_effect, outcome.score)
            if value
        ]
        support = self._get_support_value(side, support_effect, outcome.score)
        if support:
            bonuses.append((support_labels[support_effect], support))
        return {
            'frontline': frontline,
            'wound_malus': wound_malus,
            'rates': rates,
            'base': base,
            'bonuses': bonuses,
            'total': base + sum(value for _label, value in bonuses),
        }

    def _get_side_damage(self, side: Side, outcome: BattleOutcome) -> int:
        """ Damage dealt by a side, see ``_get_side_stat_breakdown`` """
        return self._get_side_stat_breakdown(side, outcome, 'damage')['total']

    def _get_side_resistance(self, side: Side, outcome: BattleOutcome) -> int:
        """ Resistance of a side, see ``_get_side_stat_breakdown`` """
        return self._get_side_stat_breakdown(side, outcome, 'resistance')['total']

    @api.model
    def _format_stat_breakdown(self, breakdown: StatBreakdown) -> str:
        """ e.g. '9 (wounds -1) × 150% (Victory, Attack) = 13, +6 Fureur → 19' """
        text = str(breakdown['frontline'])
        if breakdown['wound_malus']:
            text += f" (wounds {-breakdown['wound_malus']:+d})"
        for label, rate in breakdown['rates']:
            text += f" × {rate}% ({label})"
        text += f" = {breakdown['base']}"
        if breakdown['bonuses']:
            text += ''.join(f", {value:+d} {label}" for label, value in breakdown['bonuses'])
            text += f" → {breakdown['total']}"
        return text

    def _get_damage_details(self, outcome: BattleOutcome) -> list[str]:
        """ How damage to each side is computed, one line per side hit """
        names = {side: ', '.join(self[f'{side}_faction_ids'].sorted().mapped('name')) for side in SIDES}
        details = []
        for side, enemy, damage in zip(('responder', 'initiator'), ('initiator', 'responder'), self._get_damage(outcome), strict=True):
            details.append(_(
                "Damage to %(target)s: %(damage)s = %(source)s damage %(source_damage)s, minus %(target)s resistance %(target_resistance)s.",
                target=names[side], damage=damage, source=names[enemy],
                source_damage=self._format_stat_breakdown(self._get_side_stat_breakdown(enemy, outcome, 'damage')),
                target_resistance=self._format_stat_breakdown(self._get_side_stat_breakdown(side, outcome, 'resistance')),
            ))
        return details

    def _get_damage(self, outcome: BattleOutcome) -> tuple[int, int]:
        """ Damage dealt for a given ``outcome`` (initiators point of view), as
        (to responders, to initiators): damage of a side minus resistance of
        the other side, at least 0. """
        self.ensure_one()
        to_responders = self._get_side_damage('initiator', outcome) - self._get_side_resistance('responder', outcome)
        to_initiators = self._get_side_damage('responder', outcome) - self._get_side_resistance('initiator', outcome)
        return max(0, to_responders), max(0, to_initiators)

    @api.model
    def _get_damage_distribution(self, lines: BattleSolverLine, damage: int, state: LinesState) -> dict[BattleSolverLine, int]:
        """ Spread ``damage`` points one by one over fighting frontline units,
        then support units once no frontline unit is fighting anymore, given
        units ``state``. Returns {line: damage points}. """
        counters = {line: state[line][0] for line in lines}
        wound_states = {line: int(state[line][1]) for line in lines}
        distribution = Counter()
        for position in ('frontline', 'support'):
            pool = lines.filtered(lambda line: line.position == position)
            fighting = [line for line in pool if wound_states[line] > 0]
            while damage and fighting:
                for line in fighting:
                    if not damage:
                        break
                    distribution[line] += 1
                    damage -= 1
                    counters[line] += 1
                    if counters[line] >= DAMAGE_PER_WOUND:
                        counters[line] = 0
                        wound_states[line] -= 1
                fighting = [line for line in pool if wound_states[line] > 0]
        return dict(distribution)

    @api.model
    def _get_wound_targets(self, lines: BattleSolverLine, state: LinesState) -> list[BattleSolverLine]:
        """ Lines of units to wound, given units ``state``: fighting ones,
        frontline first, least wounded first """
        fighting = lines.filtered(lambda line: state[line][1] != '0')
        return sorted(fighting, key=lambda line: (line.position != 'frontline', -int(state[line][1])))

    # ------------------------------------------------------------
    # DICE
    # ------------------------------------------------------------

    @api.model
    def _get_roll_chances(self) -> dict[int, float]:
        """ Probability of each dice roll total """
        totals = Counter(sum(roll) for roll in itertools.product(DICE_FACES, repeat=DICE_COUNT))
        count = len(DICE_FACES) ** DICE_COUNT
        return {total: occurrences / count for total, occurrences in totals.items()}

    def _get_score_chances(self) -> dict[int, float]:
        """ Probability of each final score, given current bonus """
        self.ensure_one()
        chances = Counter()
        for total, chance in self._get_roll_chances().items():
            chances[self._get_score(total)] += chance
        return dict(chances)

    def _get_score(self, roll_total: int) -> int:
        """ Score given a dice roll total: bonus added, capped to outcomes """
        self.ensure_one()
        return max(OUTCOME_SCORE_MIN, min(OUTCOME_SCORE_MAX, self.bonus + roll_total))

    @api.model
    def _roll_dice(self, count: int = DICE_COUNT) -> list[int]:
        """ Raw dice roll, patched in tests """
        return [random.choice(DICE_FACES) for _dice in range(count)]

    def _roll_battle_dice(self) -> list[int]:
        """ Roll the dice, then apply forced rerolls: best dice of the side,
        i.e. highest for initiators, lowest for responders """
        self.ensure_one()
        roll = list(self._roll_dice())
        for side, best in (('initiator', max), ('responder', min)):
            for _reroll in range(min(self[f'{side}_forced_rerolls'], DICE_COUNT)):
                roll[roll.index(best(roll))] = self._roll_dice(1)[0]
        return roll

    @api.model
    def _format_dice(self, roll: list[int]) -> str:
        return ' '.join(f'{value:+d}' for value in roll)

    @api.model
    def _parse_dice(self, dice: str) -> list[int]:
        """ Parse dice values from a text like '-1 0 +1' """
        try:
            roll = [int(value) for value in dice.replace(',', ' ').split()]
        except ValueError:
            roll = []
        if len(roll) != DICE_COUNT or any(value not in DICE_FACES for value in roll):
            raise UserError(_(
                "Dice should be %(count)s values among %(faces)s, e.g. '-1 0 +1'.",
                count=DICE_COUNT, faces=', '.join(f'{face:+d}' for face in DICE_FACES),
            ))
        return roll

    # ------------------------------------------------------------
    # TOOLS
    # ------------------------------------------------------------

    @api.model
    def _get_result_reset_values(self) -> dict:
        """ Values clearing a simulation or a launched battle """
        return {
            'mode': False,
            'dice_roll': False,
            'result_score': 0,
            'battle_outcome_id': False,
            'damage_to_initiators': 0,
            'damage_to_responders': 0,
            'result_message': False,
        }

    def _get_reopen_action(self) -> dict:
        """ Action keeping the wizard open, e.g. to display the result """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Battle Solver"),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

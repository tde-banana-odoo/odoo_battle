import logging
import random
import typing

from collections import defaultdict

from odoo.addons.odoo_battle.const import DICE_COUNT, DICE_FACES
from odoo.addons.odoo_battle.tests.common import BattleCommon
from odoo.fields import Command
from odoo.tests import tagged

_logger = logging.getLogger(__name__)

F, S = 'frontline', 'support'
# compositions: (template xml id suffix, position)
BSD_3 = [('bsd_rank_3', F)] * 3
WW_3 = [('werewolf_rank_3', F)] * 3
BSD_MIXED = [('bsd_rank_4', F), ('bsd_rank_3', F), ('bsd_rank_3_ruse', F)]
WW_MIXED = [('werewolf_rank_4', F), ('werewolf_rank_3', F), ('werewolf_rank_3_ruse', F)]
VAMPIRES = [('vampire_coterie_g7', F), ('vampire_coterie_g8', F), ('vampire_coterie_g8', F)]
GHOULS = [('ghoul_combat', F)] * 2
HENCHMEN = [('human_henchman', F)] * 2
HENCHMEN_SUPPORT = [('human_henchman', S)] * 2
HUMANS = [('human_special_forces', F), ('human_special_forces', F), ('human_henchman', S), ('human_henchman', S)]
WW_2 = [('werewolf_rank_3', F)] * 2
JAGLINS = [('spirit_jaglin', F)] * 3
JAGLINS_DEFENSE = [('spirit_jaglin_def', F)] * 3
GAFLINS = [('spirit_gaflin', F)] * 3
ENGLIN = [('spirit_englin', F)]
INCARNA = [('spirit_incarna', F)]


class BalanceResult(typing.NamedTuple):
    win: float  # initiators chances of winning (score > 0)
    tie: float
    loss: float
    wounds_initiators: float  # expected wounds received
    wounds_responders: float
    bonus: int
    details: str  # bonus lines giving an advantage
    menace: tuple[int, int]  # (initiators, responders)
    wounds_by_template: dict[str, float]  # expected wounds received, per side and template, e.g. 'R ghoul_combat'
    wounds_if_win: tuple[float, float]  # expected wounds received by (initiators, responders) when initiators win
    wounds_if_loss: tuple[float, float]  # same, when initiators lose
    attrition: tuple[float, float]  # expected share of wound levels (4 per unit) lost per battle, per side


class BattleBalanceCommon(BattleCommon):
    """ Balance of game data: battles between units built from data templates
    (with their traits), evaluated exactly over all dice rolls. Each scenario
    gives initiators win / tie / loss chances and expected wounds received by
    each side (from damage, and wound traits such as Massacre). Not counted:
    Assassin and Embuscade (targets chosen at the table), heal and mend.

    Hard expectations are asserted. Soft targets, not met by current data,
    only log a warning (see ``_check_target``): turn them into assertions
    once data reaches them. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        fortified = cls.env.ref('odoo_battle.battle_trait_fortified')
        cls.location_open, cls.location_fortified, cls.location_umbra = cls.env['battle.location'].create([
            {'name': 'Test Open Ground', 'status': 'held', 'held_by_faction_id': cls.faction_bad.id},
            {'name': 'Test Fortified', 'status': 'held', 'held_by_faction_id': cls.faction_bad.id,
             'battle_trait_ids': fortified.ids},
            {'name': 'Test Umbra', 'status': 'held', 'held_by_faction_id': cls.faction_bad.id, 'is_umbra': True},
        ])

    def _build(
        self, location, initiators, responders, initiator_stance='attack', responder_stance='defense', changes=None,
        commands=(),
    ):
        """ Solver of a battle in ``location`` between ``initiators`` (good
        faction, aggressor camp) and ``responders`` (bad faction, holding the
        location), given as compositions. ``changes`` (what-if) are values
        written on units of a template, e.g. {'spirit_jaglin': {'size': 1}};
        ``commands`` are command actions picked for a side in the location,
        e.g. [('responder', 'hold_on')]. Returns the solver, and the created
        units and command actions, to remove afterwards. """
        changes = changes or {}
        Unit = self.env['battle.unit']
        camps = {'initiator': 'aggressor', 'responder': 'defender'}
        actions = self.env['battle.command.action']
        if commands:
            self.battle_round.write({f'{camp}_command_action_count': 10 for camp in camps.values()})
            actions = actions.create([{
                'battle_round_id': self.battle_round.id, 'camp': camps[side], 'command_type': command_type,
                'battle_location_id': location.id,
            } for side, command_type in commands])
        sides = {}
        for side, faction, composition in (('initiator', self.faction_good, initiators), ('responder', self.faction_bad, responders)):
            sides[side] = [
                (Unit.create({
                    'name': f'Test {template} {index}',
                    'battle_unit_template_id': self.env.ref(f'odoo_battle.battle_unit_template_{template}').id,
                    'battle_faction_id': faction.id,
                    'battle_location_id': location.id,
                }), position)
                for index, (template, position) in enumerate(composition)
            ]
            for unit, _position in sides[side]:
                if self._get_template_key(unit) in changes:
                    unit.write(changes[self._get_template_key(unit)])
        solver = self._new_solver_form(location).save()
        for side, units in sides.items():
            self._set_lines(
                solver, side,
                frontline=Unit.union(*(unit for unit, position in units if position == F)),
                support=Unit.union(*(unit for unit, position in units if position == S)),
            )
        solver.write({'initiator_stance': initiator_stance, 'responder_stance': responder_stance})
        return solver, Unit.union(*(unit for units in sides.values() for unit, _position in units)), actions

    @staticmethod
    def _get_template_key(unit) -> str:
        """ Template xml id suffix of a unit, e.g. 'werewolf_rank_3' (its name if no template) """
        template = unit.battle_unit_template_id
        if not template:
            return unit.name
        return template.get_external_id()[template.id].removeprefix('odoo_battle.battle_unit_template_')

    def _evaluate(self, solver) -> BalanceResult:
        """ Results of the battle set up in ``solver``, exactly over all dice rolls """
        outcomes = self.env['battle.outcome']._get_by_score()
        chances = solver._get_score_chances()
        wounds = {'initiator': 0.0, 'responder': 0.0}
        wounds_by_template = defaultdict(float)
        by_result = {result: {'initiator': 0.0, 'responder': 0.0} for result in ('win', 'loss')}
        for score, chance in chances.items():
            for line, (damage, direct_wounds) in solver._get_unit_consequences(outcomes[score]).items():
                unit = line.battle_unit_id
                _counter, after = unit._get_state_after(unit.damage_counter, unit.wound_state, damage, direct_wounds)
                received = chance * (int(unit.wound_state) - int(after))
                wounds[line.side] += received
                if score:
                    by_result['win' if score > 0 else 'loss'][line.side] += received
                wounds_by_template[f"{line.side[0].upper()} {self._get_template_key(unit)}"] += received
        win = sum(chance for score, chance in chances.items() if score > 0)
        loss = sum(chance for score, chance in chances.items() if score < 0)
        capacity = {side: 4 * len(solver._get_lines(side)) or 1 for side in ('initiator', 'responder')}
        return BalanceResult(
            win=win,
            tie=chances.get(0, 0.0),
            loss=loss,
            wounds_initiators=wounds['initiator'],
            wounds_responders=wounds['responder'],
            bonus=solver.bonus,
            details=', '.join(
                f"{line['name']} {line['initiator'] - line['responder']:+g} ({line['detail']})"
                for line in solver._get_bonus_lines() if line['initiator'] != line['responder']
            ),
            menace=(solver.initiator_menace, solver.responder_menace),
            wounds_by_template=dict(wounds_by_template),
            wounds_if_win=tuple(by_result['win'][side] / win if win else 0.0 for side in ('initiator', 'responder')),
            wounds_if_loss=tuple(by_result['loss'][side] / loss if loss else 0.0 for side in ('initiator', 'responder')),
            attrition=tuple(wounds[side] / capacity[side] for side in ('initiator', 'responder')),
        )

    def _scenario(self, location, initiators, responders, *args, **kwargs) -> BalanceResult:
        """ Results of a battle built from compositions (see ``_build``) """
        solver, units, actions = self._build(location, initiators, responders, *args, **kwargs)
        result = self._evaluate(solver)
        units.unlink()  # free the location for the next scenario
        actions.unlink()
        return result

    def _campaign(self, location, initiators, responders, *args, battles=8, runs=60, **kwargs) -> dict:
        """ The same battle fought again and again, wounds (and their
        maluses) carried over, until a side is broken (half of its wound
        levels lost, 4 per unit): ``runs`` random campaigns (seeded, so
        reproducible). Returns how many battles it took on average, and how
        often each side was broken first. """
        solver, units, actions = self._build(location, initiators, responders, *args, **kwargs)
        outcomes = self.env['battle.outcome']._get_by_score()
        rng = random.Random(42)
        lengths, broken = [], {'initiator': 0, 'responder': 0, None: 0}
        for _run in range(runs):
            units.write({'wound_state': '4', 'damage_counter': 0})
            loser = None
            for battle in range(1, battles + 1):
                solver.invalidate_recordset()
                roll = [rng.choice(DICE_FACES) for _dice in range(DICE_COUNT)]
                consequences = solver._get_unit_consequences(outcomes[solver._get_score(sum(roll))])
                for line, (damage, direct_wounds) in consequences.items():
                    unit = line.battle_unit_id
                    counter, state = unit._get_state_after(unit.damage_counter, unit.wound_state, damage, direct_wounds)
                    unit.write({'damage_counter': counter, 'wound_state': state})
                lost = {
                    side: sum(4 - int(state) for state in units.filtered(lambda unit, side=side: unit in solver[f'{side}_line_ids'].battle_unit_id).mapped('wound_state'))
                    / (4 * len(solver[f'{side}_line_ids']) or 1)
                    for side in ('initiator', 'responder')
                }
                broken_sides = [side for side, ratio in lost.items() if ratio >= 0.5]
                if broken_sides:
                    loser = max(broken_sides, key=lambda side: lost[side])
                    break
            lengths.append(battle)
            broken[loser] += 1
        units.unlink()
        actions.unlink()
        return {
            'battles': sum(lengths) / runs,
            'initiators_broken': broken['initiator'] / runs,
            'responders_broken': broken['responder'] / runs,
            'none_broken': broken[None] / runs,
        }


    def _check_target(self, condition: bool, message: str, result: BalanceResult) -> None:
        """ Soft balance target: warn when not met, without failing """
        if not condition:
            _logger.warning(
                "Balance target not met: %s (win %.0f%%, tie %.0f%%, loss %.0f%%; %s)",
                message, result.win * 100, result.tie * 100, result.loss * 100, result.details,
            )



@tagged('battle_balance')
class TestBattleBalance(BattleBalanceCommon):
    """ Balance expectations on game data (see ``BattleBalanceCommon``) """

    # ------------------------------------------------------------
    # SCENARIOS
    # ------------------------------------------------------------

    def test_balance_shapeshifters(self):
        """ BSD and werewolves (same statistics per rank) are balanced:
        symmetric results whoever attacks; the attacker is favored on open
        ground (Rage against Willpower), not anymore on fortified ground;
        BSD deal more damage, werewolves defend better """
        bsd_attack = self._scenario(self.location_open, BSD_3, WW_3)
        ww_attack = self._scenario(self.location_open, WW_3, BSD_3)
        self.assertAlmostEqual(bsd_attack.win, ww_attack.win, msg='Same chances whoever attacks')
        self.assertGreater(bsd_attack.win, bsd_attack.loss, 'Open ground: attacker favored')
        fortified = self._scenario(self.location_fortified, BSD_3, WW_3)
        self.assertLess(fortified.win, bsd_attack.win, 'Fortified ground helps defenders')
        self.assertAlmostEqual(fortified.win, fortified.loss, msg='Fortified ground: balanced')

        both_attack = self._scenario(self.location_open, BSD_3, WW_3, 'attack', 'attack')
        self.assertGreater(both_attack.wounds_responders, both_attack.wounds_initiators, 'Both attacking: BSD deal more damage')
        both_defend = self._scenario(self.location_open, BSD_3, WW_3, 'defense', 'defense')
        self.assertGreater(both_defend.wounds_initiators, both_defend.wounds_responders, 'Both defending: werewolves defend better')

        mixed_bsd_attack = self._scenario(self.location_open, BSD_MIXED, WW_MIXED)
        mixed_ww_attack = self._scenario(self.location_open, WW_MIXED, BSD_MIXED)
        self.assertAlmostEqual(mixed_bsd_attack.win, mixed_ww_attack.win, msg='Mixed ranks: same chances whoever attacks')

    def test_balance_vampires(self):
        """ Vampires (elder and two coteries, menace 13) are a match for
        three werewolves packs (menace 12), probably less powerful (soft
        target): they do not win more often than werewolves attacking BSD
        do (63%) """
        vampires_attack = self._scenario(self.location_open, VAMPIRES, WW_3)
        self.assertGreater(vampires_attack.win, vampires_attack.loss, 'Vampires are a match for werewolves')
        self._check_target(vampires_attack.win <= 0.63, "vampires attacking werewolves win at most 63%", vampires_attack)

    def test_balance_vampires_agents(self):
        """ Agents help vampires against werewolves: they bring numbers
        (size); in frontline they lower the average quality. Combat ghouls
        do not make chances worse and make werewolves bleed more; weak
        agents (henchmen) in support do not make it worse either (soft
        target); in frontline they do (slaughtered, the battle goes badly) """
        alone = self._scenario(self.location_open, WW_3, VAMPIRES)
        ghouls = self._scenario(self.location_open, WW_3, VAMPIRES + GHOULS)
        self.assertLessEqual(ghouls.win, alone.win)
        self.assertGreaterEqual(ghouls.wounds_initiators, alone.wounds_initiators)
        henchmen = self._scenario(self.location_open, WW_3, VAMPIRES + HENCHMEN_SUPPORT)
        self._check_target(henchmen.win <= alone.win, "henchmen in support do not weaken vampires against werewolves", henchmen)

    def test_balance_humans(self):
        """ Two werewolves packs beat four human units (special forces in
        frontline, henchmen in support), and are not hurt much by them,
        even on fortified ground """
        for location in (self.location_open, self.location_fortified):
            with self.subTest(location=location.name):
                result = self._scenario(location, WW_2, HUMANS)
                self.assertGreaterEqual(result.win, result.loss)
                self.assertLessEqual(result.wounds_initiators, result.wounds_responders)
        humans_attack = self._scenario(self.location_open, HUMANS, WW_2)
        self.assertLessEqual(humans_attack.win, humans_attack.loss, 'Humans attacking werewolves do not win more')

    def test_balance_elders(self):
        """ Vampire elders (G7) and rank 4 werewolves have the same menace:
        led groups (G7 + 2 G8 against WW4 + 2 WW3) are balanced. One-on-one,
        Terreur weighs a full point (spread over a single creature): accepted,
        such duels being rare (the DM may compensate). """
        led_vampires = self._scenario(self.location_open, VAMPIRES, [('werewolf_rank_4', F)] + WW_2)
        led_werewolves = self._scenario(self.location_open, [('werewolf_rank_4', F)] + WW_2, VAMPIRES)
        self.assertAlmostEqual(led_vampires.win, led_werewolves.win, msg='Led groups: same chances whoever attacks')

    def test_balance_humans_tactics(self):
        """ Humans beat werewolves only when outnumbering them and having
        tactical advantages: numbers alone are not enough """
        humans = [('human_special_forces', F)] * 4 + [('human_henchman_ruse', S)] * 4
        numbers = self._scenario(self.location_open, WW_2, humans)
        self.assertGreaterEqual(numbers.win, numbers.loss, 'Numbers alone: werewolves do not lose more often')
        tactics = self._scenario(self.location_fortified, WW_2, humans, commands=[('responder', 'location_support')])
        self.assertGreater(tactics.loss, tactics.win, 'Numbers, fortified, location support: humans win')

    def test_balance_spirits(self):
        """ Spirits against spirits in the Umbra (e.g. Hills Umbra): support
        spirits help in defense; an Incarna beats an Englin with a few
        gaflins (same menace); an Englin with a few jaglins is balanced
        against more jaglins and gaflins (same menace: quality against
        numbers); an Incarna drives small fights, jaglins helping it in
        damage rather than in chances. Note: in the Umbra, both stances
        compare Gnosis: assault and defense variants only differ after the
        roll (tweak their statistics if needed). """
        umbra = self.location_umbra
        alone = self._scenario(umbra, JAGLINS, JAGLINS_DEFENSE[:2])
        supported = self._scenario(umbra, JAGLINS, JAGLINS_DEFENSE[:2] + [('spirit_gaflin', S)] * 2)
        self.assertLess(supported.win, alone.win, 'Support spirits help in defense')
        self.assertLess(supported.attrition[1], alone.attrition[1], 'Support spirits spare defenders')
        incarna = self._scenario(umbra, INCARNA, ENGLIN + GAFLINS[:2])
        self.assertGreater(incarna.win, incarna.loss, 'Incarna beats an Englin with a few gaflins')
        englin = self._scenario(umbra, ENGLIN + GAFLINS[:2], INCARNA)
        self.assertGreater(englin.loss, englin.win, 'Incarna beats an Englin with a few gaflins, also defending')
        for initiators, responders in [(ENGLIN + JAGLINS[:2], JAGLINS[:2] + GAFLINS), (JAGLINS[:2] + GAFLINS, ENGLIN + JAGLINS[:2])]:
            with self.subTest(initiators=initiators[0][0]):
                quality = self._scenario(umbra, initiators, responders)
                self.assertAlmostEqual(quality.win, quality.loss, msg='Quality against numbers: balanced')
        jaglins = self._scenario(umbra, INCARNA + JAGLINS[:2], INCARNA + GAFLINS[:2])
        self.assertLess(jaglins.wounds_initiators, jaglins.wounds_responders, 'Jaglins spare the Incarna side more than gaflins')

    def test_balance_umbra(self):
        """ Spirits are stronger in the Umbra (Gnosis) than outside, where
        they matter less: werewolves are small players in the Umbra """
        umbra = self._scenario(self.location_umbra, WW_3, JAGLINS)
        outside = self._scenario(self.location_open, WW_3, JAGLINS)
        self.assertGreater(outside.win, outside.loss, 'Outside the Umbra, werewolves beat jaglins')
        self.assertLess(umbra.win, outside.win, 'Jaglins are stronger in the Umbra')
        self.assertGreater(umbra.loss, umbra.win, 'In the Umbra, jaglins beat werewolves')



@tagged('-standard', 'battle_balance_report')
class TestBattleBalanceReport(BattleBalanceCommon):
    """ Balance reports, logged to compare and iterate on data; not run by
    default (slow): run with --test-tags battle_balance_report """

    # ------------------------------------------------------------
    # REPORT
    # ------------------------------------------------------------

    def test_balance_report(self):
        """ Log all scenarios by theme, to compare and iterate on data (run
        with --test-tags battle_balance_report).
        What-if scenarios change some units, e.g. removing a trait. """
        terror = self.env.ref('odoo_battle.battle_trait_terror')
        no_terror = {'vampire_coterie_g7': {'battle_trait_ids': [Command.unlink(terror.id)]}}
        open_, fortified, umbra = self.location_open, self.location_fortified, self.location_umbra
        themes = {
            'Shapeshifters': [
                ('3 BSD3 attack 3 WW3, open', (open_, BSD_3, WW_3)),
                ('3 BSD3 attack 3 WW3, fortified', (fortified, BSD_3, WW_3)),
                ('3 BSD3 attack 3 WW3 attacking back, open', (open_, BSD_3, WW_3, 'attack', 'attack')),
                ('3 WW3 attack 3 BSD3, open', (open_, WW_3, BSD_3)),
                ('3 WW3 attack 3 BSD3, fortified', (fortified, WW_3, BSD_3)),
                ('3 BSD3 defend vs 3 WW3 defending', (open_, BSD_3, WW_3, 'defense', 'defense')),
                ('BSD 4+3+3c attack WW 4+3+3r, open', (open_, BSD_MIXED, WW_MIXED)),
                ('WW 4+3+3r attack BSD 4+3+3c, open', (open_, WW_MIXED, BSD_MIXED)),
                ('2 BSD3 attack 3 WW3, open', (open_, BSD_3[:2], WW_3)),
                ('3 BSD2 attack 2 WW3, open (same menace 9 vs 8)', (open_, [('bsd_rank_2', F)] * 3, WW_2)),
            ],
            'Vampires': [
                ('G7 + 2 G8 attack 3 WW3, open', (open_, VAMPIRES, WW_3)),
                ('  same, G7 without Terreur', (open_, VAMPIRES, WW_3, 'attack', 'defense', no_terror)),
                ('3 G8 attack 3 WW3, open', (open_, [('vampire_coterie_g8', F)] * 3, WW_3)),
                ('3 WW3 attack G7 + 2 G8, open', (open_, WW_3, VAMPIRES)),
                ('  same, G7 without Terreur', (open_, WW_3, VAMPIRES, 'attack', 'defense', no_terror)),
                ('3 WW3 attack 3 G8, open', (open_, WW_3, [('vampire_coterie_g8', F)] * 3)),
                ('3 WW3 attack G7 + 2 G8 + 2 combat ghouls (front)', (open_, WW_3, VAMPIRES + GHOULS)),
                ('3 WW3 attack G7 + 2 G8 + 2 ghouls (front)', (open_, WW_3, VAMPIRES + [('ghoul', F)] * 2)),
                ('3 WW3 attack G7 + 2 G8 + 2 henchmen (front)', (open_, WW_3, VAMPIRES + HENCHMEN)),
                ('3 WW3 attack G7 + 2 G8 + 2 henchmen (support)', (open_, WW_3, VAMPIRES + HENCHMEN_SUPPORT)),
                ('3 WW3 attack G7 + 2 G8 + 2 combat ghouls (support)', (open_, WW_3, VAMPIRES + [('ghoul_combat', S)] * 2)),
                ('3 WW3 attack G7 + 2 G8 + 2 humains (front)', (open_, WW_3, VAMPIRES + [('human_std', F)] * 2)),
                ('3 WW3 attack 2 G8 + 2 henchmen (same menace 10 vs 12)', (open_, WW_3, [('vampire_coterie_g8', F)] * 2 + HENCHMEN)),
            ],
            'Elders and leaders': [
                ('G7 attack WW4, open', (open_, [('vampire_coterie_g7', F)], [('werewolf_rank_4', F)])),
                ('WW4 attack G7, open', (open_, [('werewolf_rank_4', F)], [('vampire_coterie_g7', F)])),
                ('  same, G7 without Terreur', (open_, [('werewolf_rank_4', F)], [('vampire_coterie_g7', F)], 'attack', 'defense', no_terror)),
                ('G7 attack BSD4, open', (open_, [('vampire_coterie_g7', F)], [('bsd_rank_4', F)])),
                ('G7 + 2 G8 attack WW4 + 2 WW3, open', (open_, VAMPIRES, [('werewolf_rank_4', F)] + WW_2)),
                ('WW4 + 2 WW3 attack G7 + 2 G8, open', (open_, [('werewolf_rank_4', F)] + WW_2, VAMPIRES)),
            ],
            'Humans': [
                ('2 WW3 attack 2 FS + 2 HdM (support), open', (open_, WW_2, HUMANS)),
                ('2 WW3 attack 2 FS + 2 HdM (support), fortified', (fortified, WW_2, HUMANS)),
                ('2 WW3 attack 4 FS + 4 HdM (support), fortified', (fortified, WW_2, HUMANS * 2)),
                ('2 WW3 attack 2 Méca + 2 FS, fortified', (fortified, WW_2, [('human_mechanized', F)] * 2 + [('human_special_forces', F)] * 2)),
                ('2 FS + 2 HdM (support) attack 2 WW3, open', (open_, HUMANS, WW_2)),
                ('2 Méca + 2 FS + 2 HdM (support) attack 2 WW3, open', (open_, [('human_mechanized', F)] * 2 + HUMANS, WW_2)),
                ('2 WW3 attack 4 FS + 4 HdM (support), open', (open_, WW_2, HUMANS * 2)),
                ('2 WW3 attack 4 FS + 4 HdMr (support), open', (open_, WW_2, [('human_special_forces', F)] * 4 + [('human_henchman_ruse', S)] * 4)),
                ('  same, fortified + Hold On', (fortified, WW_2, [('human_special_forces', F)] * 4 + [('human_henchman_ruse', S)] * 4,
                                                 'attack', 'defense', None, [('responder', 'hold_on')])),
                ('  same, fortified + Location Support', (fortified, WW_2, [('human_special_forces', F)] * 4 + [('human_henchman_ruse', S)] * 4,
                                                          'attack', 'defense', None, [('responder', 'location_support')])),
                ('3 WW3 attack 4 FS + 4 HdMr, fortified + Location Support', (fortified, WW_3, [('human_special_forces', F)] * 4 + [('human_henchman_ruse', S)] * 4,
                                                                             'attack', 'defense', None, [('responder', 'location_support')])),
            ],
            'Kiker chaff (fomori, possessed)': [
                ('2 Fomoris + 2 Possédés attack 2 FS + 2 HdM (support)', (open_, [('fomori', F)] * 2 + [('possessed', F)] * 2, HUMANS)),
                ('2 FS + 2 HdM (support) attack 2 Fomoris + 2 Possédés', (open_, HUMANS, [('fomori', F)] * 2 + [('possessed', F)] * 2)),
                ('2 Fomoris+ attack 2 FS, open', (open_, [('fomori_engineered', F)] * 2, [('human_special_forces', F)] * 2)),
                ('2 Possédés+ attack 2 FS, open', (open_, [('possessed_elite', F)] * 2, [('human_special_forces', F)] * 2)),
                ('4 Possédés attack 1 WW3, open', (open_, [('possessed', F)] * 4, WW_3[:1])),
                ('2 Possédés+ + 2 Fomoris+ attack 2 WW3, open', (open_, [('possessed_elite', F)] * 2 + [('fomori_engineered', F)] * 2, WW_2)),
                ('BSD4 + 2 Possédés (front) attack 2 WW3, open', (open_, [('bsd_rank_4', F)] + [('possessed', F)] * 2, WW_2)),
                ('BSD4 + 2 Possédés (support) attack 2 WW3, open', (open_, [('bsd_rank_4', F)] + [('possessed', S)] * 2, WW_2)),
                ('BSD4 alone attacks 2 WW3, open', (open_, [('bsd_rank_4', F)], WW_2)),
            ],
            'Spirits (e.g. Hills Umbra)': [
                ('3 Jaglins attack 3 Jaglins (Ruse), Umbra', (umbra, JAGLINS, JAGLINS_DEFENSE)),
                ('3 Jaglins (Ruse) attack 3 Jaglins, Umbra', (umbra, JAGLINS_DEFENSE, JAGLINS)),
                ('3 Jaglins attack 2 Jaglins (Ruse), Umbra', (umbra, JAGLINS, JAGLINS_DEFENSE[:2])),
                ('  + 2 Gaflins (support)', (umbra, JAGLINS, JAGLINS_DEFENSE[:2] + [('spirit_gaflin', S)] * 2)),
                ('  + 2 Jaglins (Ruse) (support)', (umbra, JAGLINS, JAGLINS_DEFENSE[:2] + [('spirit_jaglin_def', S)] * 2)),
                ('Englin + 2 Jaglins attack 2 Jaglins + 3 Gaflins (M7 vs M7)', (umbra, ENGLIN + JAGLINS[:2], JAGLINS[:2] + GAFLINS)),
                ('2 Jaglins + 3 Gaflins attack Englin + 2 Jaglins', (umbra, JAGLINS[:2] + GAFLINS, ENGLIN + JAGLINS[:2])),
                ('Incarna attack Englin + 2 Gaflins (M5 vs M5)', (umbra, INCARNA, ENGLIN + GAFLINS[:2])),
                ('Englin + 2 Gaflins attack Incarna', (umbra, ENGLIN + GAFLINS[:2], INCARNA)),
                ('Incarna + 2 Gaflins attack Englin + 4 Gaflins (M7 vs M7)', (umbra, INCARNA + GAFLINS[:2], ENGLIN + GAFLINS + GAFLINS[:1])),
                ('Incarna + 2 Jaglins attack Incarna + 2 Gaflins', (umbra, INCARNA + JAGLINS[:2], INCARNA + GAFLINS[:2])),
                ('Incarna + 2 Gaflins attack Incarna + 2 Jaglins', (umbra, INCARNA + GAFLINS[:2], INCARNA + JAGLINS[:2])),
                ('3 WW3 attack Englin + 2 Gaflins, Umbra', (umbra, WW_3, ENGLIN + GAFLINS[:2])),
                ('3 WW3 attack Englin + 2 Gaflins, open', (open_, WW_3, ENGLIN + GAFLINS[:2])),
            ],
            'Umbra': [
                ('3 WW3 attack 3 Jaglins, Umbra', (umbra, WW_3, JAGLINS)),
                ('  same, Jaglin size 1', (umbra, WW_3, JAGLINS, 'attack', 'defense', {'spirit_jaglin': {'size': 1}})),
                ('3 WW3 attack 3 Jaglins, open', (open_, WW_3, JAGLINS)),
                ('3 Jaglins attack 3 WW3, Umbra', (umbra, JAGLINS, WW_3)),
                ('3 WW3 attack 2 Jaglins (same menace... 12 vs 4)', (umbra, WW_3, JAGLINS[:2])),
                ('WW 4+3+3r attack 3 Jaglins, Umbra', (umbra, WW_MIXED, JAGLINS)),
                ('3 WW3 attack 3 Gaflins, Umbra', (umbra, WW_3, [('spirit_gaflin', F)] * 3)),
                ('3 WW3 attack Incarna + 2 Gaflins, Umbra', (umbra, WW_3, [('spirit_incarna', F)] + [('spirit_gaflin', F)] * 2)),
                ('3 BSD3 attack 3 Jaglins, Umbra', (umbra, BSD_3, JAGLINS)),
            ],
        }
        # menace rework: menace weights the characteristic average; each scenario is run with current data, then reworked
        rework = {
            'spirit_jaglin': {'menace': 3}, 'spirit_jaglin_def': {'menace': 3},
            'bsd_rank_4': {'menace': 4}, 'werewolf_rank_4': {'menace': 4}, 'vampire_coterie_g7': {'menace': 4},
            'spirit_incarna': {'menace': 4},
        }
        rework_scenarios = [
            ('BSD 4+3+3c attack WW 4+3+3r, open', (open_, BSD_MIXED, WW_MIXED)),
            ('BSD4 + 2 BSD2 attack WW4 + 2 WW2, open', (open_, [('bsd_rank_4', F)] + [('bsd_rank_2', F)] * 2, [('werewolf_rank_4', F)] + [('werewolf_rank_2', F)] * 2)),
            ('WW4 + 2 WW2 attack BSD4 + 2 BSD2, open', (open_, [('werewolf_rank_4', F)] + [('werewolf_rank_2', F)] * 2, [('bsd_rank_4', F)] + [('bsd_rank_2', F)] * 2)),
            ('G7 + 2 G8 attack 3 WW3, open', (open_, VAMPIRES, WW_3)),
            ('3 WW3 attack G7 + 2 G8, open', (open_, WW_3, VAMPIRES)),
            ('G7 + 2 G8 attack WW4 + 2 WW3, open', (open_, VAMPIRES, [('werewolf_rank_4', F)] + WW_2)),
            ('WW4 + 2 WW3 attack G7 + 2 G8, open', (open_, [('werewolf_rank_4', F)] + WW_2, VAMPIRES)),
            ('3 WW3 attack G7 + 2 G8 + 2 henchmen', (open_, WW_3, VAMPIRES + HENCHMEN)),
            ('WW4 + 2 WW3 attack Incarna + 2 Gaflins, Umbra', (umbra, [('werewolf_rank_4', F)] + WW_2, [('spirit_incarna', F)] + [('spirit_gaflin', F)] * 2)),
            ('3 WW3 attack Incarna + 2 Jaglins, Umbra', (umbra, WW_3, [('spirit_incarna', F)] + JAGLINS[:2])),
            ('3 WW3 attack 2 Jaglins + 2 Gaflins, Umbra', (umbra, WW_3, JAGLINS[:2] + [('spirit_gaflin', F)] * 2)),
            ('3 WW3 attack 2 Jaglins + 2 Gaflins, open', (open_, WW_3, JAGLINS[:2] + [('spirit_gaflin', F)] * 2)),
            ('WW4 + 2 WW3 attack 3 Jaglins, Umbra', (umbra, [('werewolf_rank_4', F)] + WW_2, JAGLINS)),
        ]
        themes['Menace rework (current, then reworked)'] = [
            (f"{prefix}{name}", args + (('attack', 'defense', rework) if prefix else ()))
            for name, args in rework_scenarios for prefix in ('', '  reworked: ')
        ]
        lines = []
        for theme, scenarios in themes.items():
            lines.append(f"== {theme}")
            for name, args in scenarios:
                result = self._scenario(*args)
                by_template = ', '.join(f"{template} {wounds:.2f}" for template, wounds in result.wounds_by_template.items() if wounds >= 0.005)
                lines.append(
                    f"{name:52s} M{result.menace[0]:>2} vs M{result.menace[1]:<2} bonus {result.bonus:+d}"
                    f"  win {result.win:4.0%} tie {result.tie:4.0%} loss {result.loss:4.0%}"
                    f"  wounds I {result.wounds_initiators:4.2f} R {result.wounds_responders:4.2f}"
                    f"  (if win: I {result.wounds_if_win[0]:.2f} R {result.wounds_if_win[1]:.2f};"
                    f" if loss: I {result.wounds_if_loss[0]:.2f} R {result.wounds_if_loss[1]:.2f})"
                    f"  attrition I {result.attrition[0]:.0%} R {result.attrition[1]:.0%}"
                    f"\n      {result.details or 'no advantage'}" + (f" | wounds: {by_template}" if by_template else '')
                )
        _logger.info("Balance report:\n%s", '\n'.join(lines))

    def test_balance_report_real(self):
        """ Log the battles of current game data: each location with opposing
        forces, as the solver sets it up (all units in frontline, default
        stances), with units wounds and location traits; command actions and
        morale of the real round are not taken into account (run with
        --test-tags battle_balance_report) """
        lines = []
        locations = self.env['battle.location'].search([('is_external', '=', False)])
        for location in locations.filtered(lambda location: location.get_external_id()[location.id]):  # game data only
            initiators, responders = location._get_battle_sides()
            if not initiators or not responders:
                continue
            solver = self._new_solver_form(location).save()
            result = self._evaluate(solver)
            lines.append(
                f"{location.name} ({', '.join(initiators.mapped('name'))} vs {', '.join(responders.mapped('name'))}):"
                f" M{result.menace[0]} vs M{result.menace[1]} bonus {result.bonus:+d}"
                f"  win {result.win:4.0%} tie {result.tie:4.0%} loss {result.loss:4.0%}"
                f"  wounds I {result.wounds_initiators:4.2f} R {result.wounds_responders:4.2f}"
                f"  attrition I {result.attrition[0]:.0%} R {result.attrition[1]:.0%}"
                f"\n      {result.details or 'no advantage'}"
            )
        _logger.info("Balance report, current game battles:\n%s", '\n'.join(lines))

    def test_balance_report_campaigns(self):
        """ Log campaigns: the same battle fought again and again until a side
        is broken (half its wound levels lost), wounds carried over (run
        with --test-tags battle_balance_report) """
        open_, fortified, umbra = self.location_open, self.location_fortified, self.location_umbra
        campaigns = [
            ('3 BSD3 attack 3 WW3, open', (open_, BSD_3, WW_3)),
            ('3 BSD3 attack 3 WW3, fortified', (fortified, BSD_3, WW_3)),
            ('BSD 4+3+3c attack WW 4+3+3r, open', (open_, BSD_MIXED, WW_MIXED)),
            ('G7 + 2 G8 attack WW4 + 2 WW3, open', (open_, VAMPIRES, [('werewolf_rank_4', F)] + WW_2)),
            ('3 WW3 attack G7 + 2 G8 + 2 henchmen (support)', (open_, WW_3, VAMPIRES + HENCHMEN_SUPPORT)),
            ('2 WW3 attack 4 FS + 4 HdM (support), fortified', (fortified, WW_2, HUMANS * 2)),
            ('3 WW3 attack 3 Jaglins, Umbra', (umbra, WW_3, JAGLINS)),
            ('Englin + 2 Jaglins attack 2 Jaglins + 3 Gaflins, Umbra', (umbra, ENGLIN + JAGLINS[:2], JAGLINS[:2] + GAFLINS)),
        ]
        lines = []
        for name, args in campaigns:
            result = self._campaign(*args)
            lines.append(
                f"{name:55s} battles {result['battles']:.1f}  broken: initiators {result['initiators_broken']:.0%},"
                f" responders {result['responders_broken']:.0%}, none after 8 battles {result['none_broken']:.0%}"
            )
        _logger.info("Balance report, campaigns:\n%s", '\n'.join(lines))

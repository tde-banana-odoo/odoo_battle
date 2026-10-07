import logging
import typing

from odoo.addons.odoo_battle.tests.common import BattleCommon
from odoo.tests import tagged

_logger = logging.getLogger(__name__)

F, S = 'frontline', 'support'
# compositions: (template xml id suffix, position)
BSD_3 = [('bsd_rank_3', F)] * 3
WW_3 = [('werewolf_rank_3', F)] * 3
BSD_MIXED = [('bsd_rank_4', F), ('bsd_rank_3', F), ('bsd_rank_3_corr', F)]
WW_MIXED = [('werewolf_rank_4', F), ('werewolf_rank_3', F), ('werewolf_rank_3_resp', F)]
VAMPIRES = [('vampire_coterie_g7', F), ('vampire_coterie_g8', F), ('vampire_coterie_g8', F)]
GHOULS = [('ghoul_combat', F)] * 2
HENCHMEN = [('human_henchman', F)] * 2
HUMANS = [('human_special_forces', F), ('human_special_forces', F), ('human_henchman', S), ('human_henchman', S)]
WW_2 = [('werewolf_rank_3', F)] * 2
JAGLINS = [('spirit_jaglin', F)] * 3


class BalanceResult(typing.NamedTuple):
    win: float  # initiators chances of winning (score > 0)
    tie: float
    loss: float
    wounds_initiators: float  # expected wounds received
    wounds_responders: float
    bonus: int
    details: str  # bonus lines giving an advantage


@tagged('battle_balance')
class TestBattleBalance(BattleCommon):
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

    def _scenario(self, location, initiators, responders, initiator_stance='attack', responder_stance='defense') -> BalanceResult:
        """ Battle in ``location`` between ``initiators`` (good faction,
        aggressor camp) and ``responders`` (bad faction, holding the
        location), given as compositions """
        Unit = self.env['battle.unit']
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
        solver = self._new_solver_form(location).save()
        for side, units in sides.items():
            self._set_lines(
                solver, side,
                frontline=Unit.union(*(unit for unit, position in units if position == F)),
                support=Unit.union(*(unit for unit, position in units if position == S)),
            )
        solver.write({'initiator_stance': initiator_stance, 'responder_stance': responder_stance})

        outcomes = self.env['battle.outcome']._get_by_score()
        chances = solver._get_score_chances()
        wounds = {'initiator': 0.0, 'responder': 0.0}
        for score, chance in chances.items():
            for line, (damage, direct_wounds) in solver._get_unit_consequences(outcomes[score]).items():
                unit = line.battle_unit_id
                _counter, after = unit._get_state_after(unit.damage_counter, unit.wound_state, damage, direct_wounds)
                wounds[line.side] += chance * (int(unit.wound_state) - int(after))
        result = BalanceResult(
            win=sum(chance for score, chance in chances.items() if score > 0),
            tie=chances.get(0, 0.0),
            loss=sum(chance for score, chance in chances.items() if score < 0),
            wounds_initiators=wounds['initiator'],
            wounds_responders=wounds['responder'],
            bonus=solver.bonus,
            details=', '.join(
                f"{line['name']} {line['initiator'] - line['responder']:+d} ({line['detail']})"
                for line in solver._get_bonus_lines() if line['initiator'] != line['responder']
            ),
        )
        # free the location for the next scenario
        Unit.union(*(unit for units in sides.values() for unit, _position in units)).unlink()
        return result

    def _check_target(self, condition: bool, message: str, result: BalanceResult) -> None:
        """ Soft balance target: warn when not met, without failing """
        if not condition:
            _logger.warning(
                "Balance target not met: %s (win %.0f%%, tie %.0f%%, loss %.0f%%; %s)",
                message, result.win * 100, result.tie * 100, result.loss * 100, result.details,
            )

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
        """ Agents (ghouls, henchmen) help vampires against werewolves """
        alone = self._scenario(self.location_open, WW_3, VAMPIRES)
        for agents in (GHOULS, HENCHMEN):
            with self.subTest(agents=agents[0][0]):
                helped = self._scenario(self.location_open, WW_3, VAMPIRES + agents)
                self.assertLess(helped.win, alone.win)

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

    def test_balance_umbra(self):
        """ Spirits are stronger in the Umbra (Gnosis) than outside """
        umbra = self._scenario(self.location_umbra, WW_3, JAGLINS)
        outside = self._scenario(self.location_open, WW_3, JAGLINS)
        self.assertGreater(outside.win, outside.loss, 'Outside the Umbra, werewolves beat jaglins')
        self.assertLess(umbra.win, outside.win, 'Jaglins are stronger in the Umbra')

    def test_balance_umbra_annoying(self):
        """ In the Umbra, three jaglins (menace 6) are annoying for three
        werewolves packs (menace 12), not overwhelming (soft target):
        werewolves attacking keep a fair chance (at least 15%) """
        umbra = self._scenario(self.location_umbra, WW_3, JAGLINS)
        self._check_target(umbra.win >= 0.15, "werewolves attacking jaglins in the Umbra win at least 15%", umbra)

    # ------------------------------------------------------------
    # REPORT
    # ------------------------------------------------------------

    def test_balance_report(self):
        """ Log all scenarios, to compare and iterate on data (run with
        --test-tags /odoo_battle:TestBattleBalance.test_balance_report) """
        scenarios = {
            'BSD3 x3 attack WW3 x3, open': (self.location_open, BSD_3, WW_3),
            'BSD3 x3 attack WW3 x3, fortified': (self.location_fortified, BSD_3, WW_3),
            'WW3 x3 attack BSD3 x3, open': (self.location_open, WW_3, BSD_3),
            'BSD3 x3 vs WW3 x3, both attack': (self.location_open, BSD_3, WW_3, 'attack', 'attack'),
            'BSD3 x3 vs WW3 x3, both defend': (self.location_open, BSD_3, WW_3, 'defense', 'defense'),
            'BSD 4+3+3c attack WW 4+3+3r, open': (self.location_open, BSD_MIXED, WW_MIXED),
            'WW 4+3+3r attack BSD 4+3+3c, open': (self.location_open, WW_MIXED, BSD_MIXED),
            'Vampires attack WW3 x3, open': (self.location_open, VAMPIRES, WW_3),
            'WW3 x3 attack vampires, open': (self.location_open, WW_3, VAMPIRES),
            'WW3 x3 attack vampires + ghouls x2': (self.location_open, WW_3, VAMPIRES + GHOULS),
            'WW3 x3 attack vampires + henchmen x2': (self.location_open, WW_3, VAMPIRES + HENCHMEN),
            'WW3 x2 attack humans, open': (self.location_open, WW_2, HUMANS),
            'WW3 x2 attack humans, fortified': (self.location_fortified, WW_2, HUMANS),
            'Humans attack WW3 x2, open': (self.location_open, HUMANS, WW_2),
            'WW3 x3 attack jaglins x3, Umbra': (self.location_umbra, WW_3, JAGLINS),
            'WW3 x3 attack jaglins x3, open': (self.location_open, WW_3, JAGLINS),
            'Jaglins x3 attack WW3 x3, Umbra': (self.location_umbra, JAGLINS, WW_3),
        }
        lines = []
        for name, args in scenarios.items():
            result = self._scenario(*args)
            lines.append(
                f"{name:40s} bonus {result.bonus:+d}  win {result.win:4.0%} tie {result.tie:4.0%} loss {result.loss:4.0%}"
                f"  wounds received: initiators {result.wounds_initiators:4.2f}, responders {result.wounds_responders:4.2f}"
                f"\n    {result.details or 'no advantage'}"
            )
        _logger.info("Balance report:\n%s", '\n'.join(lines))

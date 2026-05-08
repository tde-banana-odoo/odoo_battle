from unittest.mock import patch

from odoo.addons.odoo_battle.tests.common import BattleCommon
from odoo.addons.odoo_battle.wizard.battle_solver import BattleSolver
from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, tagged, users


@tagged('post_install', '-at_install')
class TestBattleSolver(BattleCommon):

    def _new_solver_form(self, location):
        """ Open solver like the 'Battle' button of location form view """
        return Form(self.env['battle.solver'].with_context(
            active_model='battle.location',
            active_id=location.id,
        ))

    def _get_bonus(self, solver):
        solver.invalidate_recordset()  # changes on regular models do not invalidate transient ones
        return solver.initiator_bonus, solver.responder_bonus, solver.bonus

    # ------------------------------------------------------------
    # SIDES
    # ------------------------------------------------------------

    @users('battle_admin')
    def test_solver_defaults(self):
        """ Free location: the defender camp responds, other factions
        initiate. Initiators attack, responders defend. """
        solver_form = self._new_solver_form(self.location_isca)
        self.assertEqual(solver_form.battle_location_id, self.location_isca)
        self.assertEqual(solver_form.initiator_faction_ids.ids, self.faction_good.ids)
        self.assertEqual(solver_form.responder_faction_ids.ids, self.faction_bad.ids)
        self.assertEqual((solver_form.initiator_stance, solver_form.responder_stance), ('attack', 'defense'))
        self.assertEqual(set(solver_form.initiator_unit_ids.ids), set((self.unit_werewolf_1 + self.unit_werewolf_2).ids))
        self.assertEqual(solver_form.responder_unit_ids.ids, self.unit_vampire_1.ids)
        self.assertEqual(solver_form.initiator_menace, 5)
        self.assertEqual(solver_form.responder_menace, 4)
        self.assertFalse(solver_form.mode)

        # swapping factions swaps units
        solver_form.initiator_faction_ids.clear()
        solver_form.initiator_faction_ids.add(self.faction_bad)
        solver_form.responder_faction_ids.clear()
        solver_form.responder_faction_ids.add(self.faction_good)
        self.assertEqual(solver_form.initiator_unit_ids.ids, self.unit_vampire_1.ids)
        self.assertEqual(set(solver_form.responder_unit_ids.ids), set((self.unit_werewolf_1 + self.unit_werewolf_2).ids))

        # changing location reloads sides: only responders in Londinium
        solver_form.battle_location_id = self.location_londinium
        self.assertEqual(len(solver_form.initiator_faction_ids), 0)
        self.assertEqual(solver_form.responder_faction_ids.ids, self.faction_bad.ids)
        self.assertEqual(solver_form.responder_unit_ids.ids, self.unit_vampire_2.ids)

    @users('battle_admin')
    def test_solver_sides_holder_and_allies(self):
        """ Allies fight along their faction; held location: holders and
        their allies respond """
        faction_neutral = self.env['battle.faction'].sudo().create({
            'name': 'Test Neutral', 'role': 'neutral', 'allied_faction_id': self.faction_good.id,
        })
        unit_neutral = self.env['battle.unit'].sudo().create({
            'name': 'Test Neutral Unit', 'unit_type': 'spirit',
            'battle_faction_id': faction_neutral.id, 'battle_location_id': self.location_isca.id,
        })
        # free location: neutral allied to aggressors initiates with them
        solver_form = self._new_solver_form(self.location_isca)
        self.assertEqual(set(solver_form.initiator_faction_ids.ids), set((self.faction_good + faction_neutral).ids))
        self.assertIn(unit_neutral.id, solver_form.initiator_unit_ids.ids)

        # held by good: good and its allies respond
        self.location_isca.sudo().write({'status': 'held', 'held_by_faction_id': self.faction_good.id})
        solver_form = self._new_solver_form(self.location_isca)
        self.assertEqual(set(solver_form.responder_faction_ids.ids), set((self.faction_good + faction_neutral).ids))
        self.assertEqual(solver_form.initiator_faction_ids.ids, self.faction_bad.ids)
        self.assertEqual(solver_form.initiator_unit_ids.ids, self.unit_vampire_1.ids)

    @users('battle_admin')
    def test_solver_units_without_faction(self):
        """ Units without faction do not take part in battles """
        self.unit_werewolf_2.sudo().battle_faction_id = False
        solver_form = self._new_solver_form(self.location_isca)
        self.assertEqual(solver_form.initiator_unit_ids.ids, self.unit_werewolf_1.ids)
        self.assertEqual(solver_form.responder_unit_ids.ids, self.unit_vampire_1.ids)

    # ------------------------------------------------------------
    # BONUS
    # ------------------------------------------------------------

    @users('battle_admin')
    def test_solver_bonus(self):
        """ Isca: Rage 7 vs Willpower 6 (+1), Size 5 vs 2 (+2), no morale
        issue (6 vs 4), not fortified """
        solver = self._new_solver_form(self.location_isca).save()
        lines = {line['name']: (line['initiator'], line['responder']) for line in solver._get_bonus_lines()}
        self.assertEqual(lines, {
            'Characteristics': (1, 0),
            'Size': (2, 0),
            'Morale': (0, 0),
        })
        self.assertEqual(self._get_bonus(solver), (3, 0, 3))
        self.assertIn('Rage 7 vs Willpower 6', solver.bonus_summary)

        # location traits: fortified helps responders when defending
        self.location_isca.sudo().battle_trait_ids = self.trait_fortified
        self.assertEqual(self._get_bonus(solver), (3, 1, 2))

        # leadership: low morale is a malus
        self.faction_bad.sudo().morale = 2
        self.assertEqual(self._get_bonus(solver), (3, 0, 3))
        self.faction_good.sudo().morale = 1
        self.assertEqual(self._get_bonus(solver), (2, 0, 2))

    @users('battle_admin')
    def test_solver_bonus_stances(self):
        """ Rage when attacking, Willpower when defending; fortifications only
        help defending responders """
        self.location_isca.sudo().battle_trait_ids = self.trait_fortified
        solver = self._new_solver_form(self.location_isca).save()
        self.assertEqual(self._get_bonus(solver), (3, 1, 2))

        # both attack: Rage 7 vs Rage 1 (+2), no fortification
        solver.responder_stance = 'attack'
        self.assertEqual(self._get_bonus(solver), (4, 0, 4))
        self.assertIn('Rage 7 vs Rage 1', solver.bonus_summary)

        # both defend: Willpower 9 vs Willpower 6 (+1), fortification only for responders
        solver.write({'initiator_stance': 'defense', 'responder_stance': 'defense'})
        self.assertEqual(self._get_bonus(solver), (3, 1, 2))
        self.assertIn('Willpower 9 vs Willpower 6', solver.bonus_summary)

    @users('battle_admin')
    def test_solver_bonus_umbra(self):
        """ In Umbra, both sides use Gnosis whatever their stance """
        self.location_isca.sudo().is_umbra = True
        solver = self._new_solver_form(self.location_isca).save()
        # Gnosis 7 vs 0 (+2), Size 5 vs 2 (+2)
        self.assertEqual(self._get_bonus(solver), (4, 0, 4))
        self.assertIn('Gnosis 7 vs Gnosis 0', solver.bonus_summary)
        solver.responder_stance = 'attack'
        self.assertIn('Gnosis 7 vs Gnosis 0', solver.bonus_summary)

    def test_solver_bonus_rules(self):
        """ Comparison rules used by bonuses, including edge cases """
        Solver = self.env['battle.solver']
        for (initiator, responder), expected in [
            ((5, 5), (0, 0)),
            ((7, 6), (1, 0)),  # more
            ((12, 6), (1, 0)),  # double is not more than double
            ((13, 6), (2, 0)),  # more than double
            ((6, 7), (0, 1)),
            ((3, 0), (2, 0)),  # positive vs null or negative: more than double
            ((3, -1), (2, 0)),
            ((-1, -3), (1, 0)),
        ]:
            self.assertEqual(Solver._bonus_more_or_double(initiator, responder), expected, f'{initiator} vs {responder}')
        for (initiator, responder), expected in [
            ((3, 3), (0, 0)),
            ((4, 3), (0, 0)),  # less than 50% more
            ((3, 2), (1, 0)),  # 50% more
            ((4, 2), (2, 0)),  # 100% more
            ((7, 2), (2, 0)),  # max +2
            ((2, 3), (0, 1)),
            ((1, 0), (2, 0)),
        ]:
            self.assertEqual(Solver._bonus_per_half_more(initiator, responder), expected, f'{initiator} vs {responder}')

    def test_solver_side_morale(self):
        """ Several factions in a side: majority wins, first faction on tie """
        Solver = self.env['battle.solver']
        good, bad = self.faction_good, self.faction_bad
        self.assertEqual(Solver._get_side_morale(self.unit_werewolf_1 + self.unit_vampire_1 + self.unit_vampire_2, good + bad), 4)
        self.assertEqual(Solver._get_side_morale(self.unit_werewolf_1 + self.unit_vampire_1, good + bad), 6)
        self.assertEqual(Solver._get_side_morale(self.env['battle.unit'], bad), 4)

    @users('battle_admin')
    def test_solver_traits_bonus(self):
        """ Battle bonus traits: unique ones count once per side, location
        traits apply depending on stance """
        (self.unit_werewolf_1 + self.unit_werewolf_2).sudo().battle_trait_ids = self.trait_leadership
        self.location_isca.sudo().battle_trait_ids = self.trait_ambush
        solver = self._new_solver_form(self.location_isca).save()
        lines = {line['name']: (line['initiator'], line['responder']) for line in solver._get_bonus_lines()}
        self.assertEqual(lines['Test Leadership'], (1, 0))
        self.assertEqual(lines['Test Ambush'], (0, 1))
        self.assertNotIn('Test Fury', lines)
        self.assertEqual(self._get_bonus(solver), (4, 1, 3))

        # ambush only helps defending sides
        solver.responder_stance = 'attack'
        lines = {line['name']: (line['initiator'], line['responder']) for line in solver._get_bonus_lines()}
        self.assertNotIn('Test Ambush', lines)

    # ------------------------------------------------------------
    # DAMAGE
    # ------------------------------------------------------------

    @users('battle_admin')
    def test_solver_damage(self):
        """ Damage: damage of a side when attacking (+ traits, + outcome)
        minus resistance of the other side (+ outcome), at least 0 """
        (self.unit_werewolf_1 + self.unit_werewolf_2).sudo().write({'resistance': 0, 'battle_trait_ids': self.trait_fury.ids})
        self.unit_vampire_1.sudo().write({'resistance': 1, 'battle_trait_ids': self.trait_counter.ids})
        solver = self._new_solver_form(self.location_isca).save()
        outcomes = {outcome.score: outcome for outcome in self.env['battle.outcome'].search([])}
        # initiators attack: damage 2 + 2 vs resistance 1; responders defend: no damage
        self.assertEqual(solver._get_damage(outcomes[0]), (3, 0))
        # initiators win: fury x2
        self.assertEqual(solver._get_damage(outcomes[1]), (5, 0))
        # responders win: counter-attack
        self.assertEqual(solver._get_damage(outcomes[-1]), (3, 1))

        # both attack: responders deal damage 3, but counter-attack needs defending
        solver.responder_stance = 'attack'
        self.assertEqual(solver._get_damage(outcomes[0]), (3, 3))
        self.assertEqual(solver._get_damage(outcomes[-1]), (3, 3))
        solver.responder_stance = 'defense'

        # outcome extra damage and resistance
        outcomes[2].sudo().write({'initiator_damage': 1, 'responder_resistance': 4})
        self.assertEqual(solver._get_damage(outcomes[2]), (2, 0))

        # battle stores damage
        with patch.object(BattleSolver, '_roll_dice', return_value=[-1, -1, 0]):
            solver.action_battle()
        self.assertEqual(solver.result_score, 1)
        self.assertEqual((solver.damage_to_responders, solver.damage_to_initiators), (5, 0))
        self.assertIn('Damage: 5 to Test Bad, 0 to Test Good.', solver.result_message)

    # ------------------------------------------------------------
    # DICE AND ACTIONS
    # ------------------------------------------------------------

    def test_solver_side_result(self):
        """ Score is given from initiators point of view """
        Solver = self.env['battle.solver']
        self.assertEqual(Solver._get_side_result('initiator', 2), 'win')
        self.assertEqual(Solver._get_side_result('responder', 2), 'lose')
        self.assertEqual(Solver._get_side_result('initiator', -1), 'lose')
        self.assertEqual(Solver._get_side_result('responder', -1), 'win')
        self.assertEqual(Solver._get_side_result('initiator', 0), 'tie')
        self.assertIsNone(Solver._get_side_result('responder', None))

    def test_solver_dice(self):
        """ 3 dice from -1 to +1: -3 to +3, centered on 0 """
        chances = self.env['battle.solver']._get_roll_chances()
        self.assertEqual(sorted(chances), [-3, -2, -1, 0, 1, 2, 3])
        self.assertEqual([round(chances[total] * 27) for total in sorted(chances)], [1, 3, 6, 7, 6, 3, 1])
        self.assertAlmostEqual(sum(chances.values()), 1)

    @users('battle_admin')
    def test_solver_simulate(self):
        """ Simulation gives chances of each score, capped to outcomes range;
        changing sides or stances resets it """
        solver = self._new_solver_form(self.location_isca).save()
        solver.action_simulate()
        self.assertEqual(solver.mode, 'simulate')
        self.assertFalse(solver.battle_outcome_id)

        # bonus +3: scores above +4 are capped
        chances = solver._get_score_chances()
        self.assertEqual(sorted(chances), [0, 1, 2, 3, 4])
        self.assertEqual([round(chances[score] * 27) for score in sorted(chances)], [1, 3, 6, 7, 10])
        self.assertIn('Major Victory', solver.simulation_summary)
        self.assertIn('37.0', solver.simulation_summary)

        # changing sides or stances resets result
        solver_form = Form(solver)
        solver_form.initiator_unit_ids.remove(id=self.unit_werewolf_1.id)
        solver = solver_form.save()
        self.assertFalse(solver.mode)
        solver.action_simulate()
        solver.responder_stance = 'attack'
        self.assertFalse(solver.mode)

    @users('battle_admin')
    def test_solver_battle(self):
        """ Battle rolls dice, stores outcome and result, keeps wizard open;
        simulating again clears it """
        solver = self._new_solver_form(self.location_isca).save()
        with patch.object(BattleSolver, '_roll_dice', return_value=[-1, -1, 0]):
            action = solver.action_battle()
        self.assertEqual(solver.mode, 'battle')
        self.assertEqual(solver.dice_roll, '-1 -1 +0')
        self.assertEqual(solver.result_score, 1)
        self.assertEqual(solver.battle_outcome_id, self.env.ref('odoo_battle.battle_outcome_narrow_victory'))
        self.assertEqual(solver.result_message, 'Roll -1 -1 +0 (-2), bonus +3, score +1. '
                         'Damage: 0 to Test Bad, 0 to Test Good.')
        self.assertEqual((action['res_id'], action['target']), (solver.id, 'new'), 'Wizard stays open to display result')

        # capped score
        with patch.object(BattleSolver, '_roll_dice', return_value=[1, 1, 1]):
            solver.action_battle()
        self.assertEqual(solver.result_score, 4)
        self.assertEqual(solver.battle_outcome_id, self.env.ref('odoo_battle.battle_outcome_major_victory'))

        # real roll: bonus +3, score from 0 to +4
        solver.action_battle()
        self.assertIn(solver.battle_outcome_id.score, range(0, 5))
        self.assertIn(solver.battle_outcome_id.name, solver.result_summary)

        # simulating clears battle result
        solver.action_simulate()
        self.assertFalse(solver.battle_outcome_id)
        self.assertFalse(solver.dice_roll)

    @users('battle_admin')
    def test_solver_errors(self):
        """ Sides must be complete and distinct """
        solver = self._new_solver_form(self.location_isca).save()

        # unit on both sides
        solver.responder_unit_ids += self.unit_werewolf_1
        with self.assertRaises(UserError):
            solver.action_simulate()

        # missing units on one side
        solver.responder_unit_ids = False
        with self.assertRaises(UserError):
            solver.action_simulate()
        with self.assertRaises(UserError):
            solver.action_battle()
        self.assertFalse(solver.mode)

        # missing factions
        solver.responder_faction_ids = False
        with self.assertRaises(UserError):
            solver.action_simulate()

        # faction on both sides
        solver.write({
            'responder_faction_ids': [(6, 0, (self.faction_good + self.faction_bad).ids)],
            'responder_unit_ids': [(6, 0, self.unit_vampire_1.ids)],
        })
        with self.assertRaises(UserError):
            solver.action_simulate()

    @users('battle_user')
    def test_solver_regular_user(self):
        """ Only admins may run battles """
        with self.assertRaises(AccessError):
            self.env['battle.solver'].create({'battle_location_id': self.location_isca.id})

    @users('battle_admin')
    def test_solver_location_summary(self):
        """ Location summary displays status, holder, properties and twin """
        self.location_isca.sudo().write({
            'battle_trait_ids': self.trait_fortified.ids,
            'is_umbra': True,
            'linked_location_id': self.location_londinium.id,
            'held_by_faction_id': self.faction_bad.id,
            'status': 'held',
        })
        solver_form = self._new_solver_form(self.location_isca)
        summary = str(solver_form.battle_location_summary)
        self.assertIn('Held', summary)
        self.assertIn('Test Bad', summary)
        self.assertIn('Test Fortified', summary)
        self.assertIn('Umbra', summary)
        self.assertIn('Londinium', summary)

    @users('battle_admin')
    def test_solver_external_location(self):
        """ External locations are off the battlefield """
        self.location_isca.sudo().is_external = True
        solver = self._new_solver_form(self.location_isca).save()
        with self.assertRaises(UserError):
            solver.action_simulate()
        self.assertFalse(solver.mode)

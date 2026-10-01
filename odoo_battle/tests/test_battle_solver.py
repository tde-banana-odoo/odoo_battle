from unittest.mock import patch

from odoo.addons.odoo_battle.tests.common import BattleCommon
from odoo.addons.odoo_battle.wizard.battle_solver import BattleSolver
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import Form, users


class TestBattleSolver(BattleCommon):

    @users('battle_admin')
    def test_battle(self):
        """ Battle rolls dice, stores outcome and result, keeps wizard open;
        simulating again clears it """
        solver = self._new_solver_form(self.location_isca).save()
        with patch.object(BattleSolver, '_roll_dice', return_value=[-1, -1, 0]):
            action = solver.action_battle()
        self.assertRecordValues(solver, [{
            'mode': 'battle',
            'dice_roll': '-1 -1 +0',
            'result_score': 1,
            'battle_outcome_id': self.env.ref('odoo_battle.battle_outcome_narrow_victory').id,
            'result_message': 'Roll -1 -1 +0 (-2), bonus +3, score +1. Damage: 0 to Test Bad, 0 to Test Good.',
        }])
        self.assertEqual((action['res_id'], action['target']), (solver.id, 'new'), 'Wizard stays open to display result')

        # capped score
        with patch.object(BattleSolver, '_roll_dice', return_value=[1, 1, 1]):
            solver.action_battle()
        self.assertRecordValues(solver, [{'result_score': 4, 'battle_outcome_id': self.env.ref('odoo_battle.battle_outcome_major_victory').id}])

        # real roll: bonus +3, score from 0 to +4
        solver.action_battle()
        self.assertIn(solver.battle_outcome_id.score, range(0, 5))
        self.assertIn(solver.battle_outcome_id.name, solver.result_summary)

        solver.action_simulate()
        self.assertRecordValues(solver, [{'battle_outcome_id': False, 'dice_roll': False}])

    @users('battle_admin')
    def test_battle_damage(self):
        """ Damage: damage of a side when attacking (+ traits, + outcome)
        minus resistance of the other side (+ outcome), at least 0 """
        (self.unit_werewolf_1 + self.unit_werewolf_2).sudo().write({'resistance': 0, 'battle_trait_ids': self.trait_fury.ids})
        self.unit_vampire_1.sudo().write({'resistance': 1, 'battle_trait_ids': self.trait_counter.ids})
        self.env['battle.outcome'].search([('score', '=', 2)]).sudo().write({'initiator_damage': 1, 'responder_resistance': 4})
        solver = self._new_solver_form(self.location_isca).save()
        outcomes = {outcome.score: outcome for outcome in self.env['battle.outcome'].search([])}
        # initiators: damage 2 + 2, resistance 0; responders: damage 3, resistance 1
        for responder_stance, score, expected in [
            ('defense', 0, (3, 0)),  # defending responders deal no damage
            ('defense', 1, (5, 0)),  # initiators win: fury x2
            ('defense', -1, (3, 1)),  # responders win: counter-attack
            ('defense', 2, (2, 0)),  # outcome: initiators +1 damage, responders +4 resistance
            ('attack', 0, (3, 3)),  # attacking responders deal damage
            ('attack', -1, (3, 3)),  # counter-attack requires defending
        ]:
            with self.subTest(responder_stance=responder_stance, score=score):
                solver.responder_stance = responder_stance
                self.assertEqual(solver._get_damage(outcomes[score]), expected)

        solver.responder_stance = 'defense'
        with patch.object(BattleSolver, '_roll_dice', return_value=[-1, -1, 0]):
            solver.action_battle()
        self.assertRecordValues(solver, [{'result_score': 1, 'damage_to_responders': 5, 'damage_to_initiators': 0}])
        self.assertIn('Damage: 5 to Test Bad, 0 to Test Good.', solver.result_message)

    @users('battle_admin')
    def test_bonus(self):
        """ Isca: Rage 7 vs Willpower 6 (+1), Size 5 vs 2 (+2), morale 4 vs 3.
        Rage when attacking, Willpower when defending, Gnosis in Umbra;
        fortifications only help defending responders; low morale is a malus """
        solver = self._new_solver_form(self.location_isca).save()
        for umbra, fortified, morales, stances, expected, detail in [
            (False, False, ('4', '3'), ('attack', 'defense'), (3, 0, 3), 'Rage 7 vs Willpower 6'),
            (False, True, ('4', '3'), ('attack', 'defense'), (3, 1, 2), 'Rage 7 vs Willpower 6'),
            (False, True, ('4', '2'), ('attack', 'defense'), (3, 0, 3), 'Rage 7 vs Willpower 6'),
            (False, True, ('1', '2'), ('attack', 'defense'), (2, 0, 2), 'Rage 7 vs Willpower 6'),
            (False, True, ('4', '3'), ('attack', 'attack'), (4, 0, 4), 'Rage 7 vs Rage 1'),
            (False, True, ('4', '3'), ('defense', 'defense'), (3, 1, 2), 'Willpower 9 vs Willpower 6'),
            (True, False, ('4', '3'), ('attack', 'defense'), (4, 0, 4), 'Gnosis 7 vs Gnosis 0'),
            (True, False, ('4', '3'), ('attack', 'attack'), (4, 0, 4), 'Gnosis 7 vs Gnosis 0'),
        ]:
            with self.subTest(umbra=umbra, fortified=fortified, morales=morales, stances=stances):
                self.location_isca.sudo().write({
                    'is_umbra': umbra,
                    'battle_trait_ids': [Command.set(self.trait_fortified.ids if fortified else [])],
                })
                self.faction_good.sudo().morale, self.faction_bad.sudo().morale = morales
                solver.write({'initiator_stance': stances[0], 'responder_stance': stances[1]})
                self.assertEqual(self._get_bonus(solver), expected)
                self.assertIn(detail, solver.bonus_summary)

    @users('battle_admin')
    def test_bonus_traits(self):
        """ Battle bonus traits: unique ones count once per side, location
        traits apply depending on stance """
        (self.unit_werewolf_1 + self.unit_werewolf_2).sudo().battle_trait_ids = self.trait_leadership
        self.location_isca.sudo().battle_trait_ids = self.trait_ambush
        solver = self._new_solver_form(self.location_isca).save()
        lines = {line['name']: (line['initiator'], line['responder']) for line in solver._get_bonus_lines()}
        self.assertEqual((lines['Test Leadership'], lines['Test Ambush']), ((1, 0), (0, 1)))
        self.assertEqual(self._get_bonus(solver), (4, 1, 3))

        solver.responder_stance = 'attack'
        self.assertNotIn('Test Ambush', [line['name'] for line in solver._get_bonus_lines()])

    @users('battle_admin')
    def test_errors(self):
        """ Battles require complete and distinct sides, a location on the
        battlefield, and a round to be logged (not simulations) """
        solver = self._new_solver_form(self.location_isca).save()
        for vals in [
            {'responder_unit_ids': (self.unit_vampire_1 + self.unit_werewolf_1).ids},  # unit on both sides
            {'responder_unit_ids': []},  # missing units
            {'responder_faction_ids': []},  # missing factions
            {'responder_faction_ids': (self.faction_good + self.faction_bad).ids},  # faction on both sides
        ]:
            with self.subTest(vals=vals):
                defaults = {'responder_unit_ids': self.unit_vampire_1.ids, 'responder_faction_ids': self.faction_bad.ids}
                solver.write({fname: [(6, 0, ids)] for fname, ids in {**defaults, **vals}.items()})
                with self.assertRaises(UserError):
                    solver.action_simulate()
                with self.assertRaises(UserError):
                    solver.action_battle()
                self.assertFalse(solver.mode)

        solver = self._new_solver_form(self.location_isca).save()
        solver.battle_round_id = False
        solver.action_simulate()
        with self.assertRaises(UserError):
            solver.action_battle()

        self.location_isca.sudo().is_external = True
        with self.assertRaises(UserError):
            self._new_solver_form(self.location_isca).save().action_simulate()

    @users('battle_admin')
    def test_location_summary(self):
        """ Location summary displays status, holder, traits, Umbra and twin """
        self.location_isca.sudo().write({
            'battle_trait_ids': self.trait_fortified.ids,
            'is_umbra': True,
            'linked_location_id': self.location_londinium.id,
            'held_by_faction_id': self.faction_bad.id,
            'status': 'held',
        })
        summary = str(self._new_solver_form(self.location_isca).battle_location_summary)
        for expected in ('Held', 'Test Bad', 'Test Fortified', 'Umbra', 'Londinium'):
            self.assertIn(expected, summary)

    @users('battle_admin')
    def test_sides(self):
        """ Free location: the defender camp responds, other factions
        initiate. Initiators attack, responders defend. Sides can be swapped
        and are reloaded when changing location. """
        solver_form = self._new_solver_form(self.location_isca)
        self.assertEqual(solver_form.initiator_faction_ids.ids, self.faction_good.ids)
        self.assertEqual(solver_form.responder_faction_ids.ids, self.faction_bad.ids)
        self.assertEqual((solver_form.initiator_stance, solver_form.responder_stance), ('attack', 'defense'))
        self.assertEqual(set(solver_form.initiator_unit_ids.ids), set((self.unit_werewolf_1 + self.unit_werewolf_2).ids))
        self.assertEqual(solver_form.responder_unit_ids.ids, self.unit_vampire_1.ids)
        self.assertEqual((solver_form.initiator_menace, solver_form.responder_menace), (5, 4))

        solver_form.initiator_faction_ids.clear()
        solver_form.initiator_faction_ids.add(self.faction_bad)
        solver_form.responder_faction_ids.clear()
        solver_form.responder_faction_ids.add(self.faction_good)
        self.assertEqual(solver_form.initiator_unit_ids.ids, self.unit_vampire_1.ids)
        self.assertEqual(set(solver_form.responder_unit_ids.ids), set((self.unit_werewolf_1 + self.unit_werewolf_2).ids))

        # only responders in Londinium
        solver_form.battle_location_id = self.location_londinium
        self.assertEqual(len(solver_form.initiator_faction_ids), 0)
        self.assertEqual(solver_form.responder_unit_ids.ids, self.unit_vampire_2.ids)

    @users('battle_admin')
    def test_sides_allies_and_holders(self):
        """ Allies fight along their faction; held location: holders and
        their allies respond; units without faction do not fight """
        faction_neutral = self.env['battle.faction'].sudo().create({
            'name': 'Test Neutral', 'role': 'neutral', 'allied_faction_id': self.faction_good.id,
        })
        unit_neutral = self.env['battle.unit'].sudo().create({
            'name': 'Test Neutral Unit', 'unit_type': 'spirit',
            'battle_faction_id': faction_neutral.id, 'battle_location_id': self.location_isca.id,
        })
        self.unit_werewolf_2.sudo().battle_faction_id = False

        solver_form = self._new_solver_form(self.location_isca)
        self.assertEqual(set(solver_form.initiator_faction_ids.ids), set((self.faction_good + faction_neutral).ids))
        self.assertEqual(set(solver_form.initiator_unit_ids.ids), set((self.unit_werewolf_1 + unit_neutral).ids))

        self.location_isca.sudo().write({'status': 'held', 'held_by_faction_id': self.faction_good.id})
        solver_form = self._new_solver_form(self.location_isca)
        self.assertEqual(set(solver_form.responder_faction_ids.ids), set((self.faction_good + faction_neutral).ids))
        self.assertEqual(solver_form.initiator_unit_ids.ids, self.unit_vampire_1.ids)

    @users('battle_admin')
    def test_simulate(self):
        """ Simulation gives chances of each score, capped to outcomes range;
        changing sides or stances resets it """
        solver = self._new_solver_form(self.location_isca).save()
        solver.action_simulate()
        self.assertRecordValues(solver, [{'mode': 'simulate', 'battle_outcome_id': False}])

        # bonus +3: scores above +4 are capped
        chances = solver._get_score_chances()
        self.assertEqual({score: round(chance * 27) for score, chance in chances.items()}, {0: 1, 1: 3, 2: 6, 3: 7, 4: 10})
        self.assertIn('Major Victory', solver.simulation_summary)
        self.assertIn('37.0', solver.simulation_summary)

        solver_form = Form(solver)
        solver_form.initiator_unit_ids.remove(id=self.unit_werewolf_1.id)
        self.assertFalse(solver_form.save().mode)
        solver.action_simulate()
        solver.responder_stance = 'attack'
        self.assertFalse(solver.mode)


class TestBattleSolverAccess(BattleCommon):

    @users('battle_user')
    def test_access_regular_user(self):
        """ Only admins may run battles """
        with self.assertRaises(AccessError):
            self.env['battle.solver'].create({'battle_location_id': self.location_isca.id})


class TestBattleSolverInternals(BattleCommon):

    def test_bonus_rules(self):
        """ Comparison rules used by bonuses, including edge cases """
        Solver = self.env['battle.solver']
        for rule, values, expected in [
            (Solver._bonus_more_or_double, (5, 5), (0, 0)),
            (Solver._bonus_more_or_double, (7, 6), (1, 0)),  # more
            (Solver._bonus_more_or_double, (12, 6), (1, 0)),  # double is not more than double
            (Solver._bonus_more_or_double, (13, 6), (2, 0)),  # more than double
            (Solver._bonus_more_or_double, (6, 7), (0, 1)),
            (Solver._bonus_more_or_double, (3, 0), (2, 0)),  # positive vs null or negative: more than double
            (Solver._bonus_more_or_double, (3, -1), (2, 0)),
            (Solver._bonus_more_or_double, (-1, -3), (1, 0)),
            (Solver._bonus_per_half_more, (3, 3), (0, 0)),
            (Solver._bonus_per_half_more, (4, 3), (0, 0)),  # less than 50% more
            (Solver._bonus_per_half_more, (3, 2), (1, 0)),  # 50% more
            (Solver._bonus_per_half_more, (4, 2), (2, 0)),  # 100% more
            (Solver._bonus_per_half_more, (7, 2), (2, 0)),  # max +2
            (Solver._bonus_per_half_more, (2, 3), (0, 1)),
            (Solver._bonus_per_half_more, (1, 0), (2, 0)),
        ]:
            with self.subTest(rule=rule.__name__, values=values):
                self.assertEqual(rule(*values), expected)

    def test_dice(self):
        """ 3 dice from -1 to +1: -3 to +3, centered on 0 """
        chances = self.env['battle.solver']._get_roll_chances()
        self.assertEqual({total: round(chance * 27) for total, chance in chances.items()}, {-3: 1, -2: 3, -1: 6, 0: 7, 1: 6, 2: 3, 3: 1})

    def test_side_morale(self):
        """ Several factions in a side: majority wins, first faction on tie,
        side faction without units """
        good, bad = self.faction_good, self.faction_bad
        for units, factions, expected in [
            (self.unit_werewolf_1 + self.unit_vampire_1 + self.unit_vampire_2, good + bad, 3),  # majority
            (self.unit_werewolf_1 + self.unit_vampire_1, good + bad, 4),  # tie
            (self.env['battle.unit'], bad, 3),  # no units
        ]:
            with self.subTest(units=units.mapped('name')):
                self.assertEqual(self.env['battle.solver']._get_side_morale(units, factions), expected)

    def test_side_result(self):
        """ Score is given from initiators point of view """
        for side, score, expected in [
            ('initiator', 2, 'win'),
            ('responder', 2, 'lose'),
            ('initiator', -1, 'lose'),
            ('responder', -1, 'win'),
            ('initiator', 0, 'tie'),
            ('responder', None, None),
        ]:
            with self.subTest(side=side, score=score):
                self.assertEqual(self.env['battle.solver']._get_side_result(side, score), expected)

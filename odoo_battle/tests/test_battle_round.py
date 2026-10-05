from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo.addons.odoo_battle.tests.common import BattleCommon
from odoo.addons.odoo_battle.wizard.battle_solver import BattleSolver
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged, users
from odoo.tools import mute_logger


@tagged('battle_round')
class TestBattleRound(BattleCommon):

    @users('battle_admin')
    def test_dashboard(self):
        """ Dashboard summarizes the current round: Caern, camps leadership,
        factions, leaders, locations (forces, leaders), battles to solve
        (both sides present, no result yet), solved ones, unplaced units """
        self.battle_round.with_env(self.env).write({
            'aggressor_command_action_count': 2,
            'aggressor_command_action_ids': [
                Command.create({'camp': 'aggressor', 'command_type': 'hold_on', 'battle_location_id': self.location_isca.id}),
            ],
        })
        unplaced = self.env['battle.unit'].create({'name': 'Test Unplaced', 'unit_type': 'spirit'})

        leader, champion = self.env['battle.leader'].create([
            {'name': 'Test Leader', 'battle_faction_id': self.faction_good.id, 'battle_location_id': self.location_isca.id},
            {'name': 'Test Champion', 'battle_faction_id': self.faction_good.id, 'is_champion': True, 'wound_state': '2'},
        ])
        self.faction_good.with_env(self.env).leader_id = leader
        self.battle_round.with_env(self.env).caern_state = '3'
        round_number = self.battle_round.round_number
        self.env['battle.location.effect'].create([
            {'battle_location_id': self.location_isca.id, 'battle_faction_id': self.faction_good.id,
             'battle_trait_id': self.trait_breakthrough.id, 'round_number': round_number},
            {'battle_location_id': self.location_isca.id, 'battle_faction_id': self.faction_bad.id,
             'battle_trait_id': self.trait_heroic_defense.id, 'round_number': round_number + 1},
        ])

        data = self.env['battle.round'].get_dashboard_data()
        self.assertEqual((data['round']['id'], data['round']['caern_label']), (self.battle_round.id, 'Weakened'))
        camps = {camp['camp']: camp for camp in data['camps']}
        self.assertEqual(
            (camps['aggressor']['morale'], camps['aggressor']['command_actions'], camps['aggressor']['command_actions_picked']),
            ('Outstanding', 2, ['Hold On (Isca Augusta)']),
        )
        self.assertIn('Test Good', camps['aggressor']['factions'])
        self.assertEqual((camps['defender']['morale'], camps['defender']['command_actions']), ('Steady', 0))
        factions = {faction['name']: faction for faction in data['factions']}
        self.assertEqual(factions['Test Good']['unit_count'], 2)
        self.assertEqual(factions['Test Good']['leader']['name'], 'Test Leader')
        leaders = {leader['name']: leader for leader in data['leaders']}
        self.assertEqual(
            (leaders['Test Leader']['is_faction_leader'], leaders['Test Champion']['is_champion'], leaders['Test Champion']['wound_label']),
            (True, True, 'Badly Wounded'),
        )
        isca = next(location for location in data['locations'] if location['id'] == self.location_isca.id)
        self.assertEqual(isca['forces'], [{'faction': 'Test Good', 'count': 2, 'menace': 5}, {'faction': 'Test Bad', 'count': 1, 'menace': 4}])
        self.assertEqual(isca['leaders'], ['Test Leader'])
        self.assertEqual(
            (isca['effects'], isca['next_effects']),
            ([f'Test Good: {self.trait_breakthrough.name}'], [f'Test Bad: {self.trait_heroic_defense.name}']),
        )
        pending = [location['id'] for location in data['pending']]
        self.assertIn(self.location_isca.id, pending)
        self.assertEqual(isca['battle'], {'state': 'pending'})
        self.assertNotIn(self.location_londinium.id, pending, 'Only responders in Londinium')
        self.assertIn(unplaced.id, [unit['id'] for unit in data['unplaced_units']])

        self._battle(self.location_isca, roll=(1, 1, 1))
        data = self.env['battle.round'].get_dashboard_data()
        self.assertNotIn(self.location_isca.id, [location['id'] for location in data['pending']])
        self.assertEqual([result['location'] for result in data['results']], ['Isca Augusta'])
        # solved: winner (main faction of the winning side) and its outcome
        isca = next(location for location in data['locations'] if location['id'] == self.location_isca.id)
        self.assertEqual(isca['battle'], {'state': 'done', 'summary': 'Test Good Major Victory'})
        londinium = next(location for location in data['locations'] if location['id'] == self.location_londinium.id)
        self.assertFalse(londinium['battle'], 'No opposing forces, no battle')

        # held locations show their holder color
        self.faction_bad.with_env(self.env).color = 10
        self.location_londinium.with_env(self.env).write({'status': 'held', 'held_by_faction_id': self.faction_bad.id})
        londinium = next(location for location in self.env['battle.round'].get_dashboard_data()['locations'] if location['id'] == self.location_londinium.id)
        self.assertEqual((londinium['holder'], londinium['holder_color']), ('Test Bad', 10))

    @users('battle_admin')
    def test_dashboard_leadership(self):
        """ Camps leadership is entered from the dashboard, on the current
        round; morale trend is given compared to the previous round """
        action = self.env['battle.round'].action_open_leadership()
        self.assertEqual((action['res_model'], action['res_id']), ('battle.round', self.battle_round.id))

        self.env['battle.round'].create({'aggressor_morale': '3'})
        trends = {camp['camp']: camp['morale_trend'] for camp in self.env['battle.round'].get_dashboard_data()['camps']}
        self.assertEqual(trends, {'aggressor': 'down', 'defender': 'same'})

    @users('battle_admin')
    def test_location_effects(self):
        """ Location effects are edited round by round: those of the round
        are listed, new ones apply to it; effects granted for a round not
        created yet are linked to it when it starts """
        battle_round = self.battle_round.with_env(self.env)
        round_number = battle_round.round_number
        Effect = self.env['battle.location.effect']
        previous, next_one = Effect.create([{
            'battle_location_id': self.location_isca.id, 'battle_faction_id': self.faction_good.id,
            'battle_trait_id': self.trait_breakthrough.id, 'round_number': number,
        } for number in (round_number - 1, round_number + 1)])
        test_locations = self.location_isca + self.location_londinium
        battle_round.write({'battle_location_effect_ids': [
            Command.create({'battle_location_id': location.id, 'battle_faction_id': self.faction_bad.id, 'battle_trait_id': self.trait_fortified.id})
            for location in test_locations
        ]})
        effects = battle_round.battle_location_effect_ids.filtered(lambda effect: effect.battle_location_id in test_locations)
        self.assertEqual(effects.battle_location_id, test_locations)
        self.assertEqual(set(effects.mapped('round_number')), {round_number}, 'New effects apply to the round')
        self.assertNotIn(previous, battle_round.battle_location_effect_ids, 'Other rounds effects not listed')

        battle_round.write({'battle_location_effect_ids': [Command.delete(effects[0].id)]})
        self.assertFalse(effects[0].exists())

        self.assertFalse(next_one.battle_round_id, 'Granted for a round not started yet')
        next_round = self.env['battle.round'].action_start_next_round()
        self.assertEqual(next_one.battle_round_id, next_round)
        self.assertIn(next_one, next_round.battle_location_effect_ids)

    @users('battle_admin')
    def test_result(self):
        """ Battles are logged in the current round with their outcome """
        solver = self._battle(self.location_isca, roll=(0, -1, 0))
        self.assertRecordValues(solver.battle_result_id, [{
            'battle_round_id': self.battle_round.id,
            'battle_location_id': self.location_isca.id,
            'state': 'done',
            'battle_outcome_id': solver.battle_outcome_id.id,
            'result_score': 1,
            'initiator_faction_ids': self.faction_good.ids,
        }])
        self.assertEqual(
            [(line.side, line.battle_unit_id) for line in solver.battle_result_id.battle_result_line_ids],
            [('initiator', self.unit_werewolf_1), ('initiator', self.unit_werewolf_2), ('responder', self.unit_vampire_1)],
        )
        self.assertEqual(self.battle_round.battle_result_ids, solver.battle_result_id)

    @users('battle_admin')
    def test_result_consequences(self):
        """ Battles apply damage on units (wounds every 3 damage), logged per
        unit; cancelling the result reverts units as before the battle """
        self.unit_vampire_1.sudo().resistance = 0
        result = self._battle(self.location_isca, roll=(0, 0, 0)).battle_result_id
        # victory (+2): initiators deal (2 + 2) x 150%; responders defend: 3 x 50% vs resistance 20
        self.assertRecordValues(self.unit_vampire_1, [{'damage_counter': 0, 'wound_state': '2'}])
        self.assertRecordValues(result.battle_result_line_ids.filtered(lambda line: line.battle_unit_id == self.unit_vampire_1), [{
            'side': 'responder', 'position': 'frontline', 'damage': 6, 'wounds': 2,
            'damage_counter_before': 0, 'wound_state_before': '4',
        }])
        result.action_cancel()
        self.assertRecordValues(self.unit_vampire_1, [{'damage_counter': 0, 'wound_state': '4'}])

    @users('battle_admin')
    def test_result_solved_and_cancel(self):
        """ Solved locations are flagged in the solver (round in context);
        cancelling from the solver reverts the result and opens a fresh one """
        self.unit_vampire_1.sudo().resistance = 0
        context = {'battle_round_id': self.battle_round.id}
        self.assertEqual(self.location_isca.with_context(context).display_name, 'Isca Augusta')
        result = self._battle(self.location_isca).battle_result_id
        self.assertEqual(self.location_isca.with_context(context).display_name, 'Isca Augusta (Solved)')
        self.assertEqual(self.location_isca.display_name, 'Isca Augusta', 'Only flagged with a round')
        self.assertEqual(self.unit_vampire_1.wound_state, '2')

        solver = self._new_solver_form(self.location_isca).save()
        action = solver.action_cancel_existing_result()
        self.assertRecordValues(result, [{'state': 'cancel'}])
        self.assertEqual(self.unit_vampire_1.wound_state, '4', 'Consequences reverted')
        self.assertEqual(action['context']['active_id'], self.location_isca.id, 'Fresh solver for the same location')
        solver.invalidate_recordset()
        self.assertEqual((solver.existing_battle_result_id, solver.cancelled_result_count), (self.env['battle.result'], 1))

    @users('battle_admin')
    def test_result_wound_traits(self):
        """ Wound traits wound enemy units; heal traits heal own units (one
        wound less), mend traits reset their damage counter: prefilled when
        launching, applied (vampire 1 takes no damage here) """
        wound, heal, mend = self.env['battle.trait'].sudo().create([
            {'name': 'Test Wound', 'effect': 'wound_enemy'},
            {'name': 'Test Heal', 'effect': 'heal_self'},
            {'name': 'Test Mend', 'effect': 'mend_self'},
        ])
        for holder, trait, expected in [
            (self.unit_werewolf_1, wound, ('3', '2', 2)),  # initiators wound vampire 1
            (self.unit_vampire_1, heal, ('3', '4', 2)),  # vampire 1 heals itself
            (self.unit_vampire_1, mend, ('2', '2', 0)),  # vampire 1 mends itself, keeping its wounds
        ]:
            before, wound_state, damage_counter = expected
            with self.subTest(trait=trait.name):
                self.unit_vampire_1.sudo().write({'wound_state': before, 'damage_counter': 2})
                self.location_isca.sudo().status = 'free'  # same sides each time (victories shift the location)
                (self.unit_werewolf_1 + self.unit_vampire_1).sudo().battle_trait_ids = False
                holder.sudo().battle_trait_ids = trait
                self.env['battle.round'].create({})  # new round: no result to replace
                self._battle(self.location_isca)
                self.assertEqual((self.unit_vampire_1.wound_state, self.unit_vampire_1.damage_counter), (wound_state, damage_counter))

    @users('battle_admin')
    def test_result_assassination(self):
        """ Assassinations wound their target before rolling: applied (and
        logged) when solving the battle """
        self.unit_werewolf_1.sudo().battle_trait_ids = self.trait_assassin
        solver = self._new_solver_form(self.location_isca).save()
        solver.initiator_line_ids.filtered(lambda line: line.battle_unit_id == self.unit_werewolf_1).target_unit_id = self.unit_vampire_1
        with patch.object(BattleSolver, '_roll_dice', return_value=[0, 0, 0]):
            solver.action_launch()
        solver.action_apply()
        self.assertEqual(self.unit_vampire_1.wound_state, '3', 'Assassinated, no damage (resistance 10 x 150%)')
        self.assertRecordValues(solver.battle_result_id.battle_result_line_ids.filtered(lambda line: line.battle_unit_id == self.unit_vampire_1), [
            {'damage': 0, 'wounds': 1, 'wound_state_before': '4'},
        ])

    @users('battle_admin')
    def test_result_next_round(self):
        """ Each round has its own results """
        first = self._battle(self.location_isca).battle_result_id
        next_round = self.env['battle.round'].create({})
        second = self._battle(self.location_isca).battle_result_id
        self.assertRecordValues(first + second, [
            {'battle_round_id': self.battle_round.id, 'state': 'done'},
            {'battle_round_id': next_round.id, 'state': 'done'},
        ])

    @users('battle_admin')
    def test_result_replace(self):
        """ One result per location and round: cancel it to battle again """
        first = self._battle(self.location_isca).battle_result_id
        solver = self._new_solver_form(self.location_isca).save()
        self.assertEqual(solver.existing_battle_result_id, first)
        with self.assertRaises(UserError):
            solver.action_launch()

        solver.action_cancel_existing_result()
        second = self._battle(self.location_isca, roll=(1, 1, 1)).battle_result_id
        self.assertRecordValues(first + second, [
            {'state': 'cancel', 'result_score': 2},
            {'state': 'done', 'result_score': 4},
        ])
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            second.copy()


class TestBattleRoundInternals(BattleCommon):

    @users('battle_admin')
    def test_constraints_unique(self):
        """ Round numbers are unique """
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.env['battle.round'].create({'round_number': self.battle_round.round_number})

    @users('battle_admin')
    def test_creation(self):
        """ Rounds are numbered in sequence, the last one being the current
        one; camps morale and Caern are carried over, not command actions """
        self.battle_round.write({'caern_state': '2', 'defender_morale': '1', 'aggressor_command_action_count': 3})
        next_round = self.env['battle.round'].create({})
        self.assertEqual(next_round.round_number, self.battle_round.round_number + 1)
        self.assertEqual(self.env['battle.round']._get_current(), next_round)
        self.assertRecordValues(next_round, [{
            'caern_state': '2', 'aggressor_morale': '4', 'defender_morale': '1', 'aggressor_command_action_count': 0,
        }])

    @users('battle_admin')
    def test_leadership(self):
        """ Each camp picks at most its command actions, in locations """
        battle_round = self.battle_round.with_env(self.env)
        battle_round.aggressor_command_action_count = 1
        battle_round.aggressor_command_action_ids = [
            Command.create({'camp': 'aggressor', 'command_type': 'hold_on', 'battle_location_id': self.location_isca.id}),
        ]
        self.assertEqual(battle_round.aggressor_command_action_ids.mapped('display_name'), ['Hold On (Isca Augusta)'])
        self.assertFalse(battle_round.defender_command_action_ids)
        for values in [
            {'aggressor_command_action_count': 0},
            {'defender_command_action_ids': [Command.create({'camp': 'defender', 'command_type': 'retreat', 'battle_location_id': self.location_isca.id})]},
        ]:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                battle_round.write(values)

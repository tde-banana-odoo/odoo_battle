from psycopg2 import IntegrityError

from odoo.addons.odoo_battle.tests.common import BattleCommon
from odoo.tests import users
from odoo.tools import mute_logger


class TestBattleRound(BattleCommon):

    @users('battle_admin')
    def test_dashboard(self):
        """ Dashboard summarizes the current round: factions (leader,
        leadership), locations (forces, characters), battles to solve (both
        sides present, no result yet), solved ones, unplaced units """
        self.battle_round.battle_round_leadership_ids.filtered(
            lambda line: line.battle_faction_id == self.faction_good
        ).with_env(self.env).successes = 2
        unplaced = self.env['battle.unit'].create({'name': 'Test Unplaced', 'unit_type': 'spirit'})

        leader = self.env['battle.leader'].create({
            'name': 'Test Leader', 'battle_faction_id': self.faction_good.id, 'battle_location_id': self.location_isca.id,
        })
        self.faction_good.with_env(self.env).leader_id = leader

        data = self.env['battle.round'].get_dashboard_data()
        self.assertEqual(data['round']['id'], self.battle_round.id)
        factions = {faction['name']: faction for faction in data['factions']}
        self.assertEqual((factions['Test Good']['leadership'], factions['Test Good']['unit_count']), (2, 2))
        self.assertEqual(factions['Test Good']['leader']['name'], 'Test Leader')
        isca = next(location for location in data['locations'] if location['id'] == self.location_isca.id)
        self.assertEqual(isca['forces'], [{'faction': 'Test Good', 'count': 2}, {'faction': 'Test Bad', 'count': 1}])
        self.assertEqual(isca['leaders'], ['Test Leader'])
        pending = [location['id'] for location in data['pending']]
        self.assertIn(self.location_isca.id, pending)
        self.assertNotIn(self.location_londinium.id, pending, 'Only responders in Londinium')
        self.assertIn(unplaced.id, [unit['id'] for unit in data['unplaced_units']])

        self._battle(self.location_isca)
        data = self.env['battle.round'].get_dashboard_data()
        self.assertNotIn(self.location_isca.id, [location['id'] for location in data['pending']])
        self.assertEqual([result['location'] for result in data['results']], ['Isca Augusta'])

    @users('battle_admin')
    def test_dashboard_leadership(self):
        """ Leadership rolls are entered from the dashboard; morale trend is
        given compared to the previous round """
        action = self.env['battle.round'].action_open_leadership(self.faction_good.id)
        line = self.env['battle.round.leadership'].browse(action['res_id'])
        self.assertEqual((line.battle_round_id, line.battle_faction_id), (self.battle_round, self.faction_good))

        self.env['battle.round'].create({})
        self.faction_good.with_env(self.env).morale = '3'
        trends = {faction['name']: faction['morale_trend'] for faction in self.env['battle.round'].get_dashboard_data()['factions']}
        self.assertEqual((trends['Test Good'], trends['Test Bad']), ('down', 'same'))

    @users('battle_admin')
    def test_result(self):
        """ Battles are logged in the current round with their outcome """
        solver = self._battle(self.location_isca, roll=(-1, -1, 0))
        self.assertRecordValues(solver.battle_result_id, [{
            'battle_round_id': self.battle_round.id,
            'battle_location_id': self.location_isca.id,
            'state': 'done',
            'battle_outcome_id': solver.battle_outcome_id.id,
            'result_score': 1,
            'initiator_faction_ids': self.faction_good.ids,
            'responder_unit_ids': self.unit_vampire_1.ids,
        }])
        self.assertEqual(self.battle_round.battle_result_ids, solver.battle_result_id)

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
        """ One result per location and round: battling again cancels and
        replaces it """
        first = self._battle(self.location_isca).battle_result_id
        solver = self._new_solver_form(self.location_isca).save()
        self.assertEqual(solver.existing_battle_result_id, first)

        second = self._battle(self.location_isca, roll=(1, 1, 1)).battle_result_id
        self.assertRecordValues(first + second, [
            {'state': 'cancel', 'result_score': 3},
            {'state': 'done', 'result_score': 4},
        ])
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            second.copy()


class TestBattleRoundInternals(BattleCommon):

    @users('battle_admin')
    def test_constraints_unique(self):
        """ Round numbers are unique; a faction rolls leadership once per round """
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.env['battle.round'].create({'round_number': self.battle_round.round_number})
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.env['battle.round.leadership'].create({
                'battle_round_id': self.battle_round.id,
                'battle_faction_id': self.faction_good.id,
            })

    @users('battle_admin')
    def test_creation(self):
        """ Rounds are numbered in sequence, the last one being the current
        one; each faction gets a leadership roll """
        next_round = self.env['battle.round'].create({})
        self.assertEqual(next_round.round_number, self.battle_round.round_number + 1)
        self.assertEqual(self.env['battle.round']._get_current(), next_round)
        self.assertEqual(next_round.battle_round_leadership_ids.battle_faction_id, self.env['battle.faction'].search([]))

from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo.addons.odoo_battle.tests.common import BattleCommon
from odoo.addons.odoo_battle.wizard.battle_solver import BattleSolver
from odoo.exceptions import UserError
from odoo.tests import Form, tagged, users
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestBattleRound(BattleCommon):

    def _battle(self, location, roll=(0, 0, 0)):
        """ Solve a battle in ``location`` with a given dice ``roll`` """
        solver = Form(self.env['battle.solver'].with_context(active_model='battle.location', active_id=location.id)).save()
        with patch.object(BattleSolver, '_roll_dice', return_value=list(roll)):
            solver.action_battle()
        return solver

    @users('battle_admin')
    def test_round_creation(self):
        """ Rounds are numbered in sequence, the last one being the current
        one; each faction gets a leadership roll """
        next_round = self.env['battle.round'].create({})
        self.assertEqual(next_round.round_number, self.battle_round.round_number + 1)
        self.assertEqual(self.env['battle.round']._get_current(), next_round)
        self.assertEqual(
            next_round.battle_round_leadership_ids.battle_faction_id,
            self.env['battle.faction'].search([]),
        )
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.env['battle.round'].create({'round_number': next_round.round_number})

    @users('battle_admin')
    def test_round_leadership_unique(self):
        """ A faction rolls leadership once per round """
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.env['battle.round.leadership'].create({
                'battle_round_id': self.battle_round.id,
                'battle_faction_id': self.faction_good.id,
            })

    @users('battle_admin')
    def test_battle_result(self):
        """ Battles are logged in the current round with their outcome """
        solver = self._battle(self.location_isca, roll=(-1, -1, 0))
        result = solver.battle_result_id
        self.assertEqual((result.battle_round_id, result.battle_location_id), (self.battle_round, self.location_isca))
        self.assertEqual(result.state, 'done')
        self.assertEqual(result.battle_outcome_id, solver.battle_outcome_id)
        self.assertEqual(result.result_score, 1)
        self.assertEqual(result.initiator_faction_ids, self.faction_good)
        self.assertEqual(result.responder_unit_ids, self.unit_vampire_1)
        self.assertEqual(self.battle_round.battle_result_ids, result)

    @users('battle_admin')
    def test_battle_result_replace(self):
        """ One result per location and round: battling again replaces it,
        cancelled results do not count """
        first = self._battle(self.location_isca).battle_result_id

        solver = Form(self.env['battle.solver'].with_context(active_model='battle.location', active_id=self.location_isca.id)).save()
        self.assertEqual(solver.existing_battle_result_id, first)
        with patch.object(BattleSolver, '_roll_dice', return_value=[1, 1, 1]):
            solver.action_battle()
        self.assertEqual(first.state, 'cancel')
        self.assertEqual(solver.battle_result_id.state, 'done')
        self.assertEqual(solver.battle_result_id.result_score, 4)

        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            solver.battle_result_id.copy()

    @users('battle_admin')
    def test_battle_result_next_round(self):
        """ Each round has its own results """
        first = self._battle(self.location_isca).battle_result_id
        next_round = self.env['battle.round'].create({})
        second = self._battle(self.location_isca).battle_result_id
        self.assertEqual(second.battle_round_id, next_round)
        self.assertEqual((first.state, second.state), ('done', 'done'))

    @users('battle_admin')
    def test_battle_requires_round(self):
        """ Battles are logged, hence require a round; simulation does not """
        solver = Form(self.env['battle.solver'].with_context(active_model='battle.location', active_id=self.location_isca.id)).save()
        solver.battle_round_id = False
        solver.action_simulate()
        with self.assertRaises(UserError):
            solver.action_battle()

    @users('battle_admin')
    def test_dashboard(self):
        """ Dashboard summarizes the current round: leadership, battles to
        solve (both sides present, no result yet), solved ones, unplaced units """
        self.battle_round.battle_round_leadership_ids.filtered(
            lambda line: line.battle_faction_id == self.faction_good
        ).with_env(self.env).successes = 2
        unplaced = self.env['battle.unit'].create({'name': 'Test Unplaced', 'unit_type': 'spirit'})

        data = self.env['battle.round'].get_dashboard_data()
        self.assertEqual(data['round']['id'], self.battle_round.id)
        factions = {faction['name']: faction for faction in data['factions']}
        self.assertEqual(factions['Test Good']['leadership'], 2)
        self.assertEqual(factions['Test Good']['unit_count'], 2)
        self.assertIn(self.location_isca.id, [location['id'] for location in data['pending']])
        self.assertNotIn(self.location_londinium.id, [location['id'] for location in data['pending']],
                         'Only responders in Londinium')
        self.assertIn(unplaced.id, [unit['id'] for unit in data['unplaced_units']])

        self._battle(self.location_isca)
        data = self.env['battle.round'].get_dashboard_data()
        self.assertNotIn(self.location_isca.id, [location['id'] for location in data['pending']])
        self.assertEqual([result['location'] for result in data['results']], ['Isca Augusta'])

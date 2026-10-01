from odoo.addons.odoo_battle.tests.common import BattleCommon
from odoo.exceptions import ValidationError
from odoo.tests import users


class TestBattleFactionInternals(BattleCommon):

    @users('battle_admin')
    def test_camp(self):
        """ Camp of a faction: itself, its ally if neutral, and neutral
        factions allied to those """
        good, bad = (self.faction_good + self.faction_bad).with_env(self.env)
        neutral_good, neutral_bad = self.env['battle.faction'].create([
            {'name': 'Test Neutral Good', 'role': 'neutral', 'allied_faction_id': good.id},
            {'name': 'Test Neutral Bad', 'role': 'neutral', 'allied_faction_id': bad.id},
        ])
        for faction, camp in [(good, good + neutral_good), (neutral_good, good + neutral_good), (neutral_bad, bad + neutral_bad)]:
            with self.subTest(faction=faction.name):
                self.assertEqual(faction._get_camp(), camp)

    @users('battle_admin')
    def test_constraints_ally(self):
        """ Only neutral factions have allies, never themselves """
        neutral = self.env['battle.faction'].create({'name': 'Test Neutral', 'role': 'neutral'})
        with self.assertRaises(ValidationError):
            self.faction_good.with_env(self.env).allied_faction_id = self.faction_bad
        with self.assertRaises(ValidationError):
            neutral.allied_faction_id = neutral

    @users('battle_admin')
    def test_morale(self):
        """ Morale is given by the current round leadership roll, and carried
        over to the next round """
        good = self.faction_good.with_env(self.env)
        line = self.battle_round.battle_round_leadership_ids.filtered(lambda line: line.battle_faction_id == good)
        self.assertEqual((good.morale, line.morale), ('4', '4'))
        good.morale = '2'
        self.assertEqual(line.morale, '2')

        next_round = self.env['battle.round'].create({})
        self.assertEqual(good.morale, '2')
        good.morale = '1'
        self.assertRecordValues(line + next_round.battle_round_leadership_ids.filtered(lambda line: line.battle_faction_id == good), [
            {'morale': '2'}, {'morale': '1'},
        ])

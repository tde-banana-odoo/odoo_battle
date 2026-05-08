from odoo.addons.odoo_battle.tests.common import BattleCommon
from odoo.exceptions import ValidationError
from odoo.tests import tagged, users


@tagged('post_install', '-at_install')
class TestBattleFaction(BattleCommon):

    @users('battle_admin')
    def test_faction_camp(self):
        """ Camp of a faction: itself, its ally if neutral, and neutral
        factions allied to those """
        good, bad = (self.faction_good + self.faction_bad).with_env(self.env)
        neutral_good, neutral_bad = self.env['battle.faction'].create([
            {'name': 'Test Neutral Good', 'role': 'neutral', 'allied_faction_id': good.id},
            {'name': 'Test Neutral Bad', 'role': 'neutral', 'allied_faction_id': bad.id},
        ])
        self.assertEqual(good._get_camp(), good + neutral_good)
        self.assertEqual(neutral_good._get_camp(), good + neutral_good)
        self.assertEqual(neutral_bad._get_camp(), bad + neutral_bad)

    @users('battle_admin')
    def test_faction_ally_constraints(self):
        """ Only neutral factions have allies, never themselves """
        neutral = self.env['battle.faction'].create({'name': 'Test Neutral', 'role': 'neutral'})
        with self.assertRaises(ValidationError):
            self.faction_good.with_env(self.env).allied_faction_id = self.faction_bad
        with self.assertRaises(ValidationError):
            neutral.allied_faction_id = neutral

from odoo.addons.odoo_battle.tests.common import BattleCommon
from odoo.exceptions import ValidationError
from odoo.tests import tagged, users


@tagged('battle_faction')
class TestBattleFactionInternals(BattleCommon):

    @users('battle_admin')
    def test_camp(self):
        """ Camp of a faction: itself, its ally if neutral, and neutral
        factions allied to those """
        good, bad, neutral_good, neutral_bad, neutral_alone = (
            self.faction_good + self.faction_bad + self.faction_neutral_good + self.faction_neutral_bad + self.faction_neutral_alone
        ).with_env(self.env)
        for faction, camp in [
            (good, good + neutral_good),
            (neutral_good, good + neutral_good),
            (bad, bad + neutral_bad),
            (neutral_bad, bad + neutral_bad),
            (neutral_alone, neutral_alone),
        ]:
            with self.subTest(faction=faction.name):
                self.assertEqual(faction._get_camp(), camp)

    @users('battle_admin')
    def test_constraints_ally(self):
        """ Only neutral factions have allies, never themselves """
        with self.assertRaises(ValidationError):
            self.faction_good.with_env(self.env).allied_faction_id = self.faction_bad
        neutral = self.faction_neutral_alone.with_env(self.env)
        with self.assertRaises(ValidationError):
            neutral.allied_faction_id = neutral

    @users('battle_admin')
    def test_camp_role(self):
        """ Neutral factions fight for the camp of their ally """
        for faction, expected in [
            (self.faction_good, 'aggressor'),
            (self.faction_bad, 'defender'),
            (self.faction_neutral_good, 'aggressor'),
            (self.faction_neutral_bad, 'defender'),
            (self.faction_neutral_alone, False),
        ]:
            with self.subTest(faction=faction.name):
                self.assertEqual(faction.with_env(self.env)._get_camp_role(), expected)

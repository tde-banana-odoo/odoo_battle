from odoo.addons.odoo_battle.tests.common import BattleCommon
from odoo.exceptions import ValidationError
from odoo.tests import users


class TestBattleTraitInternals(BattleCommon):

    def test_applies(self):
        """ Traits apply depending on the side, its stance and its result;
        before rolling (no result) only unconditional traits apply """
        fury, counter, leadership, fortified = self.trait_fury, self.trait_counter, self.trait_leadership, self.trait_fortified
        traits = fury + counter + leadership + fortified
        for side, stance, result, expected in [
            ('initiator', 'attack', None, leadership),
            ('initiator', 'defense', None, leadership),
            ('responder', 'attack', None, leadership),
            ('responder', 'defense', None, leadership + fortified),  # fortified: defending responders only
            ('initiator', 'attack', 'win', fury + leadership),
            ('initiator', 'attack', 'lose', leadership),
            ('initiator', 'attack', 'tie', leadership),
            ('responder', 'defense', 'win', counter + leadership + fortified),
            ('responder', 'defense', 'lose', leadership + fortified),
        ]:
            with self.subTest(side=side, stance=stance, result=result):
                self.assertEqual(traits._applies(side, stance, result), expected)

    def test_constraints_bonus_condition(self):
        """ Bonus is applied before rolling: it cannot depend on result """
        with self.assertRaises(ValidationError):
            self.trait_leadership.condition = 'win'

    @users('battle_admin')
    def test_constraints_unit_traits(self):
        """ Units have at most 3 traits, only unit ones """
        unit = self.unit_werewolf_1.with_env(self.env)
        unit.battle_trait_ids = self.trait_fury + self.trait_counter + self.trait_leadership
        with self.assertRaises(ValidationError):
            unit.battle_trait_ids += self.env['battle.trait'].create({'name': 'Test Extra'})
        with self.assertRaises(ValidationError):
            unit.battle_trait_ids = self.trait_ambush

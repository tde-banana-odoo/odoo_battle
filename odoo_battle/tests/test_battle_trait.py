from odoo.addons.odoo_battle.tests.common import BattleCommon
from odoo.exceptions import ValidationError
from odoo.tests import users


class TestBattleTraitInternals(BattleCommon):

    def test_applies(self):
        """ Traits apply depending on the stance and result of their side
        (and on the side itself for location traits); before rolling (no
        result) only unconditional traits apply. Checked for a frontline
        holder (fureur, contre-attaque: frontline only) """
        fury, counter, leadership, fortified = self.trait_fury, self.trait_counter, self.trait_leadership, self.trait_fortified
        traits = fury + counter + leadership + fortified
        for side, stance, result, expected in [
            ('initiator', 'attack', None, leadership),
            ('initiator', 'defense', None, leadership),
            ('responder', 'attack', None, leadership),
            ('responder', 'defense', None, leadership + fortified),  # fortified: defending responders only
            ('initiator', 'attack', 'win', fury + leadership),
            ('responder', 'attack', 'win', fury + leadership),  # fureur: any attacking side
            ('initiator', 'defense', 'win', counter + leadership),  # contre-attaque: any defending side, not fortified
            ('initiator', 'attack', 'lose', leadership),
            ('initiator', 'attack', 'tie', leadership),
            ('responder', 'defense', 'win', counter + leadership + fortified),
            ('responder', 'defense', 'lose', leadership + fortified),
        ]:
            with self.subTest(side=side, stance=stance, result=result):
                self.assertEqual(traits._applies(side, stance, result, 'frontline'), expected)
        # position: support traits only for support holders, frontline ones not in support
        self.assertFalse(fury._applies('initiator', 'attack', 'win', 'support'))
        support = self.trait_support_fire
        self.assertEqual(support._applies('initiator', 'attack', None, 'support'), support)
        self.assertFalse(support._applies('initiator', 'attack', None, 'frontline'))
        with self.assertRaises(ValidationError):
            support.position = 'any'
        with self.assertRaises(ValidationError, msg='Unit traits use stance and position, not side'):
            fury.side = 'initiator'

    def test_constraints_bonus_condition(self):
        """ Bonus is applied before rolling: it cannot depend on result """
        with self.assertRaises(ValidationError):
            self.trait_leadership.condition = 'win'

    @users('battle_admin')
    def test_constraints_unit_traits(self):
        """ Units have unit traits only, as many as wanted """
        unit = self.unit_werewolf_1.with_env(self.env)
        unit.battle_trait_ids = self.trait_fury + self.trait_counter + self.trait_leadership + self.trait_fanatic
        self.assertEqual(len(unit.battle_trait_ids), 4)
        with self.assertRaises(ValidationError):
            unit.battle_trait_ids = self.trait_breakthrough

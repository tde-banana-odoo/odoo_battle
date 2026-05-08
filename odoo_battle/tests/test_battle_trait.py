from odoo.addons.odoo_battle.tests.common import BattleCommon
from odoo.exceptions import ValidationError
from odoo.tests import tagged, users


@tagged('post_install', '-at_install')
class TestBattleTrait(BattleCommon):

    def test_trait_applies(self):
        """ Traits apply depending on the side, its stance and its result;
        before rolling (no result) only unconditional traits apply """
        fury, counter, leadership, fortified = self.trait_fury, self.trait_counter, self.trait_leadership, self.trait_fortified
        traits = fury + counter + leadership + fortified
        self.assertEqual(traits._applies('initiator', 'attack'), leadership)
        self.assertEqual(traits._applies('initiator', 'defense'), leadership)
        self.assertEqual(traits._applies('responder', 'defense'), leadership + fortified)
        self.assertEqual(traits._applies('responder', 'attack'), leadership)
        self.assertEqual(traits._applies('initiator', 'attack', 'win'), fury + leadership)
        self.assertEqual(traits._applies('initiator', 'attack', 'lose'), leadership)
        self.assertEqual(traits._applies('initiator', 'attack', 'tie'), leadership)
        self.assertEqual(traits._applies('responder', 'defense', 'win'), counter + leadership + fortified)
        self.assertEqual(traits._applies('responder', 'defense', 'lose'), leadership + fortified)

    def test_trait_bonus_condition(self):
        """ Bonus is applied before rolling: it cannot depend on result """
        with self.assertRaises(ValidationError):
            self.trait_leadership.condition = 'win'

    @users('battle_admin')
    def test_unit_traits_constraints(self):
        """ Units have at most 3 traits, only unit ones """
        unit = self.unit_werewolf_1.with_env(self.env)
        unit.battle_trait_ids = self.trait_fury + self.trait_counter + self.trait_leadership
        with self.assertRaises(ValidationError):
            unit.battle_trait_ids += self.env['battle.trait'].create({'name': 'Test Extra'})
        with self.assertRaises(ValidationError):
            unit.battle_trait_ids = self.trait_ambush

    @users('battle_admin')
    def test_unit_traits_from_template(self):
        """ Traits are part of the template configuration """
        template = self.template_offense.with_env(self.env)
        template.battle_trait_ids = self.trait_fury
        unit = self.env['battle.unit'].create({'name': 'Test Templated', 'battle_unit_template_id': template.id})
        self.assertEqual(unit.battle_trait_ids, self.trait_fury)

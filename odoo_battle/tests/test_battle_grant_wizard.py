from odoo.addons.odoo_battle.tests.common import BattleCommon
from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, users


class TestBattleGrantWizard(BattleCommon):

    def _grant(self, **values):
        return self.env['battle.grant.wizard'].create(values).action_grant()

    @users('battle_admin')
    def test_grant_unit_trait(self):
        """ Unit traits are added to units (once), logged on them; prefilled
        from selected units """
        wizard = Form(self.env['battle.grant.wizard'].with_context(
            active_model='battle.unit', active_ids=(self.unit_werewolf_1 + self.unit_werewolf_2).ids,
        ))
        self.assertEqual(wizard.grant_type, 'unit')
        self.assertEqual(wizard.battle_unit_ids[:], self.unit_werewolf_1 + self.unit_werewolf_2)
        self.unit_werewolf_2.battle_trait_ids = self.trait_fury
        wizard.battle_trait_id = self.trait_fury
        wizard.note = "Role-play success"
        action = wizard.save().action_grant()
        self.assertEqual(action['params']['message'], "Fureur granted to 1 units.")
        self.assertEqual(self.unit_werewolf_1.battle_trait_ids, self.trait_fury)
        self.assertEqual(self.unit_werewolf_2.battle_trait_ids, self.trait_fury)
        self.assertIn("Granted: Fureur (Role-play success)", self.unit_werewolf_1.message_ids[0].body)

        with self.assertRaises(UserError, msg="Location traits are not for units"):
            self._grant(grant_type='unit', battle_trait_id=self.trait_fortified.id, battle_unit_ids=self.unit_werewolf_1.ids)
        with self.assertRaises(UserError, msg="Units are required"):
            self._grant(grant_type='unit', battle_trait_id=self.trait_fury.id)

    @users('battle_admin')
    def test_grant_location(self):
        """ Location traits for good, or for a faction during a round
        (location effect); prefilled from the selected location """
        wizard = Form(self.env['battle.grant.wizard'].with_context(active_model='battle.location', active_ids=self.location_isca.ids))
        self.assertEqual(wizard.grant_type, 'location_round')
        self.assertEqual(wizard.battle_location_id, self.location_isca)
        self.assertEqual(wizard.round_number, self.battle_round.round_number, 'Current round by default')
        wizard.grant_type = 'location'
        wizard.battle_trait_id = self.trait_fortified
        wizard.save().action_grant()
        self.assertEqual(self.location_isca.battle_trait_ids, self.trait_fortified)

        self._grant(
            grant_type='location_round', battle_trait_id=self.trait_heroic_defense.id, battle_location_id=self.location_londinium.id,
            battle_faction_id=self.faction_bad.id, round_number=self.battle_round.round_number,
        )
        self.assertRecordValues(self.location_londinium.battle_location_effect_ids, [{
            'battle_round_id': self.battle_round.id, 'battle_faction_id': self.faction_bad.id,
            'battle_trait_id': self.trait_heroic_defense.id, 'round_number': self.battle_round.round_number,
        }])
        self.assertIn("Granted: Défense Héroïque, Test Bad, Londinium", self.battle_round.message_ids[0].body)

        # a round to come: kept by number, linked once the round starts
        self._grant(
            grant_type='location_round', battle_trait_id=self.trait_heroic_defense.id, battle_location_id=self.location_isca.id,
            battle_faction_id=self.faction_good.id, round_number=self.battle_round.round_number + 1,
        )
        effect = self.location_isca.battle_location_effect_ids
        self.assertFalse(effect.battle_round_id)
        next_round = self.env['battle.round'].sudo().create({})
        self.assertEqual(effect.battle_round_id, next_round)

    @users('battle_admin')
    def test_grant_command_action(self):
        """ An extra command action for the faction camp (allies included):
        the camp command actions count is raised; its rule is shown """
        wizard = Form(self.env['battle.grant.wizard'])
        wizard.grant_type = 'command'
        wizard.command_type = 'location_support'
        self.assertEqual(wizard.command_rule, "+1 au bonus par action (+2 max par camp)")

        self._grant(
            grant_type='command', command_type='location_support', battle_location_id=self.location_isca.id,
            battle_faction_id=self.faction_neutral_bad.id, round_number=self.battle_round.round_number, note="Allies",
        )
        self.assertEqual(self.battle_round.defender_command_action_count, 1)
        self.assertRecordValues(self.battle_round.defender_command_action_ids, [{
            'camp': 'defender', 'command_type': 'location_support', 'battle_location_id': self.location_isca.id, 'note': "Allies",
        }])
        self.assertFalse(self.battle_round.aggressor_command_action_ids)

        with self.assertRaises(UserError, msg="Unallied factions have no camp"):
            self._grant(
                grant_type='command', command_type='hold_on', battle_location_id=self.location_isca.id,
                battle_faction_id=self.faction_neutral_alone.id, round_number=self.battle_round.round_number,
            )
        with self.assertRaises(UserError, msg="Command actions need an existing round"):
            self._grant(
                grant_type='command', command_type='hold_on', battle_location_id=self.location_isca.id,
                battle_faction_id=self.faction_good.id, round_number=self.battle_round.round_number + 1,
            )

    @users('battle_user')
    def test_grant_access(self):
        """ Only admins grant bonuses """
        with self.assertRaises(AccessError):
            self.env['battle.grant.wizard'].create({'grant_type': 'unit'})

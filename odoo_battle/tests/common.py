from odoo.tests import common, new_test_user


class BattleCommon(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_admin = new_test_user(cls.env, login='battle_admin', groups='base.group_user,base.group_system')
        cls.user_regular = new_test_user(cls.env, login='battle_user', groups='base.group_user,base.group_user_regular')

        cls.location_isca, cls.location_londinium = cls.env['battle.location'].create([
            {'name': 'Isca Augusta'},
            {'name': 'Londinium'},
        ])
        # good ones are aggressors, bad ones defend their places
        cls.faction_good, cls.faction_bad = cls.env['battle.faction'].create([
            {'name': 'Test Good', 'sequence': 1, 'morale': 6, 'role': 'aggressor'},
            {'name': 'Test Bad', 'sequence': 2, 'morale': 4, 'role': 'defender'},
        ])
        traits = cls.env['battle.trait'].create([
            {'name': 'Test Fury', 'stance': 'attack', 'condition': 'win', 'effect': 'damage'},
            {'name': 'Test Counter', 'stance': 'defense', 'condition': 'win', 'effect': 'damage'},
            {'name': 'Test Leadership', 'effect': 'bonus', 'is_unique': True},
            {'name': 'Test Ambush', 'target': 'location', 'stance': 'defense', 'effect': 'bonus'},
            {'name': 'Test Fortified', 'target': 'location', 'side': 'responder', 'stance': 'defense', 'effect': 'bonus'},
        ])
        cls.trait_fury, cls.trait_counter, cls.trait_leadership, cls.trait_ambush, cls.trait_fortified = traits
        cls.template_offense, cls.template_henchmen = cls.env['battle.unit.template'].create([
            {
                'name': 'Test Offense Werewolves', 'unit_type': 'werewolf',
                'menace': 3, 'size': 1, 'rage': 3, 'willpower': 1, 'gnosis': 0, 'damage': 2, 'resistance': 1,
            }, {
                'name': 'Test Henchmen', 'unit_type': 'human',
                'menace': 1, 'size': 2, 'rage': -1, 'willpower': -1, 'gnosis': -2, 'damage': 1, 'resistance': 0,
            },
        ])
        # Isca: two good werewolves vs a bad vampire; Londinium: a bad vampire
        cls.unit_werewolf_1, cls.unit_werewolf_2, cls.unit_vampire_1, cls.unit_vampire_2 = cls.env['battle.unit'].create([
            {
                'name': 'Test Werewolf 1', 'unit_type': 'werewolf',
                'battle_faction_id': cls.faction_good.id, 'battle_location_id': cls.location_isca.id,
                'menace': 3, 'size': 2, 'rage': 4, 'willpower': 5, 'gnosis': 3, 'damage': 2, 'resistance': 12,
            }, {
                'name': 'Test Werewolf 2', 'unit_type': 'werewolf',
                'battle_faction_id': cls.faction_good.id, 'battle_location_id': cls.location_isca.id,
                'menace': 2, 'size': 3, 'rage': 3, 'willpower': 4, 'gnosis': 4, 'damage': 2, 'resistance': 8,
            }, {
                'name': 'Test Vampire 1', 'unit_type': 'vampire',
                'battle_faction_id': cls.faction_bad.id, 'battle_location_id': cls.location_isca.id,
                'menace': 4, 'size': 2, 'rage': 1, 'willpower': 6, 'gnosis': 0, 'damage': 3, 'resistance': 10,
            }, {
                'name': 'Test Vampire 2', 'unit_type': 'vampire',
                'battle_faction_id': cls.faction_bad.id, 'battle_location_id': cls.location_londinium.id,
                'menace': 5, 'size': 3, 'rage': 2, 'willpower': 7, 'gnosis': 0, 'damage': 4, 'resistance': 14,
            },
        ])

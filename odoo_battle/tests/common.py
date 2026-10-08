from unittest.mock import patch

from odoo.addons.odoo_battle.wizard.battle_solver import BattleSolver
from odoo.fields import Command
from odoo.tests import Form, common, new_test_user


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
        # current round, holding camps leadership
        cls.battle_round = cls.env['battle.round'].create({'aggressor_morale': '4', 'defender_morale': '3'})
        # good ones are aggressors, bad ones defend their places
        cls.faction_good, cls.faction_bad = cls.env['battle.faction'].create([
            {'name': 'Test Good', 'sequence': 1, 'role': 'aggressor'},
            {'name': 'Test Bad', 'sequence': 2, 'role': 'defender'},
        ])
        # neutral factions, fighting along their ally; or alone (no camp, hardly supported)
        cls.faction_neutral_good, cls.faction_neutral_bad, cls.faction_neutral_alone = cls.env['battle.faction'].create([
            {'name': 'Test Neutral Good', 'sequence': 3, 'role': 'neutral', 'allied_faction_id': cls.faction_good.id},
            {'name': 'Test Neutral Bad', 'sequence': 4, 'role': 'neutral', 'allied_faction_id': cls.faction_bad.id},
            {'name': 'Test Neutral Alone', 'sequence': 5, 'role': 'neutral'},
        ])
        # data traits, to test actual game rules
        cls.trait_ambush = cls.env.ref('odoo_battle.battle_trait_ambush')
        cls.trait_assassin = cls.env.ref('odoo_battle.battle_trait_assassin')
        cls.trait_barrage_fire = cls.env.ref('odoo_battle.battle_trait_barrage_fire')
        cls.trait_breakthrough = cls.env.ref('odoo_battle.battle_trait_breakthrough')
        cls.trait_counter = cls.env.ref('odoo_battle.battle_trait_counter_attack')
        cls.trait_diversion = cls.env.ref('odoo_battle.battle_trait_diversion')
        cls.trait_fortified = cls.env.ref('odoo_battle.battle_trait_fortified')
        cls.trait_fury = cls.env.ref('odoo_battle.battle_trait_fury')
        cls.trait_heroic_defense = cls.env.ref('odoo_battle.battle_trait_heroic_defense')
        cls.trait_leadership = cls.env.ref('odoo_battle.battle_trait_leadership')
        cls.trait_scout = cls.env.ref('odoo_battle.battle_trait_scout')
        cls.trait_support_fire = cls.env.ref('odoo_battle.battle_trait_support_fire')
        cls.trait_tactics = cls.env.ref('odoo_battle.battle_trait_tactics')
        cls.trait_wavering = cls.env.ref('odoo_battle.battle_trait_wavering_morale')
        cls.trait_fanatic = cls.env.ref('odoo_battle.battle_trait_fanatic')
        # templates: menace, size / rage, willpower, gnosis / damage, resistance // traits
        cls.template_offense, cls.template_defense, cls.template_old_vampire, cls.template_ghoul, cls.template_military, cls.template_henchmen = cls.env['battle.unit.template'].create([
            {
                'name': 'Test Offense Werewolves', 'unit_type': 'werewolf',
                'menace': 3, 'size': 1, 'rage': 3, 'willpower': 1, 'gnosis': 1, 'damage': 3, 'resistance': 2,
                'battle_trait_ids': (cls.trait_assassin + cls.trait_fury).ids,
            }, {
                'name': 'Test Defense Werewolves', 'unit_type': 'werewolf',
                'menace': 3, 'size': 1, 'rage': 2, 'willpower': 1, 'gnosis': 2, 'damage': 3, 'resistance': 2,
                'battle_trait_ids': (cls.trait_tactics + cls.trait_counter).ids,
            }, {
                'name': 'Test Old Vampires', 'unit_type': 'vampire',
                'menace': 3, 'size': 1, 'rage': 2, 'willpower': 3, 'gnosis': 2, 'damage': 2, 'resistance': 3,
                'battle_trait_ids': (cls.trait_leadership + cls.trait_assassin).ids,
            }, {
                'name': 'Test Ghouls', 'unit_type': 'ghoul',
                'menace': 1, 'size': 1, 'rage': 0, 'willpower': 0, 'gnosis': -1, 'damage': 1, 'resistance': 1,
                'battle_trait_ids': cls.trait_fanatic.ids,
            }, {
                'name': 'Test Military', 'unit_type': 'human',
                'menace': 1, 'size': 2, 'rage': 0, 'willpower': -1, 'gnosis': -2, 'damage': 2, 'resistance': 1,
                'battle_trait_ids': (cls.trait_support_fire + cls.trait_counter).ids,
            }, {
                'name': 'Test Henchmen', 'unit_type': 'human',
                'menace': 1, 'size': 2, 'rage': -1, 'willpower': -1, 'gnosis': -2, 'damage': 1, 'resistance': 0,
                'battle_trait_ids': cls.trait_support_fire.ids,
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

    @classmethod
    def _create_units(cls, location, faction, template, count, name):
        """ Create ``count`` units from ``template``, already damaged (1) """
        return cls.env['battle.unit'].create([{
            'name': f'{name} {index}', 'battle_unit_template_id': template.id,
            'battle_faction_id': faction.id, 'battle_location_id': location.id, 'damage_counter': 1,
        } for index in range(1, count + 1)])

    def _new_solver_form(self, location):
        """ Open solver like the 'Battle' button of location form view """
        return Form(self.env['battle.solver'].with_context(active_model='battle.location', active_id=location.id))

    def _battle(self, location, roll=(0, 0, 0)):
        """ Solve a battle in ``location`` with a given dice ``roll``, and
        apply its results """
        solver = self._new_solver_form(location).save()
        with patch.object(BattleSolver, '_roll_dice', return_value=list(roll)):
            solver.action_launch()
        solver.action_apply()
        return solver

    def _get_units(self, solver, side):
        """ Units of a solver side """
        return solver[f'{side}_line_ids'].battle_unit_id

    def _get_units_in_battle(self, solver, side):
        """ Units of a solver side taking part in the battle """
        return solver._get_lines(side).battle_unit_id

    def _set_lines(self, solver, side, frontline=None, support=None):
        """ Replace units of a solver side, in frontline or support """
        solver[f'{side}_line_ids'] = [Command.clear()] + [
            Command.create({'side': side, 'battle_unit_id': unit.id, 'position': position})
            for position, units in (('frontline', frontline), ('support', support)) for unit in (units or [])
        ]

    def _get_bonus(self, solver):
        """ Bonus as (initiators, responders, difference); changes on regular
        models do not invalidate transient ones, as a new request would """
        solver.invalidate_recordset()
        return solver.initiator_bonus, solver.responder_bonus, solver.bonus


class BattleSolverCommon(BattleCommon):
    """ Battlefield with typical battles; all units are already damaged (1),
    two more damage points give a wound """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.location_ww, cls.location_vw, cls.location_hw = cls.env['battle.location'].create([
            {'name': 'Werewolves War'},
            {'name': 'Vampires vs Werewolves', 'status': 'held', 'held_by_faction_id': cls.faction_good.id},
            {'name': 'Human Wars'},
        ])
        # Werewolves War: 3 offense werewolves vs 2 defense werewolves + 2 henchmen
        cls.ww_offense = cls._create_units(cls.location_ww, cls.faction_good, cls.template_offense, 3, 'WW Offense')
        cls.ww_defense = cls._create_units(cls.location_ww, cls.faction_bad, cls.template_defense, 2, 'WW Defense')
        cls.ww_henchmen = cls._create_units(cls.location_ww, cls.faction_bad, cls.template_henchmen, 2, 'WW Henchmen')
        # Vampires vs Werewolves: 2 old vampires + 2 ghouls assault 2 offense werewolves holding the place
        cls.vw_vampires = cls._create_units(cls.location_vw, cls.faction_bad, cls.template_old_vampire, 2, 'VW Vampire')
        cls.vw_ghouls = cls._create_units(cls.location_vw, cls.faction_bad, cls.template_ghoul, 2, 'VW Ghoul')
        cls.vw_werewolves = cls._create_units(cls.location_vw, cls.faction_good, cls.template_offense, 2, 'VW Werewolf')
        # Human Wars: 2 military vs 4 henchmen
        cls.hw_military = cls._create_units(cls.location_hw, cls.faction_good, cls.template_military, 2, 'HW Military')
        cls.hw_henchmen = cls._create_units(cls.location_hw, cls.faction_bad, cls.template_henchmen, 4, 'HW Henchmen')

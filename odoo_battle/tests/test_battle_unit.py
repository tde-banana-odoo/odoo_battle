from odoo.addons.odoo_battle.tests.common import BattleCommon
from odoo.exceptions import AccessError
from odoo.tests import Form, users
from odoo.tools import BinaryBytes
from odoo.tools.misc import file_open

OFFENSE_STATS = {
    'unit_type': 'werewolf', 'menace': 3, 'size': 1,
    'rage': 3, 'willpower': 1, 'gnosis': 0, 'damage': 2, 'resistance': 1,
}
HENCHMEN_STATS = {
    'unit_type': 'human', 'menace': 1, 'size': 2,
    'rage': -1, 'willpower': -1, 'gnosis': -2, 'damage': 1, 'resistance': 0,
}


class TestBattleUnit(BattleCommon):

    @users('battle_admin')
    def test_dead_or_out_of_combat(self):
        """ Dead or out of combat units do not fight anymore """
        unit = self.unit_vampire_1.with_env(self.env)
        for vals in [{'is_dead': True}, {'wound_state': '0'}]:
            with self.subTest(vals=vals):
                unit.write({'is_dead': False, 'wound_state': '4', **vals})
                # Isca: only good units left, no battle anymore
                self.assertEqual(self.location_isca.with_env(self.env)._get_battle_sides(), (self.faction_good, self.env['battle.faction']))
                self.assertFalse(self._new_solver_form(self.location_isca).responder_unit_ids)
        self.assertEqual(self.faction_bad.with_env(self.env).battle_unit_count, 2, 'Out of combat units are still alive')

    @users('battle_admin')
    def test_form(self):
        """ Unit form view is usable: choosing a template fills the unit.
        Statistics are edited through a JS widget, hence not in Form. """
        unit_form = Form(self.env['battle.unit'])
        unit_form.name = 'Test Werewolf 3'
        unit_form.battle_unit_template_id = self.template_offense
        self.assertEqual(unit_form.unit_type, 'werewolf')
        self.assertRecordValues(unit_form.save(), [OFFENSE_STATS])

    @users('battle_admin')
    def test_template(self):
        """ Templates pre-configure units (statistics, traits) field by field.
        Tweaked values are kept when template values change, and reset when
        changing template """
        template_offense, template_henchmen = (self.template_offense + self.template_henchmen).with_env(self.env)
        template_offense.battle_trait_ids = self.trait_fury
        unit, unit_tweaked = self.env['battle.unit'].create([
            {'name': 'Test Templated', 'battle_unit_template_id': template_offense.id},
            {'name': 'Test Tweaked', 'battle_unit_template_id': template_offense.id, 'menace': 5},
        ])
        self.assertRecordValues(unit + unit_tweaked, [
            {**OFFENSE_STATS, 'battle_trait_ids': self.trait_fury.ids},
            {**OFFENSE_STATS, 'menace': 5, 'battle_trait_ids': self.trait_fury.ids},  # explicit values take precedence
        ])

        # rewriting same template (e.g. data update) keeps tweaks
        unit.rage = 4
        unit.write({'battle_unit_template_id': template_offense.id})
        self.assertEqual(unit.rage, 4)

        # changing template resets values, removing it keeps them
        unit.battle_unit_template_id = template_henchmen
        self.assertRecordValues(unit, [{**HENCHMEN_STATS, 'battle_trait_ids': []}])
        unit.battle_unit_template_id = False
        self.assertRecordValues(unit, [HENCHMEN_STATS])

        # updating template: units follow, unless tweaked
        unit.battle_unit_template_id = template_offense
        template_offense.write({'menace': 4, 'size': 2})
        self.assertRecordValues(unit + unit_tweaked, [{'menace': 4, 'size': 2}, {'menace': 5, 'size': 2}])


class TestBattleUnitAccess(BattleCommon):

    @users('battle_user')
    def test_access_regular_user(self):
        """ Regular users can display units but not modify them """
        Form(self.unit_werewolf_1.with_env(self.env))
        with self.assertRaises(AccessError):
            self.unit_werewolf_1.with_env(self.env).write({'menace': 10})
        with self.assertRaises(AccessError):
            self.env['battle.unit'].create({'name': 'Intruder', 'unit_type': 'werewolf'})


class TestBattleUnitInternals(BattleCommon):

    def _get_glyph(self, unit_type):
        with file_open(f'odoo_battle/static/img/unit_type/{unit_type}.svg', 'rb') as glyph:
            return glyph.read()

    def test_display_name(self):
        """ Dead units are flagged in their name """
        self.unit_vampire_1.is_dead = True
        self.assertEqual(self.unit_vampire_1.display_name, 'Test Vampire 1 †')
        self.assertEqual(self.unit_vampire_2.display_name, 'Test Vampire 2')

    def test_image(self):
        """ Image defaults to the unit type glyph, available for each type;
        template image is given to units """
        for unit_type, _label in self.env['battle.unit']._fields['unit_type'].selection:
            with self.subTest(unit_type=unit_type):
                self.unit_werewolf_1.unit_type = unit_type
                self.assertEqual(self.unit_werewolf_1.image_1920.content, self._get_glyph(unit_type))

        self.assertEqual(self.template_offense.image_1920.content, self._get_glyph('werewolf'))
        self.template_offense.image_1920 = BinaryBytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>', filename='test.svg')
        self.unit_werewolf_1.battle_unit_template_id = self.template_offense
        self.assertEqual(self.unit_werewolf_1.image_1920.content, self.template_offense.image_1920.content)

    def test_load(self):
        """ Loading data (e.g. csv): filled cells (including 0) are set, empty
        ones are skipped: template or default values for new units, current
        values (e.g. updated during the game) for existing ones """
        fields = ['id', 'name', 'battle_unit_template_id/.id', 'unit_type', 'menace', 'rage', 'willpower', 'wound_state']
        row = ['test_unit_loaded', 'Test Loaded', str(self.template_offense.id), '', '', '4', '0', '']
        unit = self.env['battle.unit'].browse(self.env['battle.unit'].load(fields, [row])['ids'])
        self.assertRecordValues(unit, [{**OFFENSE_STATS, 'rage': 4, 'willpower': 0, 'wound_state': '4'}])

        unit.write({'wound_state': '3', 'menace': 5})
        self.env['battle.unit'].load(fields, [row])
        self.assertRecordValues(unit, [{'wound_state': '3', 'menace': 5}])

    @users('battle_user')
    def test_order(self):
        """ Units are ordered by faction sequence, then unit type, then
        creation; reordering factions reorders units """
        faction_first = self.env['battle.faction'].sudo().create({'name': 'Test First', 'sequence': 0})
        unit_vampire, unit_werewolf = self.env['battle.unit'].sudo().create([
            {'name': 'Test First Vampire', 'unit_type': 'vampire', 'battle_faction_id': faction_first.id},
            {'name': 'Test First Werewolf', 'unit_type': 'werewolf', 'battle_faction_id': faction_first.id},
        ])
        domain = [('battle_faction_id', 'in', (faction_first + self.faction_good + self.faction_bad).ids)]
        self.assertEqual(
            self.env['battle.unit'].search(domain).ids,
            (unit_werewolf + unit_vampire + self.unit_werewolf_1 + self.unit_werewolf_2 + self.unit_vampire_1 + self.unit_vampire_2).ids,
        )
        faction_first.sudo().sequence = 10
        self.assertEqual(self.env['battle.unit'].search(domain)[-2:].ids, (unit_werewolf + unit_vampire).ids)

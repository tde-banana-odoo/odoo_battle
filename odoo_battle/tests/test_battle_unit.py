from odoo.addons.odoo_battle.tests.common import BattleCommon
from odoo.exceptions import AccessError
from odoo.tests import Form, tagged, users
from odoo.tools import BinaryBytes
from odoo.tools.misc import file_open


@tagged('post_install', '-at_install')
class TestBattleUnit(BattleCommon):

    def _get_stats(self, unit):
        return [unit.unit_type, unit.menace, unit.size, unit.rage, unit.willpower, unit.gnosis, unit.damage, unit.resistance]

    @users('battle_admin')
    def test_unit_form(self):
        """ Unit form view is usable: choosing a template fills the unit.
        Statistics are edited through a JS widget, hence not in Form. """
        unit_form = Form(self.env['battle.unit'])
        unit_form.name = 'Test Werewolf 3'
        unit_form.battle_unit_template_id = self.template_offense
        self.assertEqual(unit_form.unit_type, 'werewolf')
        unit = unit_form.save()
        self.assertEqual(self._get_stats(unit), ['werewolf', 3, 1, 3, 1, 0, 2, 1])

    @users('battle_user')
    def test_unit_access(self):
        """ Regular users can display units but not modify them """
        Form(self.unit_werewolf_1.with_env(self.env))
        with self.assertRaises(AccessError):
            self.unit_werewolf_1.with_env(self.env).write({'menace': 10})
        with self.assertRaises(AccessError):
            self.env['battle.unit'].create({'name': 'Intruder', 'unit_type': 'werewolf'})

    @users('battle_user')
    def test_unit_order(self):
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

    @users('battle_admin')
    def test_unit_template(self):
        """ Templates pre-configure units field by field; tweaked values are
        kept unless the template changes """
        template_offense, template_henchmen = (self.template_offense + self.template_henchmen).with_env(self.env)
        unit, unit_tweaked = self.env['battle.unit'].create([
            {'name': 'Test Templated', 'battle_unit_template_id': template_offense.id},
            {'name': 'Test Tweaked', 'battle_unit_template_id': template_offense.id, 'menace': 5},
        ])
        self.assertEqual(self._get_stats(unit), ['werewolf', 3, 1, 3, 1, 0, 2, 1])
        self.assertEqual(self._get_stats(unit_tweaked), ['werewolf', 5, 1, 3, 1, 0, 2, 1],
                         'Explicit values take precedence over template')

        # rewriting same template (e.g. data update) keeps tweaks
        unit.rage = 4
        unit.write({'battle_unit_template_id': template_offense.id})
        self.assertEqual(unit.rage, 4)

        # changing template resets values, removing it keeps them
        unit.battle_unit_template_id = template_henchmen
        self.assertEqual(self._get_stats(unit), ['human', 1, 2, -1, -1, -2, 1, 0])
        unit.battle_unit_template_id = False
        self.assertEqual(self._get_stats(unit), ['human', 1, 2, -1, -1, -2, 1, 0])

        # updating template does not override units, as they may be tweaked
        template_offense.menace = 4
        self.assertEqual(unit_tweaked.menace, 5)

    def test_unit_load_template_override(self):
        """ Loading data (e.g. csv): empty cells keep template values, filled
        ones (including 0) override them """
        result = self.env['battle.unit'].load(
            ['name', 'battle_unit_template_id/.id', 'unit_type', 'menace', 'rage', 'willpower'],
            [['Test Loaded', str(self.template_offense.id), '', '', '4', '0']],
        )
        unit = self.env['battle.unit'].browse(result['ids'])
        self.assertEqual(self._get_stats(unit), ['werewolf', 3, 1, 4, 0, 0, 2, 1])

    @users('battle_admin')
    def test_unit_image(self):
        """ Image defaults to the unit type glyph; template image is given
        to units """
        def glyph(unit_type):
            with file_open(f'odoo_battle/static/img/unit_type/{unit_type}.svg', 'rb') as glyph_file:
                return glyph_file.read()

        unit = self.unit_werewolf_1.with_env(self.env)
        self.assertEqual(unit.image_1920.content, glyph('werewolf'))
        unit.unit_type = 'possessed'
        self.assertEqual(unit.image_1920.content, glyph('possessed'))

        template = self.template_offense.with_env(self.env)
        self.assertEqual(template.image_1920.content, glyph('werewolf'))
        template.image_1920 = BinaryBytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>', filename='test.svg')
        unit.battle_unit_template_id = template
        self.assertEqual(unit.image_1920.content, template.image_1920.content)

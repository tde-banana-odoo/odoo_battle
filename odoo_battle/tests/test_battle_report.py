from odoo.addons.odoo_battle.tests.common import BattleCommon
from odoo.tests import users


class TestBattleReport(BattleCommon):

    @users('battle_user')
    def test_unit_sheet(self):
        """ Unit sheets display statistics, checked wounds, combat traits
        (with effect) and lore traits apart; 10 sheets per page """
        lore = self.env['battle.trait'].sudo().create({'name': 'Test Lore'})
        self.unit_werewolf_1.sudo().write({
            'wound_state': '2',
            'battle_trait_ids': (self.trait_fury + lore).ids,
        })
        Report = self.env['report.odoo_battle.report_unit_sheet']
        sheet = Report._get_report_values(self.unit_werewolf_1.ids)['pages'][0][0]
        self.assertEqual(
            {key: sheet[key] for key in ('name', 'faction', 'menace', 'size', 'rage', 'gnosis', 'willpower', 'damage', 'resistance', 'wounds')},
            {'name': 'Test Werewolf 1', 'faction': 'Test Good', 'menace': 3, 'size': 2, 'rage': 4, 'gnosis': 3,
             'willpower': 5, 'damage': 2, 'resistance': 12, 'wounds': 2},
        )
        self.assertEqual((sheet['battle_traits'], sheet['lore_traits']), (['Test Fury'], ['Test Lore']))
        self.assertTrue(sheet['image'].startswith('data:image/svg+xml;base64,'))

        units = self.env['battle.unit'].sudo().create([{'name': f'Test Unit {index}', 'unit_type': 'human'} for index in range(21)])
        self.assertEqual([len(page) for page in Report._get_report_values(units.ids)['pages']], [10, 10, 1])

        html = self.env['ir.actions.report']._render_qweb_html('odoo_battle.action_report_unit_sheet', self.unit_werewolf_1.ids)[0]
        self.assertIn(b'Test Werewolf 1', html)

    @users('battle_user')
    def test_unit_sheet_blank(self):
        """ Blank sheets: pre-filled from templates (name to fill in), or
        fully blank """
        wizard = self.env['battle.unit.sheet.wizard'].create({
            'battle_unit_template_ids': self.template_offense.ids,
            'copies': 3,
            'blank_copies': 2,
        })
        data = wizard.action_print()['data']
        sheets = self.env['report.odoo_battle.report_unit_sheet']._get_report_values([], data)['pages'][0]
        self.assertEqual(len(sheets), 5)
        self.assertEqual(
            [(sheet['name'], sheet['template'], sheet['menace']) for sheet in sheets],
            [('', 'Test Offense Werewolves', 3)] * 3 + [('', '', None)] * 2,
        )

import base64

from odoo.addons.odoo_battle.tests.common import BattleCommon
from odoo.tests import users


class TestBattleReport(BattleCommon):

    @users('battle_user')
    def test_unit_sheet(self):
        """ Unit sheets display statistics, combat traits (with effect) and
        lore traits apart, and a black and white glyph (wounds are left blank,
        updated by hand); 10 sheets per page """
        lore = self.env['battle.trait'].sudo().create({'name': 'Test Lore'})
        self.unit_werewolf_1.sudo().write({
            'wound_state': '2',
            'battle_trait_ids': (self.trait_fury + lore).ids,
        })
        Report = self.env['report.odoo_battle.report_unit_sheet']
        sheet = Report._get_report_values(self.unit_werewolf_1.ids)['pages'][0][0]
        self.assertEqual(
            {key: sheet[key] for key in ('name', 'faction', 'menace', 'size', 'rage', 'gnosis', 'willpower', 'damage', 'resistance')},
            {'name': 'Test Werewolf 1', 'faction': 'Test Good', 'menace': 3, 'size': 2, 'rage': 4, 'gnosis': 3,
             'willpower': 5, 'damage': 2, 'resistance': 12},
        )
        self.assertEqual((sheet['battle_traits'], sheet['lore_traits']), (['Fureur\u00a0(A)'], ['Test Lore']), 'Attack trait: (A) suffix')
        self.assertFalse(sheet['traits_merged'], 'Short combat traits: own line, lore on the next one')
        self.assertTrue(sheet['image'].startswith('data:image/svg+xml;base64,'))
        glyph = base64.b64decode(sheet['image'].split(',', 1)[1])
        self.assertNotIn(b'<rect width="180" height="180"', glyph, 'no colored background when printed')
        self.assertNotIn(b'#f3ead8', glyph, 'dark drawing when printed')

        units = self.env['battle.unit'].sudo().create([{'name': f'Test Unit {index}', 'unit_type': 'human'} for index in range(21)])
        self.assertEqual([len(page) for page in Report._get_report_values(units.ids)['pages']], [10, 10, 1])

        html = self.env['ir.actions.report']._render_qweb_html('odoo_battle.action_report_unit_sheet', self.unit_werewolf_1.ids)[0]
        self.assertIn(b'Test Werewolf 1', html)

        # long combat traits wrap over the lore line
        self.unit_werewolf_1.sudo().battle_trait_ids += self.trait_leadership + self.trait_counter
        sheet_long = Report._get_report_values(self.unit_werewolf_1.ids)['pages'][0][0]
        self.assertEqual((sheet_long['traits_merged'], sheet_long['traits_small']), (True, False))
        self.assertIn('Contre\u2011Attaque\u00a0(D)', sheet_long['battle_traits'], 'Non-breaking hyphen and space, never split')
        # even longer: smaller font, 3 lines
        self.unit_werewolf_1.sudo().battle_trait_ids += self.trait_assassin + self.trait_tactics + self.trait_diversion + self.trait_support_fire
        self.assertTrue(Report._get_report_values(self.unit_werewolf_1.ids)['pages'][0][0]['traits_small'])

        # template short name below the glyph, e.g. 'LG 3'
        self.template_offense.sudo().short_name = 'LG 3'
        pack = self.env['battle.unit'].sudo().create({'name': 'Test Pack', 'battle_unit_template_id': self.template_offense.id})
        self.assertEqual(Report._get_report_values(pack.ids)['pages'][0][0]['short_name'], 'LG 3')
        self.assertEqual(sheet['short_name'], '', 'No template, no short name')

    @users('battle_user')
    def test_unit_sheet_blank(self):
        """ Blank sheets: pre-filled from templates (name to fill in), or
        fully blank """
        self.template_offense.sudo().short_name = 'LG 3'
        wizard = self.env['battle.unit.sheet.wizard'].create({
            'battle_unit_template_ids': self.template_offense.ids,
            'copies': 3,
            'blank_copies': 2,
        })
        data = wizard.action_print()['data']
        sheets = self.env['report.odoo_battle.report_unit_sheet']._get_report_values([], data)['pages'][0]
        self.assertEqual(len(sheets), 5)
        self.assertEqual(
            [(sheet['name'], sheet['template'], sheet['short_name'], sheet['menace']) for sheet in sheets],
            [('', 'Test Offense Werewolves', 'LG 3', 3)] * 3 + [('', '', '', None)] * 2,
        )

    @users('battle_user')
    def test_location_sheet(self):
        """ Location sheets display Umbra, twin location, traits with their
        rules; status and holder are left blank (filled in by hand during
        play); 10 sheets per page """
        self.location_isca.sudo().write({
            'status': 'held',
            'held_by_faction_id': self.faction_bad.id,
            'is_umbra': True,
            'linked_location_id': self.location_londinium.id,
            'battle_trait_ids': self.trait_fortified.ids,
        })
        Report = self.env['report.odoo_battle.report_location_sheet']
        sheet = Report._get_report_values(self.location_isca.ids)['pages'][0][0]
        self.assertEqual(sheet, {
            'name': 'Isca Augusta',
            'is_umbra': True,
            'linked': 'Londinium',
            'traits': [(self.trait_fortified.name, self.trait_fortified.description)],
        })

        locations = self.env['battle.location'].sudo().create([{'name': f'Test Location {index}'} for index in range(11)])
        self.assertEqual([len(page) for page in Report._get_report_values(locations.ids)['pages']], [10, 1])

        html = self.env['ir.actions.report']._render_qweb_html('odoo_battle.action_report_location_sheet', self.location_isca.ids)[0]
        for expected in (b'Isca Augusta', b'UMBRA', b'Londinium', self.trait_fortified.name.encode(), 'Percée'.encode()):
            self.assertIn(expected, html)
        self.assertNotIn(b'Test Bad', html, 'Holder filled in by hand')
        self.assertNotIn(b'o_bs_box_checked"', html, 'Status checked by hand')  # class of a box (also in styles)

        html = self.env['ir.actions.report']._render_qweb_html('odoo_battle.action_report_location_sheet', locations[0].ids)[0]
        self.assertNotIn('Lié à'.encode(), html, 'No twin location')

    @users('battle_user')
    def test_rules_reference(self):
        """ Game aid: rules, outcomes, command actions (effects from the rules
        constants), unit traits with their stance, location traits """
        values = self.env['report.odoo_battle.report_rules_reference']._get_report_values([])
        commands = dict(values['commands'])
        self.assertEqual(commands['Soutien de Zone'], '+1 au bonus par action (+2 max par camp)')
        self.assertEqual(commands['Retraite'], 'dégâts ×0 %, résistance ×200 % ; les unités quittent ensuite la zone')
        self.assertEqual([outcome['score'] for outcome in values['outcomes']], list(range(-4, 5)))
        groups = dict(values['unit_traits'])
        self.assertIn(self.trait_fury, groups['Dégâts'], 'Traits grouped by sequence, as in data')
        self.assertIn(self.trait_leadership, groups['Tactique'])
        html = self.env['ir.actions.report']._render_qweb_html('odoo_battle.action_report_rules_reference', [])[0]
        for expected in (self.trait_fury.name, self.trait_fortified.name, 'Victoire écrasante'):
            self.assertIn(expected.encode(), html)

    @users('battle_user')
    def test_traits_reference(self):
        """ Traits reference, for players: all traits, without other rules """
        html = self.env['ir.actions.report']._render_qweb_html('odoo_battle.action_report_traits_reference', [])[0]
        for expected in (self.trait_fury.name, self.trait_fortified.name):
            self.assertIn(expected.encode(), html)
        for hidden in ('Victoire écrasante', 'Actions de commandement'):
            self.assertNotIn(hidden.encode(), html)


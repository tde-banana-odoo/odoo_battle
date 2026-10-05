from odoo.addons.odoo_battle.tests.common import BattleCommon
from odoo.tests import users


class TestBattleLeader(BattleCommon):

    @users('battle_admin')
    def test_faction_leader(self):
        """ Leaders leading a faction are flagged (and searchable) """
        leader, other = self.env['battle.leader'].create([
            {'name': 'Test Leader', 'battle_faction_id': self.faction_good.id},
            {'name': 'Test Other', 'battle_faction_id': self.faction_good.id},
        ])
        self.assertFalse(leader.is_faction_leader)
        self.faction_good.with_env(self.env).leader_id = leader
        self.assertEqual((leader + other).mapped('is_faction_leader'), [True, False])
        self.assertEqual(self.env['battle.leader'].search([('is_faction_leader', '=', True), ('id', 'in', (leader + other).ids)]), leader)

        self.faction_good.with_env(self.env).leader_id = other
        self.assertEqual((leader + other).mapped('is_faction_leader'), [False, True])

    @users('battle_admin')
    def test_image(self):
        """ Leaders image is their type glyph, in a gold ringed circle
        instead of the square of units """
        leader = self.env['battle.leader'].create({'name': 'Test Leader', 'unit_type': 'werewolf'})
        glyph = leader.image_1920.content
        self.assertIn(b'<circle cx="90" cy="90" r="84" fill="#7a4b1f" stroke="#c9a227"', glyph)
        self.assertNotIn(b'<rect width="180" height="180"', glyph)
        self.assertNotEqual(glyph, self.unit_werewolf_1.image_1920.content)

        leader.unit_type = False
        self.assertFalse(leader.image_1920)

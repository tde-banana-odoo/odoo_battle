from odoo.addons.odoo_battle.tests.common import BattleCommon
from odoo.exceptions import ValidationError
from odoo.tests import Form, tagged, users


@tagged('post_install', '-at_install')
class TestBattleLocation(BattleCommon):

    @users('battle_admin')
    def test_linked_location(self):
        """ Links between twin locations are kept symmetric """
        isca, londinium = (self.location_isca + self.location_londinium).with_env(self.env)
        umbra = self.env['battle.location'].create({
            'name': 'Isca Augusta (Umbra)',
            'linked_location_id': isca.id,
        })
        self.assertEqual(isca.linked_location_id, umbra)

        # relink: previous twin is released
        umbra.linked_location_id = londinium
        self.assertEqual(londinium.linked_location_id, umbra)
        self.assertFalse(isca.linked_location_id)

        # unlink from the other side
        londinium.linked_location_id = False
        self.assertFalse(umbra.linked_location_id)

        with self.assertRaises(ValidationError):
            isca.linked_location_id = isca

    @users('battle_admin')
    def test_status(self):
        """ A held location needs a holder; freeing a location releases it,
        contesting it keeps it """
        location = self.location_isca.with_env(self.env)
        with self.assertRaises(ValidationError):
            location.status = 'held'

        with Form(location) as location_form:
            location_form.status = 'held'
            location_form.held_by_faction_id = self.faction_good
        self.assertEqual(location.held_by_faction_id, self.faction_good)

        # contested: holder is kept, free: holder is released
        location.status = 'contested'
        self.assertEqual(location.held_by_faction_id, self.faction_good)
        location.status = 'free'
        self.assertFalse(location.held_by_faction_id)

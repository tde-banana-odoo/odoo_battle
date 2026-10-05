from odoo import api, models

from odoo.addons.odoo_battle.report.battle_unit_sheet import SHEETS_PER_PAGE


class ReportBattleLocationSheet(models.AbstractModel):
    """ Printable location sheets, same cards as unit ones (70x50mm, 10 per
    A4 page): status and holder to fill in by hand during play, twin location,
    traits with their rules, boxes for traits granted by battles for the next
    round, tokens zone. """
    _name = 'report.odoo_battle.report_location_sheet'
    _description = "Location Sheets"

    @api.model
    def _get_report_values(self, docids, data=None):
        sheets = [self._get_sheet_values(location) for location in self.env['battle.location'].browse(docids)]
        return {'pages': [sheets[index:index + SHEETS_PER_PAGE] for index in range(0, len(sheets), SHEETS_PER_PAGE)]}

    @api.model
    def _get_sheet_values(self, location):
        return {
            'name': location.name,
            'is_umbra': location.is_umbra,
            'linked': location.linked_location_id.name or '',
            'traits': [(trait.name, trait.description or '') for trait in location.battle_trait_ids.sorted()],
        }

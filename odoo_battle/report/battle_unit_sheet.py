import base64

from odoo import api, models

SHEETS_PER_PAGE = 10


class ReportBattleUnitSheet(models.AbstractModel):
    """ Printable unit sheets (70x50mm cards, 10 per A4 page), for units or
    blank ones (from templates, or fully blank) to fill by hand. """
    _name = 'report.odoo_battle.report_unit_sheet'
    _description = "Unit Sheets"

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        if data.get('blank'):
            templates = self.env['battle.unit.template'].browse(data.get('template_ids', []))
            sheets = [
                self._get_sheet_values(template, blank=True)
                for template in templates for _copy in range(data.get('copies', 1))
            ] + [self._get_sheet_values(None, blank=True)] * data.get('blank_copies', 0)
        else:
            sheets = [self._get_sheet_values(unit) for unit in self.env['battle.unit'].browse(docids)]
        return {'pages': [sheets[index:index + SHEETS_PER_PAGE] for index in range(0, len(sheets), SHEETS_PER_PAGE)]}

    @api.model
    def _get_sheet_values(self, record, blank=False):
        """ Values of a sheet, from a unit or a template (blank sheet to fill
        in), or fully blank if no record """
        image = record and record.image_1920
        traits = record.battle_trait_ids if record else self.env['battle.trait']
        is_unit = bool(record) and record._name == 'battle.unit'
        return {
            'blank': blank,
            'name': record.display_name if is_unit else '',
            'faction': record.battle_faction_id.name if is_unit else '',
            'template': record.name if record and not is_unit else '',
            'image': image and f'data:{image.mimetype};base64,{base64.b64encode(image.content).decode()}',
            **{
                fname: record[fname] if record else None
                for fname in ('menace', 'size', 'rage', 'gnosis', 'willpower', 'damage', 'resistance')
            },
            'wounds': 4 - int(record.wound_state) if is_unit else 0,
            'battle_traits': traits.filtered(lambda trait: trait.effect != 'none').mapped('name'),
            'lore_traits': traits.filtered(lambda trait: trait.effect == 'none').mapped('name'),
        }

import base64

from odoo import api, models

from odoo.addons.odoo_battle.const import DAMAGE_PER_WOUND
from odoo.addons.odoo_battle.models.battle_unit_stats_mixin import get_unit_type_print_glyph

SHEETS_PER_PAGE = 10
# characters fitting on the combat traits line (estimated, at its font size);
# longer combat traits wrap over the lore line, lore traits being appended,
# in a smaller font (3 lines instead of 2) if they still do not fit
TRAITS_LINE_CHARS = 36
TRAITS_MERGED_CHARS = 66


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
        in), or fully blank if no record. Wounds and damage are left blank, to
        update by hand; the unit type glyph is printed in black and white, to
        color by hand. """
        image = get_unit_type_print_glyph(record.unit_type) if record and record.unit_type else False
        traits = record.battle_trait_ids if record else self.env['battle.trait']
        is_unit = bool(record) and record._name == 'battle.unit'
        template = record.battle_unit_template_id if is_unit else record
        # non-breaking hyphens: 'Contre-Attaque' never split on two lines
        battle_traits = [name.replace('-', '\u2011') for name in traits.filtered(lambda trait: trait.effect != 'lore').mapped('name')]
        lore_traits = [name.replace('-', '\u2011') for name in traits.filtered(lambda trait: trait.effect == 'lore').mapped('name')]
        traits_length = len(', '.join(battle_traits)) + (len(', '.join(lore_traits)) + 6 if lore_traits else 0)
        return {
            'blank': blank,
            'name': record.display_name if is_unit else '',
            'faction': record.battle_faction_id.name if is_unit else '',
            'template': record.name if record and not is_unit else '',
            'short_name': (template and template.short_name) or '',
            'image': image and f'data:image/svg+xml;base64,{base64.b64encode(image).decode()}',
            **{
                fname: record[fname] if record else None
                for fname in ('menace', 'size', 'rage', 'gnosis', 'willpower', 'damage', 'resistance')
            },
            'damage_slots': DAMAGE_PER_WOUND - 1,
            'battle_traits': battle_traits,
            'lore_traits': lore_traits,
            'traits_merged': len(', '.join(battle_traits)) > TRAITS_LINE_CHARS,
            'traits_small': traits_length > TRAITS_MERGED_CHARS,
        }

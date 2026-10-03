from odoo import fields, models


class BattleUnitSheetWizard(models.TransientModel):
    """ Print blank unit sheets, to have a reserve on the table """
    _name = 'battle.unit.sheet.wizard'
    _description = "Print Blank Unit Sheets"

    battle_unit_template_ids = fields.Many2many(
        'battle.unit.template', string="Templates",
        default=lambda self: self.env.context.get('active_model') == 'battle.unit.template' and self.env.context.get('active_ids'),
        help="Sheets pre-filled with template statistics, name and faction to fill in.",
    )
    copies = fields.Integer("Copies per Template", default=2)
    blank_copies = fields.Integer("Fully Blank Sheets", default=0)

    def action_print(self):
        self.ensure_one()
        return self.env.ref('odoo_battle.action_report_unit_sheet').report_action(None, data={
            'blank': True,
            'template_ids': self.battle_unit_template_ids.ids,
            'copies': self.copies,
            'blank_copies': self.blank_copies,
        })

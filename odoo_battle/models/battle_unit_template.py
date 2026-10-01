from odoo import fields, models

# template values followed by units, unless tweaked
FOLLOWED_FIELDS = ['unit_type', 'menace', 'size', 'rage', 'willpower', 'gnosis', 'damage', 'resistance', 'battle_trait_ids']


class BattleUnitTemplate(models.Model):
    _name = 'battle.unit.template'
    _inherit = ['battle.unit.stats.mixin']
    _description = "Unit Template"
    _order = 'sequence asc, id asc'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer()
    battle_unit_ids = fields.One2many('battle.unit', 'battle_unit_template_id', string="Units")

    def write(self, vals):
        """ Units follow template changes for values they did not tweak, i.e.
        values still equal to the previous template ones """
        fnames = [fname for fname in FOLLOWED_FIELDS if fname in vals]
        previous = {template: {fname: template[fname] for fname in fnames} for template in self}
        res = super().write(vals)
        for template in self:
            for fname in fnames:
                units = template.battle_unit_ids.filtered(lambda unit: unit[fname] == previous[template][fname])
                if units and template[fname] != previous[template][fname]:
                    units[fname] = template[fname]
        return res

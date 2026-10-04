from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BattleTrait(models.Model):
    """ Simple mechanics differentiating units or locations: depending on
    the stance of a side and its result, give a bonus (before rolling) or
    damage (after). """
    _name = 'battle.trait'
    _description = "Trait"
    _order = 'sequence asc, id asc'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer()
    description = fields.Text(translate=True)
    target = fields.Selection(
        [('unit', 'Unit'), ('location', 'Location')],
        string="Target", default='unit', required=True,
    )
    # when
    side = fields.Selection(
        [('initiator', 'Initiators'), ('responder', 'Responders'), ('any', 'Any')],
        string="Side", default='any', required=True,
        help="Battle side benefiting from the trait, e.g. only holders (responders) benefit from fortifications.",
    )
    stance = fields.Selection(
        [('attack', 'When Attacking'), ('defense', 'When Defending'), ('any', 'Always')],
        string="Stance", default='any', required=True,
        help="Battle stance of the side the trait belongs to.",
    )
    condition = fields.Selection(
        [('win', 'On Win'), ('lose', 'On Loss'), ('any', 'Always')],
        string="Condition", default='any', required=True,
        help="Win or loss of the side the trait belongs to.",
    )
    # what
    effect = fields.Selection(
        [('damage', 'Damage'), ('bonus', 'Battle Bonus'), ('none', 'None (lore)')],
        string="Effect", default='none', required=True,
    )
    value = fields.Integer("Value", default=1)
    is_unique = fields.Boolean(
        "Once per Side", help="Counts only once per side in a battle, whatever the number of units having it.",
    )

    @api.constrains('effect', 'condition')
    def _check_effect_condition(self):
        for trait in self:
            if trait.effect == 'bonus' and trait.condition != 'any':
                raise ValidationError(_(
                    "Trait %(trait_name)s gives a battle bonus, applied before rolling: it cannot depend on win or loss.",
                    trait_name=trait.name,
                ))

    def _applies(self, side, stance, result=None):
        """ Traits applying for ``side`` ('initiator' or 'responder') in
        ``stance`` ('attack' or 'defense'), given its ``result`` ('win',
        'lose', 'tie') if known. """
        return self.filtered(lambda trait: (
            trait.side in (side, 'any') and trait.stance in (stance, 'any') and trait.condition in (result, 'any')
        ))

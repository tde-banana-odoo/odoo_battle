from __future__ import annotations

import typing

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

if typing.TYPE_CHECKING:
    from odoo.addons.odoo_battle.const import Position, Side, SideResult, Stance


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
        help="Location traits: battle side benefiting from the trait, e.g. only holders (responders) benefit from "
             "fortifications. Unit traits apply to their holder side, depending on its stance.",
    )
    stance = fields.Selection(
        [('attack', 'When Attacking'), ('defense', 'When Defending'), ('any', 'Always')],
        string="Stance", default='any', required=True,
        help="Battle stance of the side the trait belongs to.",
    )
    position = fields.Selection(
        [('frontline', 'Frontline'), ('support', 'Support'), ('any', 'Any')],
        string="Position", default='any', required=True,
        help="Position of the unit holding the trait (location traits: any).",
    )
    condition = fields.Selection(
        [('win', 'On Win'), ('lose', 'On Loss'), ('any', 'Always')],
        string="Condition", default='any', required=True,
        help="Win or loss of the side the trait belongs to.",
    )
    # what
    effect = fields.Selection(
        [
            ('bonus', 'Battle Bonus'),
            ('damage', 'Damage'),
            ('resistance', 'Resistance'),
            ('damage_rate', 'Damage Rate'),
            ('resistance_rate', 'Resistance Rate'),
            ('size_rate', 'Size Rate'),
            ('wound_enemy', 'Wound Enemy'),
            ('heal_self', 'Heal Self'),
            ('mend_self', 'Mend Self'),
            ('support_damage', 'Support Damage'),
            ('support_resistance', 'Support Resistance'),
            ('diversion', 'Diversion'),
            ('reroll', 'Dice Reroll'),
            ('forced_reroll', 'Forced Reroll'),
            ('assassin', 'Assassination'),
            ('ambush', 'Ambush'),
            ('lore', 'Lore (manual)'),
        ],
        string="Effect", default='lore', required=True,
        help="Battle Bonus: added before rolling. "
             "Damage, Resistance: added to the side damage (before enemy resistance) or resistance. "
             "Damage Rate, Resistance Rate: change (in %, e.g. -25) of the side frontline damage or resistance, "
             "multiplied with outcome and command actions rates. "
             "Size Rate: change (in %, e.g. -25) of the side size, for the size bonus. "
             "Wound Enemy: wounds enemy units directly (ignoring resistance), frontline and least wounded first. "
             "Heal Self: units of the side to heal (one wound less) after the battle, one per value point. "
             "Mend Self: units of the side to mend (damage counter reset) after the battle, one per value point. "
             "Heal and mend are prefilled in the solver (most wounded / damaged first), and can be changed. "
             "Support Damage: support unit adds its damage to the side damage. Support Resistance: support unit adds its damage to the side resistance. "
             "Diversion: removes its value from the enemy compared characteristic, spread over its creatures (size): it matters less for bigger sides; e.g. once per side. Dice Reroll: dice the side may reroll. "
             "Forced Reroll: dice the side has to reroll, its best ones (highest for initiators, lowest for responders). "
             "Assassination: wounds a chosen enemy unit before rolling. Ambush: puts a chosen enemy unit out of the battle. "
             "Lore: no battle effect, resolved manually by the DM (narration, units updates).",
    )
    value = fields.Integer("Value", default=1, help="Bonus, damage, resistance, rate change (%), number of wounds, damage points or dice. Unused for support effects.")
    is_unique = fields.Boolean(
        "Once per Side", help="Counts only once per side in a battle, whatever the number of units having it.",
    )

    @api.constrains('effect', 'condition', 'position', 'target', 'side')
    def _check_effect_condition(self):
        for trait in self:
            if trait.target == 'unit' and trait.side != 'any':
                raise ValidationError(_(
                    "Trait %(trait_name)s is a unit trait: it applies to its holder side, use stance and position instead of side.",
                    trait_name=trait.name,
                ))
            if trait.effect == 'bonus' and trait.condition != 'any':
                raise ValidationError(_(
                    "Trait %(trait_name)s gives a battle bonus, applied before rolling: it cannot depend on win or loss.",
                    trait_name=trait.name,
                ))
            if trait.effect in ('support_damage', 'support_resistance') and trait.position != 'support':
                raise ValidationError(_(
                    "Trait %(trait_name)s is a support effect: it should be held by support units.",
                    trait_name=trait.name,
                ))

    def _applies(self, side: Side, stance: Stance, result: SideResult | None = None, position: Position | None = None) -> BattleTrait:
        """ Traits applying for ``side`` ('initiator' or 'responder') in
        ``stance`` ('attack' or 'defense'), given its ``result`` ('win',
        'lose', 'tie') if known, for a holder in ``position`` ('frontline' or
        'support', None for location traits). """
        return self.filtered(lambda trait: (
            trait.side in (side, 'any') and trait.stance in (stance, 'any') and trait.condition in (result, 'any')
            and trait.position in (position, 'any')
        ))

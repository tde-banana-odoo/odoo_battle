from odoo import api, fields, models


class BattleLocationEffect(models.Model):
    """ Trait a faction benefits from (or suffers) in a location for a given
    round, e.g. Percée (breakthrough) granted by a clear-cut victory for the next
    round. Granted by battle results (location and round then come from the
    result, removed when cancelling it), or set manually. """
    _name = 'battle.location.effect'
    _description = "Location Effect"
    _order = 'round_number desc, battle_location_id, id'

    battle_result_id = fields.Many2one(
        'battle.result', string="Granted By", index='btree_not_null', ondelete='cascade', readonly=True,
    )
    battle_location_id = fields.Many2one('battle.location', string="Location", required=True, index=True, ondelete='cascade')
    round_number = fields.Integer("Round", required=True, help="Round during which the effect applies: the one after the battle granting it.")
    # matched by number, as effects may be granted for a round not created yet
    battle_round_id = fields.Many2one(
        'battle.round', string="Round Record", compute='_compute_battle_round_id', store=True, readonly=False,
        index='btree_not_null', ondelete='set null',
    )
    battle_faction_id = fields.Many2one('battle.faction', string="Faction", required=True, ondelete='cascade')
    battle_trait_id = fields.Many2one(
        'battle.trait', string="Trait", required=True, ondelete='cascade',
        domain="[('target', '=', 'location')]",
    )

    @api.depends('round_number')
    def _compute_battle_round_id(self):
        rounds = self.env['battle.round'].search([('round_number', 'in', self.mapped('round_number'))])
        for effect in self:
            effect.battle_round_id = rounds.filtered(lambda battle_round: battle_round.round_number == effect.round_number)[:1]

    @api.model_create_multi
    def create(self, vals_list):
        """ Effects granted by a result default to its location, for the
        round after it; effects created from a round apply to it """
        for vals in vals_list:
            if vals.get('battle_round_id') and not vals.get('round_number'):
                vals['round_number'] = self.env['battle.round'].browse(vals['battle_round_id']).round_number
            if vals.get('battle_result_id'):
                result = self.env['battle.result'].browse(vals['battle_result_id'])
                vals.setdefault('battle_location_id', result.battle_location_id.id)
                vals.setdefault('round_number', result.battle_round_id.round_number + 1)
        return super().create(vals_list)

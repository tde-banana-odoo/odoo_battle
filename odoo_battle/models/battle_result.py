from odoo import api, fields, models

from odoo.addons.odoo_battle.const import LOCATION_STATUSES, STANCES


class BattleResult(models.Model):
    """ Result of a battle solved (and applied) in a location for a round:
    sides, roll and outcome, units consequences (one line per unit, with its
    state before the battle), location consequences (status shift, effects
    granted for the next round). Only one valid result per location and
    round: cancel it to solve the battle again, which reverts everything. """
    _name = 'battle.result'
    _description = "Battle Result"
    _order = 'battle_round_id desc, id desc'

    battle_round_id = fields.Many2one('battle.round', string="Round", required=True, index=True, ondelete='restrict')
    battle_location_id = fields.Many2one('battle.location', string="Location", required=True, ondelete='restrict')
    state = fields.Selection([('done', 'Done'), ('cancel', 'Cancelled')], string="Status", default='done', required=True)
    # sides
    initiator_faction_ids = fields.Many2many(
        'battle.faction', 'battle_result_initiator_faction_rel', 'result_id', 'faction_id', string="Initiators",
    )
    responder_faction_ids = fields.Many2many(
        'battle.faction', 'battle_result_responder_faction_rel', 'result_id', 'faction_id', string="Responders",
    )
    initiator_stance = fields.Selection(STANCES, string="Initiators Stance")
    responder_stance = fields.Selection(STANCES, string="Responders Stance")
    battle_result_line_ids = fields.One2many('battle.result.line', 'battle_result_id', string="Units")
    # result
    bonus = fields.Integer("Bonus")
    dice_roll = fields.Char("Dice Roll")
    result_score = fields.Integer("Score")
    battle_outcome_id = fields.Many2one('battle.outcome', string="Outcome")
    damage_to_initiators = fields.Integer("Damage to Initiators")
    damage_to_responders = fields.Integer("Damage to Responders")
    result_message = fields.Text("Result")
    # consequences on the location: effects granted for the next round, status shift (reverted when cancelling)
    battle_location_effect_ids = fields.One2many('battle.location.effect', 'battle_result_id', string="Granted Effects")
    location_status_before = fields.Selection(LOCATION_STATUSES, string="Location Status Before", help="Set if the battle shifted the location.")
    held_by_faction_before_id = fields.Many2one('battle.faction', string="Held By Before")

    _round_location_uniq = models.UniqueIndex(
        "(battle_round_id, battle_location_id) WHERE state = 'done'",
        "A battle has already been solved in this location for this round: cancel it first.",
    )

    @api.depends('battle_round_id', 'battle_location_id')
    def _compute_display_name(self):
        for result in self:
            result.display_name = f"{result.battle_round_id.display_name} - {result.battle_location_id.name}"

    def action_cancel(self):
        """ Cancel results, restoring damage and wounds of units and the
        location as before the battle, removing granted effects """
        done = self.filtered(lambda result: result.state == 'done')
        for line in done.battle_result_line_ids:
            line.battle_unit_id.write({
                'damage_counter': line.damage_counter_before,
                'wound_state': line.wound_state_before,
            })
        for result in done.filtered('location_status_before'):
            result.battle_location_id.write({
                'status': result.location_status_before,
                'held_by_faction_id': result.held_by_faction_before_id.id,
            })
        done.battle_location_effect_ids.unlink()
        self.state = 'cancel'


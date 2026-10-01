from odoo import api, fields, models

STANCES = [('attack', 'Attack'), ('defense', 'Defend')]


class BattleResult(models.Model):
    """ Result of a battle solved in a location for a round. Only one valid
    result per location and round: cancel it to solve the battle again. """
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
    initiator_unit_ids = fields.Many2many(
        'battle.unit', 'battle_result_initiator_unit_rel', 'result_id', 'unit_id', string="Initiator Units",
    )
    responder_unit_ids = fields.Many2many(
        'battle.unit', 'battle_result_responder_unit_rel', 'result_id', 'unit_id', string="Responder Units",
    )
    # result
    bonus = fields.Integer("Bonus")
    dice_roll = fields.Char("Dice Roll")
    result_score = fields.Integer("Score")
    battle_outcome_id = fields.Many2one('battle.outcome', string="Outcome")
    damage_to_initiators = fields.Integer("Damage to Initiators")
    damage_to_responders = fields.Integer("Damage to Responders")
    result_message = fields.Text("Result")

    _round_location_uniq = models.UniqueIndex(
        "(battle_round_id, battle_location_id) WHERE state = 'done'",
        "A battle has already been solved in this location for this round: cancel it first.",
    )

    @api.depends('battle_round_id', 'battle_location_id')
    def _compute_display_name(self):
        for result in self:
            result.display_name = f"{result.battle_round_id.display_name} - {result.battle_location_id.name}"

    def action_cancel(self):
        self.state = 'cancel'

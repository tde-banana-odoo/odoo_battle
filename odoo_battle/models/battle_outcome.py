from odoo import fields, models

OUTCOME_SCORE_MIN, OUTCOME_SCORE_MAX = -4, 4


class BattleOutcome(models.Model):
    """ Battle outcome, from initiators point of view: score goes from major
    defeat (-4) to major victory (+4). """
    _name = 'battle.outcome'
    _description = "Battle Outcome"
    _order = 'score asc'

    name = fields.Char(required=True, translate=True)
    score = fields.Integer(required=True)
    # additional effects, taken into account in damage computation
    initiator_damage = fields.Integer("Initiators Extra Damage")
    initiator_resistance = fields.Integer("Initiators Extra Resistance")
    responder_damage = fields.Integer("Responders Extra Damage")
    responder_resistance = fields.Integer("Responders Extra Resistance")
    # effects on location, applied after battle (TDE TODO)
    location_shift = fields.Integer(
        "Location Shift",
        help="Steps the location status moves: positive towards initiators taking it, negative towards responders.",
    )
    battle_trait_ids = fields.Many2many(
        'battle.trait', string="Granted Traits", domain="[('target', '=', 'location')]",
        help="Location traits granted to the winner for the next round, e.g. Breakthrough.",
    )

    _score_uniq = models.Constraint('UNIQUE(score)', "An outcome already exists for this score.")
    _score_range = models.Constraint(
        f'CHECK(score >= {OUTCOME_SCORE_MIN} AND score <= {OUTCOME_SCORE_MAX})',
        f"Score should be between {OUTCOME_SCORE_MIN} and {OUTCOME_SCORE_MAX}.",
    )

from __future__ import annotations

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from odoo.addons.odoo_battle.const import OUTCOME_SCORE_MAX, OUTCOME_SCORE_MIN


class BattleOutcome(models.Model):
    """ Battle outcome, for the side getting this score: from major defeat
    (-4) to major victory (+4). Each side reads its own outcome (initiators
    the battle score, responders its opposite) for its stance: rates applied
    to its frontline damage and resistance, traits granted for the next
    round in the location. The winner, if attacking, shifts the location. """
    _name = 'battle.outcome'
    _description = "Battle Outcome"
    _order = 'score asc'

    name = fields.Char(required=True, translate=True)
    score = fields.Integer(required=True)
    # rates (%) of frontline damage and resistance, depending on the stance
    attack_damage_rate = fields.Integer("Attack Damage (%)", default=100)
    attack_resistance_rate = fields.Integer("Attack Resistance (%)", default=50)
    defense_damage_rate = fields.Integer("Defense Damage (%)", default=50)
    defense_resistance_rate = fields.Integer("Defense Resistance (%)", default=150)
    # traits granted in the location for the next round, depending on the stance
    attack_trait_ids = fields.Many2many(
        'battle.trait', 'battle_outcome_attack_trait_rel', 'outcome_id', 'trait_id',
        string="Attack Granted Traits", domain="[('target', '=', 'location')]",
        help="Location traits granted to the side factions for the next round, when attacking.",
    )
    defense_trait_ids = fields.Many2many(
        'battle.trait', 'battle_outcome_defense_trait_rel', 'outcome_id', 'trait_id',
        string="Defense Granted Traits", domain="[('target', '=', 'location')]",
        help="Location traits granted to the side factions for the next round, when defending.",
    )
    location_shift = fields.Integer(
        "Location Shift",
        help="Steps the location status moves towards the winner, if attacking (victories only).",
    )

    _score_uniq = models.Constraint('UNIQUE(score)', "An outcome already exists for this score.")
    _score_range = models.Constraint(
        f'CHECK(score >= {OUTCOME_SCORE_MIN} AND score <= {OUTCOME_SCORE_MAX})',
        f"Score should be between {OUTCOME_SCORE_MIN} and {OUTCOME_SCORE_MAX}.",
    )

    @api.constrains('score', 'location_shift')
    def _check_location_shift(self):
        if any(outcome.location_shift and outcome.score <= 0 for outcome in self):
            raise ValidationError(_("Only victories shift the location."))

    @api.model
    def _get_by_score(self) -> dict[int, BattleOutcome]:
        return {outcome.score: outcome for outcome in self.search([])}

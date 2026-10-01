from odoo import api, fields, models, _


class BattleRound(models.Model):
    """ Game round: factions roll their leadership, then battles are solved
    in locations. The current round is the last one. """
    _name = 'battle.round'
    _inherit = ['mail.thread']
    _description = "Round"
    _order = 'round_number desc'

    round_number = fields.Integer(
        "Round", required=True, tracking=True,
        default=lambda self: (self.search([], limit=1).round_number or 0) + 1,
    )
    battle_round_leadership_ids = fields.One2many(
        'battle.round.leadership', 'battle_round_id', string="Leadership",
        default=lambda self: [(0, 0, {'battle_faction_id': faction.id}) for faction in self.env['battle.faction'].search([])],
    )
    battle_result_ids = fields.One2many('battle.result', 'battle_round_id', string="Battles")

    _round_number_uniq = models.Constraint('UNIQUE(round_number)', "This round already exists.")

    @api.depends('round_number')
    def _compute_display_name(self):
        for battle_round in self:
            battle_round.display_name = _("Round %s", battle_round.round_number)

    @api.model
    def _get_current(self):
        return self.search([], limit=1)

    @api.model
    def action_start_next_round(self):
        return self.create({}).id

    @api.model
    def get_dashboard_data(self):
        """ Summary of the current game state, for the DM dashboard """
        current = self._get_current()
        results = current.battle_result_ids.filtered(lambda result: result.state == 'done')
        leadership = {line.battle_faction_id: line.successes for line in current.battle_round_leadership_ids}
        locations = self.env['battle.location'].search([('is_external', '=', False)])
        pending = []
        for location in locations - results.battle_location_id:
            initiators, responders = location._get_battle_sides()
            if initiators and responders:
                pending.append({
                    'id': location.id,
                    'name': location.name,
                    'initiators': initiators.sorted().mapped('name'),
                    'responders': responders.sorted().mapped('name'),
                })
        return {
            'is_admin': self.env.user.has_group('base.group_system'),
            'round': {'id': current.id, 'name': current.display_name} if current else False,
            'factions': [{
                'id': faction.id,
                'name': faction.name,
                'role': dict(faction._fields['role']._description_selection(self.env))[faction.role],
                'ally': faction.allied_faction_id.name,
                'unit_count': faction.battle_unit_count,
                'morale': faction.morale,
                'leadership': leadership.get(faction),
            } for faction in self.env['battle.faction'].search([])],
            'results': [{
                'id': result.id,
                'location': result.battle_location_id.name,
                'initiators': result.initiator_faction_ids.sorted().mapped('name'),
                'responders': result.responder_faction_ids.sorted().mapped('name'),
                'outcome': result.battle_outcome_id.name,
                'score': result.result_score,
                'damage_to_initiators': result.damage_to_initiators,
                'damage_to_responders': result.damage_to_responders,
            } for result in results],
            'pending': pending,
            'unplaced_units': [
                {'id': unit.id, 'name': unit.name, 'faction': unit.battle_faction_id.name}
                for unit in self.env['battle.unit'].search([('battle_location_id', '=', False)])
            ],
        }


class BattleRoundLeadership(models.Model):
    """ Leadership roll of a faction for a round: each success allows to take
    leadership actions. """
    _name = 'battle.round.leadership'
    _description = "Leadership Roll"
    _order = 'battle_round_id, battle_faction_id'

    battle_round_id = fields.Many2one('battle.round', string="Round", required=True, index=True, ondelete='cascade')
    battle_faction_id = fields.Many2one('battle.faction', string="Faction", required=True, ondelete='cascade')
    successes = fields.Integer("Successes")

    _round_faction_uniq = models.Constraint(
        'UNIQUE(battle_round_id, battle_faction_id)', "A faction rolls leadership once per round.",
    )

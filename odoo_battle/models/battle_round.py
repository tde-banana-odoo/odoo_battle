from odoo import api, fields, models, _

from odoo.addons.odoo_battle.models.battle_faction import MORALES


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
        default=lambda self: [
            (0, 0, {'battle_faction_id': faction.id, 'morale': faction.morale})  # morale carried over from previous round
            for faction in self.env['battle.faction'].search([])
        ],
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
    def action_open_leadership(self, faction_id):
        """ Enter the leadership roll of a faction for the current round """
        current = self._get_current()
        line = current.battle_round_leadership_ids.filtered(lambda line: line.battle_faction_id.id == faction_id)
        if not line:
            line = self.env['battle.round.leadership'].create({'battle_round_id': current.id, 'battle_faction_id': faction_id})
        return {
            'type': 'ir.actions.act_window',
            'name': _("Leadership Roll"),
            'res_model': 'battle.round.leadership',
            'res_id': line.id,
            'views': [(False, 'form')],
            'target': 'new',
        }

    @api.model
    def get_dashboard_data(self):
        """ Summary of the current game state, for the DM dashboard """
        current = self._get_current()
        previous = self.search([('round_number', '<', current.round_number)], limit=1) if current else self
        lines = {line.battle_faction_id: line for line in current.battle_round_leadership_ids}
        previous_lines = {line.battle_faction_id: line for line in previous.battle_round_leadership_ids}
        results = current.battle_result_ids.filtered(lambda result: result.state == 'done')
        locations = self.env['battle.location'].search([('is_external', '=', False)])
        leaders = self.env['battle.leader'].search([])

        def label(record, fname):
            return dict(record._fields[fname]._description_selection(self.env)).get(record[fname])

        def morale_trend(faction):
            if faction not in lines or faction not in previous_lines:
                return False
            delta = int(lines[faction].morale) - int(previous_lines[faction].morale)
            return 'up' if delta > 0 else 'down' if delta < 0 else 'same'

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
                'role': label(faction, 'role'),
                'ally': faction.allied_faction_id.name,
                'leader': {
                    'name': faction.leader_id.name,
                    'state': faction.leader_id.state,
                    'state_label': label(faction.leader_id, 'state'),
                } if faction.leader_id else False,
                'unit_count': faction.battle_unit_count,
                'morale': label(faction, 'morale'),
                'morale_trend': morale_trend(faction),
                'leadership': lines[faction].successes if faction in lines else None,
            } for faction in self.env['battle.faction'].search([])],
            'locations': [{
                'id': location.id,
                'name': location.name,
                'status': location.status,
                'status_label': label(location, 'status'),
                'holder': location.held_by_faction_id.name,
                'forces': [{'faction': faction.name, 'count': count} for faction, count in location._get_forces()],
                'leaders': leaders.filtered(lambda leader: leader.battle_location_id == location).mapped('name'),
            } for location in locations],
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
                for unit in self.env['battle.unit'].search([('battle_location_id', '=', False), ('is_dead', '=', False)])
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
    morale = fields.Selection(MORALES, string="Morale", default='3', required=True)

    _round_faction_uniq = models.Constraint(
        'UNIQUE(battle_round_id, battle_faction_id)', "A faction rolls leadership once per round.",
    )

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from odoo.addons.odoo_battle.const import CAERN_STATES, CAMPS, MORALES


class BattleRound(models.Model):
    """ Game round. Each camp (aggressors, defenders; neutral factions follow
    their ally) rolls its leadership: morale (carried over from the previous
    round, low morale being a battle malus) and command actions to pick in
    locations (optional). Then battles are solved in locations. The Caern
    integrity is followed round after round. The current round is the last
    one. """
    _name = 'battle.round'
    _inherit = ['mail.thread']
    _description = "Round"
    _order = 'round_number desc'

    round_number = fields.Integer(
        "Round", required=True, tracking=True,
        default=lambda self: (self.search([], limit=1).round_number or 0) + 1,
    )
    battle_result_ids = fields.One2many('battle.result', 'battle_round_id', string="Battles")
    caern_state = fields.Selection(
        CAERN_STATES, string="Caern", required=True, tracking=True,
        default=lambda self: self._get_current().caern_state or '4',  # carried over from previous round
        help="Integrity of the Caern defended by the players, from full power (4) to corrupted (0).",
    )
    # leadership of aggressors
    aggressor_morale = fields.Selection(
        MORALES, string="Aggressors Morale", required=True, tracking=True,
        default=lambda self: self._get_current().aggressor_morale or '3',  # carried over from previous round
    )
    aggressor_command_action_count = fields.Integer(
        "Aggressors Command Actions", tracking=True,
        help="Leadership successes: command actions the camp may pick.",
    )
    aggressor_command_action_ids = fields.One2many(
        'battle.command.action', 'battle_round_id', string="Aggressors Picked Actions",
        domain=[('camp', '=', 'aggressor')],
    )
    # leadership of defenders
    defender_morale = fields.Selection(
        MORALES, string="Defenders Morale", required=True, tracking=True,
        default=lambda self: self._get_current().defender_morale or '3',  # carried over from previous round
    )
    defender_command_action_count = fields.Integer(
        "Defenders Command Actions", tracking=True,
        help="Leadership successes: command actions the camp may pick.",
    )
    defender_command_action_ids = fields.One2many(
        'battle.command.action', 'battle_round_id', string="Defenders Picked Actions",
        domain=[('camp', '=', 'defender')],
    )
    # edited round by round, e.g. a trait granted to a faction on several locations
    battle_location_effect_ids = fields.One2many('battle.location.effect', 'battle_round_id', string="Location Effects")

    _round_number_uniq = models.Constraint('UNIQUE(round_number)', "This round already exists.")

    @api.constrains('aggressor_command_action_count', 'defender_command_action_count')
    def _check_command_action_count(self):
        """ A camp picks at most its command actions """
        camp_labels = dict(CAMPS)
        for battle_round in self:
            for camp in camp_labels:
                picked = len(battle_round[f'{camp}_command_action_ids'])
                count = battle_round[f'{camp}_command_action_count']
                if picked > count:
                    raise ValidationError(_(
                        "%(camp)s picked %(picked)s command actions in %(round)s, but have only %(count)s.",
                        camp=camp_labels[camp], picked=picked, round=battle_round.display_name, count=count,
                    ))

    @api.model_create_multi
    def create(self, vals_list):
        """ Effects already granted for the new rounds (by outcomes of the
        previous one) are linked to them """
        rounds = super().create(vals_list)
        rounds._link_location_effects()
        return rounds

    def write(self, vals):
        res = super().write(vals)
        if 'round_number' in vals:
            self._link_location_effects()
        return res

    @api.depends('round_number')
    def _compute_display_name(self):
        for battle_round in self:
            battle_round.display_name = _("Round %(round_number)s", round_number=battle_round.round_number)

    def _link_location_effects(self):
        """ Link location effects to their round, matched by number (outcomes
        grant them for the next round, before it exists) """
        effects = self.env['battle.location.effect'].search([('round_number', 'in', self.mapped('round_number'))])
        for battle_round in self:
            effects.filtered(lambda effect: effect.round_number == battle_round.round_number).battle_round_id = battle_round

    @api.model
    def action_start_next_round(self):
        """ Start the next round (dashboard): it becomes the current one """
        return self.create({})

    @api.model
    def action_open_leadership(self):
        """ Enter leadership of both camps for the current round (dashboard) """
        return {
            'type': 'ir.actions.act_window',
            'name': _("Leadership"),
            'res_model': 'battle.round',
            'res_id': self._get_current().id,
            'views': [(self.env.ref('odoo_battle.battle_round_view_form_leadership').id, 'form')],
            'target': 'new',
        }

    @api.model
    def get_dashboard_data(self):
        """ Summary of the current game state, for the DM dashboard """
        current = self._get_current()
        previous = self.search([('round_number', '<', current.round_number)], limit=1) if current else self
        results = current.battle_result_ids.filtered(lambda result: result.state == 'done')
        locations = self.env['battle.location'].search([('is_external', '=', False)])
        leaders = self.env['battle.leader'].search([])
        factions = self.env['battle.faction'].search([])

        def label(record, fname):
            return dict(record._fields[fname]._description_selection(self.env)).get(record[fname])

        def morale_trend(camp):
            if not previous:
                return False
            delta = int(current[f'{camp}_morale']) - int(previous[f'{camp}_morale'])
            if delta > 0:
                return 'up'
            if delta < 0:
                return 'down'
            return 'same'

        outcomes = self.env['battle.outcome']._get_by_score()

        def battle_summary(result):
            """ Winner and its outcome, e.g. 'Kiker Victory' (main faction of
            the winning side), or 'Tied' """
            score = result.result_score
            if not score:
                return result.battle_outcome_id.name
            winners = result.initiator_faction_ids if score > 0 else result.responder_faction_ids
            return f"{winners.sorted()[:1].name} {outcomes[abs(score)].name}"

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
        pending_ids = {location['id'] for location in pending}
        location_results = {result.battle_location_id: result for result in results}
        return {
            'is_admin': self.env.user.has_group('base.group_system'),
            'round': {
                'id': current.id,
                'name': current.display_name,
                'caern_state': current.caern_state,
                'caern_label': label(current, 'caern_state'),
            } if current else False,
            'factions': [{
                'id': faction.id,
                'name': faction.name,
                'role': label(faction, 'role'),
                'ally': faction.allied_faction_id.name,
                'leader': {
                    'name': faction.leader_id.name,
                    'narrative_state': faction.leader_id.narrative_state,
                    'narrative_state_label': label(faction.leader_id, 'narrative_state'),
                } if faction.leader_id else False,
                'unit_count': faction.battle_unit_count,
            } for faction in factions],
            'camps': [{
                'camp': camp,
                'name': camp_label,
                'factions': factions.filtered(lambda faction: faction._get_camp_role() == camp).mapped('name'),
                'morale': label(current, f'{camp}_morale'),
                'morale_trend': morale_trend(camp),
                'command_actions': current[f'{camp}_command_action_count'],
                'command_actions_picked': current[f'{camp}_command_action_ids'].mapped('display_name'),
            } for camp, camp_label in CAMPS] if current else [],
            'leaders': [{
                'id': leader.id,
                'name': leader.name,
                'faction': leader.battle_faction_id.name,
                'location': leader.battle_location_id.name,
                'is_faction_leader': leader.is_faction_leader,
                'is_champion': leader.is_champion,
                'wound_state': leader.wound_state,
                'wound_label': label(leader, 'wound_state'),
                'narrative_state': leader.narrative_state,
                'narrative_state_label': label(leader, 'narrative_state'),
            } for leader in leaders],
            'locations': [{
                'id': location.id,
                'name': location.name,
                'status': location.status,
                'status_label': label(location, 'status'),
                'holder': location.held_by_faction_id.name,
                'holder_color': location.held_by_faction_id.color,
                'forces': [
                    {'faction': faction.name, 'count': count, 'menace': menace}
                    for faction, count, menace in location._get_forces()
                ],
                'leaders': leaders.filtered(lambda leader: leader.battle_location_id == location).mapped('name'),
                'effects': [
                    f"{effect.battle_faction_id.name}: {effect.battle_trait_id.name}"
                    for effect in location._get_round_effects(current.round_number)
                ],
                'next_effects': [
                    f"{effect.battle_faction_id.name}: {effect.battle_trait_id.name}"
                    for effect in location._get_round_effects(current.round_number + 1)
                ],
                # battle of the round: waiting to be solved, or its summary once done
                'battle': (
                    {'state': 'done', 'summary': battle_summary(location_results[location])} if location in location_results
                    else {'state': 'pending'} if location.id in pending_ids
                    else False
                ),
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

    @api.model
    def _get_current(self):
        return self.search([], limit=1)

    @api.model
    def _get_tracking_body(self) -> str:
        """ Body of tracking messages of game records (units, leaders): the
        current round, to know when a change happened """
        current = self._get_current()
        return current.display_name if current else ''


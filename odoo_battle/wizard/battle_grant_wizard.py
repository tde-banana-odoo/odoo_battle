from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.fields import Command

from odoo.addons.odoo_battle.const import COMMAND_TYPES

GRANT_TYPES = [
    ('unit', 'Unit Trait'),
    ('location', 'Location Trait'),
    ('location_round', 'Location Effect (Round)'),
    ('command', 'Command Action'),
]
# fields to fill in, per grant type
GRANT_REQUIRED_FIELDS = {
    'unit': ['battle_trait_id', 'battle_unit_ids'],
    'location': ['battle_trait_id', 'battle_location_id'],
    'location_round': ['battle_trait_id', 'battle_location_id', 'battle_faction_id', 'round_number'],
    'command': ['command_type', 'battle_location_id', 'battle_faction_id', 'round_number'],
}


class BattleGrantWizard(models.TransientModel):
    """ Grant a bonus (or a malus) from one place, e.g. to help players: a
    trait to units, a permanent trait to a location, a trait to a faction in
    a location for a round (location effect), or an extra command action to
    the camp of a faction (its command actions count is raised). """
    _name = 'battle.grant.wizard'
    _description = "Grant Bonus"

    def _default_grant_type(self):
        return {'battle.unit': 'unit', 'battle.location': 'location_round'}.get(self.env.context.get('active_model'), 'unit')

    def _default_battle_unit_ids(self):
        if self.env.context.get('active_model') == 'battle.unit':
            return self.env.context.get('active_ids')
        return False

    def _default_battle_location_id(self):
        if self.env.context.get('active_model') == 'battle.location':
            return (self.env.context.get('active_ids') or [False])[0]
        return False

    grant_type = fields.Selection(
        GRANT_TYPES, string="Grant", required=True, default=_default_grant_type,
        help="Unit Trait: added to units. Location Trait: added to the location, for good. Location Effect: a "
             "location trait for a faction during a round. Command Action: an extra action for the faction camp.",
    )
    battle_trait_id = fields.Many2one('battle.trait', string="Trait")
    command_type = fields.Selection(COMMAND_TYPES, string="Command Action")
    command_rule = fields.Char("Rule", compute='_compute_command_rule')
    battle_unit_ids = fields.Many2many('battle.unit', string="Units", default=_default_battle_unit_ids)
    battle_location_id = fields.Many2one('battle.location', string="Location", default=_default_battle_location_id)
    battle_faction_id = fields.Many2one('battle.faction', string="Faction")
    round_number = fields.Integer("Round", default=lambda self: self.env['battle.round']._get_current().round_number)
    note = fields.Char("Note", help="Why it is granted, e.g. a role-play success: logged on units and rounds, kept on command actions.")

    @api.depends('command_type')
    def _compute_command_rule(self):
        for wizard in self:
            wizard.command_rule = wizard.command_type and self.env['battle.command.action']._get_command_rule(wizard.command_type)

    @api.onchange('grant_type')
    def _onchange_grant_type(self):
        """ Traits target units or locations, depending on the grant type """
        target = 'unit' if self.grant_type == 'unit' else 'location'
        if self.battle_trait_id.target != target:
            self.battle_trait_id = False

    def action_grant(self):
        self.ensure_one()
        self._check_grant()
        message = getattr(self, f'_grant_{self.grant_type}')()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'message': message, 'type': 'success', 'next': {'type': 'ir.actions.act_window_close'}},
        }

    def _check_grant(self):
        missing = [self._fields[fname].string for fname in GRANT_REQUIRED_FIELDS[self.grant_type] if not self[fname]]
        if missing:
            raise UserError(_("Fill in: %(fields)s.", fields=', '.join(missing)))
        target = 'unit' if self.grant_type == 'unit' else 'location'
        if self.battle_trait_id and self.grant_type != 'command' and self.battle_trait_id.target != target:
            raise UserError(_("%(trait)s is not a %(target)s trait.", trait=self.battle_trait_id.name, target=target))

    def _get_log_body(self, what: str) -> str:
        """ e.g. 'Granted: Effroi (role-play success)' """
        return _("Granted: %(what)s", what=what) + (f" ({self.note})" if self.note else '')

    def _grant_unit(self) -> str:
        units = self.battle_unit_ids.filtered(lambda unit: self.battle_trait_id not in unit.battle_trait_ids)
        units.write({'battle_trait_ids': [Command.link(self.battle_trait_id.id)]})
        for unit in units:
            unit.message_post(body=self._get_log_body(self.battle_trait_id.name))
        return _("%(trait)s granted to %(count)s units.", trait=self.battle_trait_id.name, count=len(units))

    def _grant_location(self) -> str:
        self.battle_location_id.battle_trait_ids = [Command.link(self.battle_trait_id.id)]
        return _("%(trait)s granted to %(location)s.", trait=self.battle_trait_id.name, location=self.battle_location_id.name)

    def _grant_location_round(self) -> str:
        effect = self.env['battle.location.effect'].create({
            'battle_location_id': self.battle_location_id.id,
            'battle_faction_id': self.battle_faction_id.id,
            'battle_trait_id': self.battle_trait_id.id,
            'round_number': self.round_number,
        })
        if effect.battle_round_id:
            effect.battle_round_id.message_post(body=self._get_log_body(
                f"{self.battle_trait_id.name}, {self.battle_faction_id.name}, {self.battle_location_id.name}",
            ))
        return _(
            "%(trait)s granted to %(faction)s in %(location)s for round %(round)s.",
            trait=self.battle_trait_id.name, faction=self.battle_faction_id.name,
            location=self.battle_location_id.name, round=self.round_number,
        )

    def _grant_command(self) -> str:
        """ An extra command action: the camp command actions count is raised
        accordingly, as it is a bonus on top of leadership rolls """
        battle_round = self.env['battle.round'].search([('round_number', '=', self.round_number)])
        if not battle_round:
            raise UserError(_("Round %(round)s does not exist yet: start it first.", round=self.round_number))
        camp = self.battle_faction_id._get_camp_role()
        if not camp:
            raise UserError(_("%(faction)s fights for no camp: command actions belong to camps.", faction=self.battle_faction_id.name))
        battle_round[f'{camp}_command_action_count'] += 1
        action = self.env['battle.command.action'].create({
            'battle_round_id': battle_round.id,
            'camp': camp,
            'command_type': self.command_type,
            'battle_location_id': self.battle_location_id.id,
            'note': self.note,
        })
        battle_round.message_post(body=self._get_log_body(f"{action.display_name}, {self.battle_faction_id.name}"))
        return _("%(action)s granted to %(faction)s for round %(round)s.", action=action.display_name, faction=self.battle_faction_id.name, round=self.round_number)

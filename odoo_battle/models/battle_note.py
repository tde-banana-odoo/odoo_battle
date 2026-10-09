from odoo import api, fields, models


class BattleNote(models.Model):
    """ DM note for an upcoming round, e.g. 'begin Kiker ritual at Marais',
    optionally about a location or a faction. Shown on the dashboard by
    round (notes without round last), then sequence, until done in a past
    round. """
    _name = 'battle.note'
    _description = "Note"
    _order = 'has_round desc, round_number, sequence, id'

    name = fields.Char("Note", required=True)
    sequence = fields.Integer("Sequence", default=10, help="Order of notes of the same round (or without round).")
    round_number = fields.Integer("Round", help="Round to act in; leave empty for notes without a date.")
    has_round = fields.Boolean("Has Round", compute='_compute_has_round', store=True)  # notes without round come last
    battle_location_id = fields.Many2one('battle.location', string="Location", ondelete='set null')
    battle_faction_id = fields.Many2one('battle.faction', string="Faction", ondelete='set null')
    is_done = fields.Boolean("Done")

    @api.depends('round_number')
    def _compute_has_round(self):
        for note in self:
            note.has_round = bool(note.round_number)

    @api.model
    def _get_dashboard_notes(self, current_round_number: int):
        """ Notes to show: all but the ones done for a past round (or without
        round), done ones of the current or future rounds staying as a
        reminder """
        return self.search([]).filtered(
            lambda note: not note.is_done or (note.round_number and note.round_number >= current_round_number),
        )

    def action_toggle_done(self):
        for note in self:
            note.is_done = not note.is_done

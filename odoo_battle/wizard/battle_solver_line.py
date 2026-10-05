from odoo import api, fields, models, _

from odoo.addons.odoo_battle.const import DAMAGE_PER_WOUND, POSITIONS, SIDE_SELECTION, WOUND_STATES


class BattleSolverLine(models.TransientModel):
    """ Unit of a side in the battle solver: position (frontline or support),
    out of the battle or not, target of its assassin / ambush trait, and the
    consequences of the launched battle on it (tweakable before applying). """
    _name = 'battle.solver.line'
    _description = "Battle Solver Unit"
    _order = 'side, position, id'

    battle_solver_id = fields.Many2one('battle.solver', string="Solver", required=True, index=True, ondelete='cascade')
    side = fields.Selection(SIDE_SELECTION, string="Side", required=True)
    position = fields.Selection(
        POSITIONS, string="Position", default='frontline', required=True,
        help="Support units (second line) count for characteristics and size, but deal no damage and bring no "
             "resistance (unless traits say otherwise), and receive damage only once frontline is down.",
    )
    battle_unit_id = fields.Many2one('battle.unit', string="Unit", required=True, ondelete='cascade')
    is_excluded = fields.Boolean("Out", help="Out of the battle, e.g. scouts avoiding it, or any roleplay reason.")
    target_unit_id = fields.Many2one(
        'battle.unit', string="Target", ondelete='cascade',
        help="Enemy unit targeted by an Assassination (wounded before rolling) or Ambush (out of the battle) trait.",
    )
    can_target = fields.Boolean("Can Target", compute='_compute_can_target')
    battle_status = fields.Char("Status", compute='_compute_battle_status')
    is_out = fields.Boolean("Out of Battle", compute='_compute_battle_status')
    needs_target = fields.Boolean("Needs Target", compute='_compute_battle_status')
    # unit display (statistics are used by the battle_unit_stats widget)
    battle_faction_id = fields.Many2one(related='battle_unit_id.battle_faction_id')
    battle_trait_ids = fields.Many2many(related='battle_unit_id.battle_trait_ids')
    menace = fields.Integer(related='battle_unit_id.menace')
    size = fields.Integer(related='battle_unit_id.size')
    rage = fields.Integer(related='battle_unit_id.rage')
    willpower = fields.Integer(related='battle_unit_id.willpower')
    gnosis = fields.Integer(related='battle_unit_id.gnosis')
    damage = fields.Integer(related='battle_unit_id.damage')
    resistance = fields.Integer(related='battle_unit_id.resistance')
    damage_counter = fields.Integer(related='battle_unit_id.damage_counter')
    wound_state = fields.Selection(related='battle_unit_id.wound_state')
    # consequences of the launched battle, applied on the unit (can be tweaked before)
    damage_received = fields.Integer("Damage Received", help=f"Damage points received, adding a wound every {DAMAGE_PER_WOUND} points.")
    wounds_received = fields.Integer("Wounds Received", help="Direct wounds (assassination, traits).")
    wound_state_after = fields.Selection(WOUND_STATES, string="Wounds After", compute='_compute_wound_state_after')

    @api.depends('battle_unit_id.battle_trait_ids')
    def _compute_can_target(self):
        for line in self:
            line.can_target = any(trait.effect in ('assassin', 'ambush') for trait in line.battle_unit_id.battle_trait_ids)

    @api.depends(
        'is_excluded', 'position', 'target_unit_id', 'battle_unit_id.wound_state',
        'battle_solver_id.initiator_line_ids.target_unit_id', 'battle_solver_id.initiator_line_ids.is_excluded',
        'battle_solver_id.responder_line_ids.target_unit_id', 'battle_solver_id.responder_line_ids.is_excluded',
    )
    def _compute_battle_status(self):
        """ Short status: why the unit is out of the battle, wounds received
        from an assassin before rolling, or a target to choose """
        reasons = {
            'excluded': _("Out"),
            'ambushed': _("Ambushed"),
            'killed': _("Killed"),
        }
        self.update({'battle_status': False, 'is_out': False, 'needs_target': False})
        for solver in self.battle_solver_id:
            for line, (pre_wounds, reason) in solver._get_line_states().items():
                if line not in self:
                    continue
                line.is_out = bool(reason)
                line.needs_target = line.can_target and not line.target_unit_id and not reason
                if reason:
                    line.battle_status = reasons[reason]
                elif pre_wounds:
                    line.battle_status = _("-%(wounds)s wound", wounds=pre_wounds)
                elif line.needs_target:
                    line.battle_status = _("Target?")

    @api.depends(
        'battle_unit_id.damage_counter', 'battle_unit_id.wound_state', 'damage_received', 'wounds_received',
        'battle_solver_id.heal_unit_ids', 'battle_solver_id.mend_unit_ids',
    )
    def _compute_wound_state_after(self):
        for line in self:
            unit = line.battle_unit_id
            heal = unit in line.battle_solver_id.heal_unit_ids
            mend = unit in line.battle_solver_id.mend_unit_ids
            _counter, line.wound_state_after = unit._get_state_after(
                unit.damage_counter, unit.wound_state or '4', line.damage_received, line.wounds_received, heal, mend,
            )

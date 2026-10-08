from odoo import api, models

from odoo.addons.odoo_battle.const import COMMAND_BONUS, COMMAND_BONUS_MAX, COMMAND_RATES, COMMAND_STANCES, DAMAGE_PER_WOUND

# printed in French, for players at the table
OUTCOME_NAMES = {
    -4: "Défaite écrasante", -3: "Défaite nette", -2: "Défaite", -1: "Défaite de justesse", 0: "Égalité",
    1: "Victoire de justesse", 2: "Victoire", 3: "Victoire nette", 4: "Victoire écrasante",
}
COMMAND_NAMES = {
    'location_support': "Soutien de Zone",
    'hold_on': "Tenir",
    'full_attack': "Attaque Totale",
    'retreat': "Retraite",
    'attack_unstoppable': "Attaque Irrésistible (RP)",
}
# traits groups, by sequence (see the data file sections): (first sequence, label)
TRAIT_GROUPS = [
    (0, "Tactique"), (100, "Avant le jet"), (200, "Dégâts"), (300, "Résistance"),
    (400, "Après la bataille"), (500, "Lore"),
    (600, "Lieux"), (650, "Accordés par le MJ"), (700, "Accordés par les résultats"),
]
COMMAND_NOTES = {
    'retreat': "les unités quittent ensuite la zone",
    'attack_unstoppable': "accordée en jeu de rôle",
}


class ReportBattleRulesReference(models.AbstractModel):
    """ Printable game aid (A4, French): bonus rules, outcomes, command
    actions, wounds, then all unit and location traits with their rules. """
    _name = 'report.odoo_battle.report_rules_reference'
    _description = "Rules Reference"

    @api.model
    def _get_report_values(self, docids, data=None):
        traits = self.env['battle.trait'].search([])
        return {
            'outcomes': [
                {
                    'score': outcome.score,
                    'name': OUTCOME_NAMES.get(outcome.score, outcome.name),
                    'attack': f"{outcome.attack_damage_rate} % / {outcome.attack_resistance_rate} %",
                    'defense': f"{outcome.defense_damage_rate} % / {outcome.defense_resistance_rate} %",
                    'granted': ', '.join(sorted(set((outcome.attack_trait_ids | outcome.defense_trait_ids).mapped('name')))),
                    'shift': outcome.location_shift,
                }
                for outcome in self.env['battle.outcome'].search([])
            ],
            'commands': [(COMMAND_NAMES.get(command_type, command_type), self._get_command_rule(command_type)) for command_type in COMMAND_NAMES],
            'damage_per_wound': DAMAGE_PER_WOUND,
            'unit_traits': self._get_trait_groups(traits.filtered(lambda trait: trait.target == 'unit')),
            'location_traits': self._get_trait_groups(traits.filtered(lambda trait: trait.target == 'location')),
        }

    @api.model
    def _get_trait_groups(self, traits) -> list[tuple[str, list]]:
        """ Traits split by group (see TRAIT_GROUPS), as [(label, traits)] """
        groups = []
        for trait in traits.sorted():
            label = next(label for sequence, label in reversed(TRAIT_GROUPS) if trait.sequence >= sequence)
            if not groups or groups[-1][0] != label:
                groups.append((label, []))
            groups[-1][1].append(trait)
        return groups

    @api.model
    def _get_command_rule(self, command_type: str) -> str:
        """ Effect of a command action, in French, from the rules constants """
        parts = []
        if command_type in COMMAND_BONUS:
            rule = f"+{COMMAND_BONUS[command_type]} au bonus par action"
            if command_type in COMMAND_BONUS_MAX:
                rule += f" (+{COMMAND_BONUS_MAX[command_type]} max par camp)"
            parts.append(rule)
        rates = COMMAND_RATES.get(command_type, {})
        for stat, label in (('damage', "dégâts"), ('resistance', "résistance")):
            if rates.get(stat, 100) != 100:
                parts.append(f"{label} ×{rates[stat]} %")
        rule = ', '.join(parts)
        if COMMAND_STANCES.get(command_type) == 'attack':
            rule = f"en attaque : {rule}"
        if command_type in COMMAND_NOTES:
            rule += f" ; {COMMAND_NOTES[command_type]}"
        return rule


class ReportBattleTraitsReference(models.AbstractModel):
    """ Printable traits reference (A4, French), for players: all unit and
    location traits with their rules, without the other rules details. """
    _name = 'report.odoo_battle.report_traits_reference'
    _inherit = ['report.odoo_battle.report_rules_reference']
    _description = "Traits Reference"

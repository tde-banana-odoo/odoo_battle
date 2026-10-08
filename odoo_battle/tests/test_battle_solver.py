from unittest.mock import patch

from odoo.addons.odoo_battle.tests.common import BattleSolverCommon
from odoo.addons.odoo_battle.wizard.battle_solver import BattleSolver
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import users


class TestBattleSolver(BattleSolverCommon):

    @users('battle_admin')
    def test_battle(self):
        """ Launching the battle rolls dice, computes outcome and consequences
        without applying them (can be launched again); applying them updates
        units and logs the result """
        solver = self._new_solver_form(self.location_ww).save()
        with patch.object(BattleSolver, '_roll_dice', return_value=[0, 0, 0]):
            action = solver.action_launch()
        self.assertRecordValues(solver, [{
            'mode': 'launched',
            'dice_roll': '+0 +0 +0',
            'result_score': 1,
            'battle_outcome_id': self.env.ref('odoo_battle.battle_outcome_narrow_victory').id,
            'battle_result_id': False,
        }])
        # message explains damage: outcome rates (narrow victory) and traits (fureur)
        self.assertEqual(solver.result_message.splitlines(), [
            'Roll +0 +0 +0 (+0), bonus +1, score +1. Damage: 10 to Test Bad, 1 to Test Good.',
            'Damage to Test Bad: 10 = Test Good damage 9 × 100% (Narrow Victory, Attack) = 9, +6 Fureur → 15, '
            'minus Test Bad resistance 4 × 125% (Narrow Defeat, Defend) = 5.',
            'Damage to Test Good: 1 = Test Bad damage 8 × 50% (Narrow Defeat, Defend) = 4, '
            'minus Test Good resistance 6 × 50% (Narrow Victory, Attack) = 3.',
        ])
        self.assertEqual((action['res_id'], action['target']), (solver.id, 'new'), 'Wizard stays open to display result')
        self.assertEqual(set(self.ww_defense.mapped('wound_state')), {'4'}, 'Not applied yet')

        # capped score
        with patch.object(BattleSolver, '_roll_dice', return_value=[1, 1, 1]):
            solver.action_launch()
        self.assertRecordValues(solver, [{'result_score': 4, 'battle_outcome_id': self.env.ref('odoo_battle.battle_outcome_major_victory').id}])

        # real roll: bonus +1, score from -2 to +4
        solver.action_launch()
        self.assertIn(solver.battle_outcome_id.score, range(-2, 5))
        self.assertIn(solver.battle_outcome_id.name, solver.result_summary)

        solver.action_apply()
        self.assertEqual(solver.mode, 'done')
        self.assertEqual(solver.battle_result_id.result_score, solver.result_score)
        with self.assertRaises(UserError):
            solver.action_launch()

        solver = self._new_solver_form(self.location_ww).save()
        solver.action_simulate()
        self.assertRecordValues(solver, [{'mode': 'simulate', 'battle_outcome_id': False, 'dice_roll': False}])
        with self.assertRaises(UserError, msg='Already solved: cancel it first'):
            solver.action_launch()
        with self.assertRaises(UserError, msg='Launch first'):
            solver.action_apply()

    @users('battle_admin')
    def test_battle_heal_mend(self):
        """ Heal (one wound less) and mend (damage counter reset) are prefilled
        when launching from Heal Self / Mend Self traits (one unit per value
        point, most wounded / damaged first, after the battle damage), and
        can be changed (e.g. role-play) before applying """
        heal, mend = self.env['battle.trait'].sudo().create([
            {'name': 'Test Heal', 'effect': 'heal_self'},
            {'name': 'Test Mend', 'effect': 'mend_self'},
        ])
        self.ww_defense[0].sudo().battle_trait_ids += heal
        self.ww_henchmen[1].sudo().battle_trait_ids += mend
        solver = self._new_solver_form(self.location_ww).save()
        with patch.object(BattleSolver, '_roll_dice', return_value=[1, 1, 0]):
            solver.action_launch()
        # clear-cut victory: (9 x 150% + fureur 6) - (4 x 100%) = 15 damage, spread by size (henchmen: size 2),
        # counters starting at 1: defense werewolves take 3 (wounded, counter 1), henchman 1 takes 5 (badly wounded,
        # counter 0), henchman 2 takes 4 (wounded, counter 2): henchman 1 prefilled to heal (most wounded), henchman 2
        # to mend (most damaged)
        defense_1, defense_2 = (solver.responder_line_ids.filtered(lambda line, unit=unit: line.battle_unit_id == unit) for unit in self.ww_defense)
        self.assertEqual((solver.heal_unit_ids, solver.mend_unit_ids), (self.ww_henchmen[0], self.ww_henchmen[1]))
        self.assertEqual((defense_1.wound_state_after, defense_2.wound_state_after), ('3', '3'))
        self.assertEqual(solver._get_heal_mend_reminders(), ['Test Heal: 1 heals (Responders)', 'Test Mend: 1 mends (Responders)'])
        self.assertIn('Heal / Mend', solver.result_summary)

        # role-play: heal the other defense werewolf instead, also mend henchman 2
        solver.heal_unit_ids = self.ww_defense[1]
        solver.mend_unit_ids += self.ww_henchmen[1]
        solver.action_apply()
        self.assertEqual(
            [(unit.wound_state, unit.damage_counter) for unit in self.ww_defense + self.ww_henchmen],
            [('3', 1), ('4', 1), ('2', 0), ('3', 0)],
        )
        result_line = solver.battle_result_id.battle_result_line_ids.filtered(lambda line: line.battle_unit_id == self.ww_defense[1])
        self.assertEqual((result_line.damage, result_line.wounds), (3, 0), 'Wound received then healed')

    @users('battle_admin')
    def test_battle_lore_reminders(self):
        """ Lore traits applying in the launched battle (stance, position,
        result) are listed to resolve manually: units ones, location ones
        (once if applying to both sides) """
        lore_win, lore_lose, lore_location, lore_location_responders = self.env['battle.trait'].sudo().create([
            {'name': 'Test Lore Win', 'condition': 'win'},
            {'name': 'Test Lore Lose', 'condition': 'lose'},
            {'name': 'Test Lore Location', 'target': 'location'},
            {'name': 'Test Lore Responders', 'target': 'location', 'side': 'responder', 'stance': 'defense'},
        ])
        self.ww_offense[0].sudo().battle_trait_ids += lore_win
        self.ww_offense[1].sudo().battle_trait_ids += lore_lose  # initiators win: not listed
        self.ww_defense[0].sudo().battle_trait_ids += self.trait_fanatic
        self.location_ww.sudo().battle_trait_ids = lore_location + lore_location_responders
        solver = self._new_solver_form(self.location_ww).save()
        with patch.object(BattleSolver, '_roll_dice', return_value=[0, 0, 0]):
            solver.action_launch()  # initiators win
        self.assertEqual(solver._get_lore_reminders(), [
            'Test Lore Win (WW Offense 1)',
            f'{self.trait_fanatic.name} (WW Defense 1)',
            'Test Lore Location (Werewolves War)',
            'Test Lore Responders (Werewolves War, Responders)',
        ])
        self.assertIn('To resolve', solver.result_summary)

    @users('battle_admin')
    def test_battle_apply(self):
        """ Launched consequences are displayed per unit (damage, direct
        wounds, state after) and for the location, can be tweaked, then are
        applied as displayed """
        solver = self._new_solver_form(self.location_ww).save()
        assassin = solver.initiator_line_ids.filtered(lambda line: line.battle_unit_id == self.ww_offense[0])
        assassin.target_unit_id = self.ww_henchmen[0]
        with patch.object(BattleSolver, '_roll_dice', return_value=[1, 1, 1]):
            solver.action_launch()
        # major victory: (9 x 200% + fureur 6) - (4 x 100%, routed defense) = 20 damage to responders, spread by size
        # (henchmen: size 2): 4 to each defense werewolf, 6 to each henchman (counters start at 1); henchman 1 also
        # assassinated
        lines = solver.responder_line_ids.sorted(lambda line: line.battle_unit_id.id)
        self.assertEqual(
            [(line.battle_unit_id, line.damage_received, line.wounds_received, line.wound_state_after) for line in lines],
            [
                (self.ww_defense[0], 4, 0, '3'),
                (self.ww_defense[1], 4, 0, '3'),
                (self.ww_henchmen[0], 6, 1, '1'),
                (self.ww_henchmen[1], 6, 0, '2'),
            ],
        )
        self.assertRecordValues(solver, [{
            'location_status_after': 'held', 'held_by_faction_after_id': self.faction_good.id,
            'initiator_granted_trait_ids': self.trait_breakthrough.ids, 'responder_granted_trait_ids': self.trait_wavering.ids,
        }])
        self.assertEqual(self.location_ww.status, 'free', 'Not applied yet')

        # GM tweaks: henchman 2 spared, contested location, no wavering; changing the battle itself outdates it
        lines[3].damage_received = 0
        self.assertFalse(solver.is_outdated)
        solver.responder_stance = 'attack'
        self.assertTrue(solver.is_outdated)
        with self.assertRaises(UserError):
            solver.action_apply()
        solver.responder_stance = 'defense'
        solver.write({'location_status_after': 'contested', 'responder_granted_trait_ids': [Command.clear()]})
        solver.action_apply()
        self.assertEqual(self.ww_defense.mapped('wound_state') + self.ww_henchmen.mapped('wound_state'), ['3', '3', '1', '4'])
        self.assertRecordValues(self.location_ww, [{'status': 'contested', 'held_by_faction_id': self.faction_good.id}])
        self.assertEqual(solver.battle_result_id.battle_location_effect_ids.battle_trait_id, self.trait_breakthrough)
        self.assertRecordValues(solver.battle_result_id.battle_result_line_ids.filtered(lambda line: line.side == 'responder'), [
            {'battle_unit_id': unit.id, 'damage': damage, 'wounds': wounds}
            for unit, damage, wounds in [(self.ww_defense[0], 4, 1), (self.ww_defense[1], 4, 1), (self.ww_henchmen[0], 6, 3), (self.ww_henchmen[1], 0, 0)]
        ])

    @users('battle_admin')
    def test_battle_damage(self):
        """ Damage: frontline damage of a side times its outcome rate, then
        traits, minus resistance of the other side (frontline resistance times
        its outcome rate, then traits), at least 0. Responders read the
        opposite outcome. Attacking exposes (resistance 50% unless winning
        well), defending protects (damage 50% unless winning, resistance 150%
        or more, falling to 100% with the defeat). """
        solver = self._new_solver_form(self.location_ww).save()
        outcomes = self.env['battle.outcome']._get_by_score()
        # initiators (3 offense, attacking): damage 3 x3, resistance 2 x3, fureur;
        # responders (2 defense, 2 henchmen): damage 3 x2 + 1 x2, resistance 2 x2, contre-attaque
        for responder_stance, score, side_damage, expected in [
            ('defense', 0, (9, 8 // 2), (9 - 4 * 3 // 2, 4 - 6 // 2)),  # tie: defense deals 50%, resists 150%; attack resists 50%
            ('defense', 1, (9 + 6, 4), (15 - 5, 4 - 3)),  # narrow victory: fureur (+2) x3; defeated defense resists 125%
            ('defense', 2, (9 * 3 // 2 + 6, 4), (19 - 5, 4 - 6)),  # victory: attack deals 150%, resists 100%; defense resists 125%
            ('defense', -1, (9, 8 + 4), (9 - 6, 12 - 3)),  # narrow defeat: winning defense deals 100%, contre-attaque (+2) x2
            ('defense', -2, (9, 8 + 4), (9 - 4 * 2, 12 - 3)),  # defeat: winning defense resists 200%
            ('defense', -4, (9, 8 * 2 + 4), (9 - 4 * 5 // 2, 20 - 3)),  # major defeat: winning defense deals 200%, resists 250%
            ('attack', 0, (9, 8), (9 - 4 // 2, 8 - 3)),  # attacking responders deal full damage, resist 50%
            ('attack', -1, (9, 8), (9 - 2, 8 - 3)),  # contre-attaque requires defending
            ('attack', -2, (9, 8 * 3 // 2), (9 - 4, 12 - 3)),  # victory of attacking responders: deal 150%, resist 100%
        ]:
            with self.subTest(responder_stance=responder_stance, score=score):
                solver.responder_stance = responder_stance
                outcome = outcomes[score]
                self.assertEqual((solver._get_side_damage('initiator', outcome), solver._get_side_damage('responder', outcome)), side_damage)
                self.assertEqual(solver._get_damage(outcome), (max(expected[0], 0), max(expected[1], 0)))

        solver.responder_stance = 'defense'
        with patch.object(BattleSolver, '_roll_dice', return_value=[0, 0, 0]):
            solver.action_launch()
        self.assertRecordValues(solver, [{'result_score': 1, 'damage_to_responders': 10, 'damage_to_initiators': 1}])
        self.assertIn('Damage: 10 to Test Bad, 1 to Test Good.', solver.result_message)

    @users('battle_admin')
    def test_battle_damage_rates(self):
        """ Rate traits change frontline damage or resistance by a percentage,
        multiplied with outcome rates; per holder changes add up """
        obstacles, shield_wall = self.env['battle.trait'].sudo().create([
            {'name': 'Test Obstacles', 'target': 'location', 'stance': 'attack', 'effect': 'damage_rate', 'value': -25},
            {'name': 'Test Shield Wall', 'stance': 'defense', 'position': 'frontline', 'effect': 'resistance_rate', 'value': 25},
        ])
        self.location_ww.sudo().battle_trait_ids = obstacles
        self.ww_defense.sudo().battle_trait_ids += shield_wall
        solver = self._new_solver_form(self.location_ww).save()
        tie = self.env['battle.outcome']._get_by_score()[0]
        # attacking initiators slowed down; defending responders: 2 shield walls (+50%), not slowed down
        for side, stat, expected in [
            ('initiator', 'damage', '9 × 100% (Tied, Attack) × 75% (Test Obstacles) = 6'),
            ('responder', 'resistance', '4 × 150% (Tied, Defend) × 150% (Test Shield Wall) = 9'),
            ('responder', 'damage', '8 × 50% (Tied, Defend) = 4'),
        ]:
            with self.subTest(side=side, stat=stat):
                self.assertEqual(solver._format_stat_breakdown(solver._get_side_stat_breakdown(side, tie, stat)), expected)
        self.assertEqual(solver._get_damage(tie), (0, 4 - 3))

    @users('battle_admin')
    def test_battle_size_rate(self):
        """ Size rate traits change the side size (rounded down) for the size
        bonus, e.g. obstacles slowing attackers down """
        obstacles = self.env['battle.trait'].sudo().create({
            'name': 'Test Obstacles', 'target': 'location', 'stance': 'attack', 'effect': 'size_rate', 'value': -25,
        })
        self.location_ww.sudo().battle_trait_ids = obstacles
        solver = self._new_solver_form(self.location_ww).save()
        size_line = next(line for line in solver._get_bonus_lines() if line['name'] == 'Size')
        # attacking initiators: 3 x 75% = 2; defending responders not slowed down: 6
        self.assertEqual(size_line['detail'], '2 (Test Obstacles -25%) vs 6')
        self.assertEqual((size_line['initiator'], size_line['responder']), (0, 1))
        solver.responder_stance = 'attack'
        size_line = next(line for line in solver._get_bonus_lines() if line['name'] == 'Size')
        self.assertEqual(size_line['detail'], '2 (Test Obstacles -25%) vs 4 (Test Obstacles -25%)')

    @users('battle_admin')
    def test_battle_wounds_and_dm_bonus(self):
        """ Wounded units have maluses: badly wounded -1 characteristic,
        critical -1 characteristic, damage and resistance (never below 0).
        The DM may give a side a bonus. """
        self.ww_offense[0].sudo().wound_state = '2'
        self.ww_offense[1].sudo().wound_state = '1'
        self.ww_henchmen[0].sudo().wound_state = '1'  # damage 1, resistance 0: no resistance malus
        solver = self._new_solver_form(self.location_ww).save()
        solver.responder_dm_bonus = '1.5'
        # averages weighted by menace: Rage (27 - 3 - 3) / 9 = 2.33 rounded to 2.5; Willpower (4 - 1) / 8 = 0.38
        # rounded to 0.5, as without wounds (henchmen weigh little)
        self.assertIn('Rage 2.5 (wounds -0.5) vs Willpower 0.5', solver.bonus_summary)
        self.assertIn('DM Bonus', solver.bonus_summary)
        self.assertEqual(self._get_bonus(solver), (2, 2.5, 0), 'Characteristics +2 (capped), size and DM bonus +2.5: -0.5 dropped')

        tie = self.env['battle.outcome']._get_by_score()[0]
        for side, stat, expected in [
            ('initiator', 'damage', '8 (wounds -1) × 100% (Tied, Attack) = 8'),
            ('initiator', 'resistance', '5 (wounds -1) × 50% (Tied, Attack) = 2'),
            ('responder', 'damage', '7 (wounds -1) × 50% (Tied, Defend) = 3'),
            ('responder', 'resistance', '4 × 150% (Tied, Defend) = 6'),
        ]:
            with self.subTest(side=side, stat=stat):
                self.assertEqual(solver._format_stat_breakdown(solver._get_side_stat_breakdown(side, tie, stat)), expected)

    @users('battle_admin')
    def test_battle_dice(self):
        """ Dice are entered from the table (with a score preview) or rolled,
        then used to solve the battle """
        solver = self._new_solver_form(self.location_ww).save()
        for dice, preview in [
            ('-1 -1 0', 'Score -1: Narrow Defeat'),
            ('+1, +1, +1', 'Score +4: Major Victory'),
            ('-1 2 0', "Dice should be 3 values among -1, +0, +1, e.g. '-1 0 +1'."),
            ('-1 0', "Dice should be 3 values among -1, +0, +1, e.g. '-1 0 +1'."),
        ]:
            with self.subTest(dice=dice):
                solver.dice_input = dice
                self.assertEqual(solver.dice_input_preview, preview)
        with patch.object(BattleSolver, '_roll_dice', return_value=[0, -1, 1]):
            solver.action_roll()
        self.assertEqual(solver.dice_input, '+0 -1 +1')

        solver.dice_input = '-1 -1 0'
        solver.action_launch()
        self.assertRecordValues(solver, [{'dice_roll': '-1 -1 +0', 'result_score': -1}])

        # forced reroll: initiators reroll their highest die, applied when rolling
        forced = self.env['battle.trait'].sudo().create({'name': 'Test Forced Reroll', 'target': 'location', 'effect': 'forced_reroll'})
        self.env['battle.location.effect'].sudo().create({
            'battle_location_id': self.location_ww.id, 'battle_faction_id': self.faction_good.id,
            'round_number': self.battle_round.round_number, 'battle_trait_id': forced.id,
        })
        solver = self._new_solver_form(self.location_ww).save()
        self.assertEqual((solver.initiator_forced_rerolls, solver.responder_forced_rerolls), (1, 0))
        with patch.object(BattleSolver, '_roll_dice', side_effect=[[1, 0, -1], [-1]]):
            solver.action_roll()
        self.assertEqual(solver.dice_input, '-1 +0 -1')

    @users('battle_admin')
    def test_battle_support(self):
        """ Support units count for characteristics and size, but deal no
        damage and bring no resistance, unless Appui / Couverture, added
        after outcome rates """
        support_fire, barrage_fire = self.trait_support_fire, self.trait_barrage_fire
        solver = self._new_solver_form(self.location_vw).save()
        self._set_lines(solver, 'initiator', frontline=self.vw_vampires, support=self.vw_ghouls)
        tie = self.env['battle.outcome'].search([('score', '=', 0)])
        # Rage (2 x 3 + 2 x 3 + 0 + 0) / 8 (weighted by menace) = 1.5 vs Willpower 1 (+0.5), Size 4 vs 2 (+1),
        # Commandement (+1): +2.5, half point dropped
        self.assertEqual(self._get_bonus(solver), (2.5, 0, 2), 'Support counts for characteristics and size')
        # initiators: frontline vampires (damage 2, resistance 3), support ghouls (damage 1);
        # tie: attack 100% / 50%, defense 50% / 150%
        for stance, traits, damage, resistance in [
            ('attack', [], 2 + 2, (3 + 3) // 2),
            ('attack', support_fire.ids, 2 + 2 + 1 + 1, (3 + 3) // 2),
            ('defense', support_fire.ids, (2 + 2) // 2, (3 + 3) * 3 // 2),
            ('defense', barrage_fire.ids, (2 + 2) // 2, (3 + 3) * 3 // 2 + 1 + 1),
        ]:
            with self.subTest(stance=stance, traits=traits):
                self.vw_ghouls.sudo().battle_trait_ids = traits
                solver.invalidate_recordset()
                solver.initiator_stance = stance
                self.assertEqual(solver._get_side_damage('initiator', tie), damage)
                self.assertEqual(solver._get_side_resistance('initiator', tie), resistance)

    @users('battle_admin')
    def test_battle_damage_distribution(self):
        """ Damage is spread over fighting frontline units, each taking as
        many points as its size per turn, support units being hit only once
        frontline is out of combat """
        offense = self.ww_offense
        solver = self._new_solver_form(self.location_ww).save()
        self._set_lines(solver, 'initiator', frontline=offense[:2], support=offense[2])
        frontline_1, frontline_2, support = solver.initiator_line_ids.sorted(lambda line: (line.position, line.battle_unit_id.id))
        for state, damage, expected in [
            ('4', 5, {frontline_1: 3, frontline_2: 2}),
            ('1', 5, {frontline_1: 2, frontline_2: 2, support: 1}),  # critical, 1 damage: 2 more put out of combat
        ]:
            with self.subTest(state=state, damage=damage):
                offense[:2].sudo().wound_state = state
                lines = solver.initiator_line_ids
                self.assertEqual(solver._get_damage_distribution(lines, damage, solver._get_lines_state(lines)), expected)

        # more people, more wounds: henchmen (size 2) take twice the share of defense werewolves (size 1)
        lines = solver.responder_line_ids.sorted(lambda line: line.battle_unit_id.id)
        self.assertEqual(
            solver._get_damage_distribution(lines, 6, solver._get_lines_state(lines)),
            dict(zip(lines, [1, 1, 2, 2], strict=True)),
        )

    @users('battle_admin')
    def test_battle_location(self):
        """ Side outcomes grant location effects to side factions for the next
        round (depending on stance), attacking winners shift the location;
        cancelling the result reverts both """
        next_round = self.battle_round.round_number + 1
        # major victory of attacking initiators: location taken, breakthrough; major defeat of responders: wavering
        solver = self._battle(self.location_ww, roll=(1, 1, 1))
        result = solver.battle_result_id
        self.assertRecordValues(self.location_ww, [{'status': 'held', 'held_by_faction_id': self.faction_good.id}])
        self.assertEqual(
            {(effect.battle_faction_id, effect.battle_trait_id, effect.round_number) for effect in result.battle_location_effect_ids},
            {(self.faction_good, self.trait_breakthrough, next_round), (self.faction_bad, self.trait_wavering, next_round)},
        )
        self.assertEqual(self.location_ww.battle_location_effect_ids, result.battle_location_effect_ids)
        for expected in ('Held', self.trait_breakthrough.name, self.trait_wavering.name):
            self.assertIn(expected, str(solver.result_summary))
        solver = self._new_solver_form(self.location_ww).save()
        self.assertEqual(
            (solver.initiator_faction_ids, solver.responder_faction_ids), (self.faction_good, self.faction_bad),
            'Replacing a battle keeps its sides, although the location shifted',
        )

        result.action_cancel()
        self.assertRecordValues(self.location_ww, [{'status': 'free', 'held_by_faction_id': False}])
        self.assertFalse(self.location_ww.battle_location_effect_ids)

        # victory of defending responders: no shift, no effect
        result = self._battle(self.location_ww, roll=(-1, -1, -1)).battle_result_id
        self.assertEqual((result.result_score, self.location_ww.status), (-2, 'free'))
        self.assertFalse(result.battle_location_effect_ids)

    @users('battle_admin')
    def test_bonus(self):
        """ Werewolves War: Rage 3 vs Willpower 0.5 (averages weighted by
        menace, +2 at most), Size 3 vs 6 (+1 to responders), morale 4 vs 3. Rage when
        attacking, Willpower when defending, Gnosis in Umbra; fortifications
        only help defending responders; low morale is a malus; advantages
        (half points) left over are dropped """
        solver = self._new_solver_form(self.location_ww).save()
        for umbra, fortified, morales, stances, expected, detail in [
            (False, False, ('4', '3'), ('attack', 'defense'), (2, 1, 1), 'Rage 3 vs Willpower 0.5'),
            (False, True, ('4', '3'), ('attack', 'defense'), (2, 2, 0), 'Rage 3 vs Willpower 0.5'),
            (False, True, ('4', '2'), ('attack', 'defense'), (2, 1, 1), 'Rage 3 vs Willpower 0.5'),
            (False, True, ('1', '2'), ('attack', 'defense'), (1, 1, 0), 'Rage 3 vs Willpower 0.5'),
            (False, True, ('4', '3'), ('attack', 'attack'), (1.5, 1, 0), 'Rage 3 vs Rage 1.5'),  # half point dropped
            (False, True, ('4', '3'), ('defense', 'defense'), (0.5, 2, -1), 'Willpower 1 vs Willpower 0.5'),
            (True, False, ('4', '3'), ('attack', 'defense'), (0, 1, -1), 'Gnosis 1 vs Gnosis 1'),
            (True, False, ('4', '3'), ('attack', 'attack'), (0, 1, -1), 'Gnosis 1 vs Gnosis 1'),
        ]:
            with self.subTest(umbra=umbra, fortified=fortified, morales=morales, stances=stances):
                self.location_ww.sudo().write({
                    'is_umbra': umbra,
                    'battle_trait_ids': [Command.set(self.trait_fortified.ids if fortified else [])],
                })
                self.battle_round.sudo().write({'aggressor_morale': morales[0], 'defender_morale': morales[1]})
                solver.write({'initiator_stance': stances[0], 'responder_stance': stances[1]})
                self.assertEqual(self._get_bonus(solver), expected)
                self.assertIn(detail, solver.bonus_summary)

    @users('battle_admin')
    def test_command_actions(self):
        """ Command actions picked by a camp in the location for the round:
        Location Support gives +1 (per action), Hold On / Full Attack change
        frontline damage and resistance rates (on top of outcome ones). They
        apply to the side of the camp, initiating or responding. Unstoppable
        Attack only applies for attacking sides. """
        location_ww, location_vw = self.location_ww, self.location_vw
        self.battle_round.sudo().write({
            'aggressor_command_action_count': 3,
            'aggressor_command_action_ids': [
                Command.create({'camp': 'aggressor', 'command_type': 'location_support', 'battle_location_id': location_ww.id}),
                Command.create({'camp': 'aggressor', 'command_type': 'full_attack', 'battle_location_id': location_ww.id}),
                Command.create({'camp': 'aggressor', 'command_type': 'attack_unstoppable', 'battle_location_id': location_ww.id}),
            ],
            'defender_command_action_count': 3,
            'defender_command_action_ids': [
                Command.create({'camp': 'defender', 'command_type': 'hold_on', 'battle_location_id': location_ww.id}),
                Command.create({'camp': 'defender', 'command_type': 'location_support', 'battle_location_id': location_vw.id}),
                Command.create({'camp': 'defender', 'command_type': 'attack_unstoppable', 'battle_location_id': location_ww.id}),  # defending: no effect
            ],
        })
        solver = self._new_solver_form(self.location_ww).save()
        lines = {line['name']: (line['initiator'], line['responder']) for line in solver._get_bonus_lines()}
        self.assertEqual((lines['Location Support'], lines['Full Attack'], lines['Hold On']), ((1, 0), (0, 0), (0, 0)))
        self.assertEqual(self._get_bonus(solver), (2 + 1, 1, 1 + 1))

        # tie: initiators attack (100% / 50%) in full and unstoppable attack, responders defend (50% / 150%) holding on
        tie = self.env['battle.outcome']._get_by_score()[0]
        self.assertEqual(
            solver._format_stat_breakdown(solver._get_side_stat_breakdown('initiator', tie, 'damage')),
            '9 × 100% (Tied, Attack) × 125% (Unstoppable Attack (RP)) × 150% (Full Attack) = 16',
        )
        self.assertEqual(
            solver._format_stat_breakdown(solver._get_side_stat_breakdown('responder', tie, 'resistance')),
            '4 × 150% (Tied, Defend) × 150% (Hold On) = 9',
        )
        self.assertEqual(
            (solver._get_side_damage('initiator', tie), solver._get_side_resistance('initiator', tie)),
            (9 * 100 * 125 * 150 // 1000000, 6 * 50 * 75 // 10000),
        )
        self.assertEqual(
            (solver._get_side_damage('responder', tie), solver._get_side_resistance('responder', tie)),
            (8 * 50 * 75 // 10000, 4 * 150 * 150 // 10000),
        )

        # held by aggressors: defenders initiate, with their support
        solver = self._new_solver_form(location_vw).save()
        lines = {line['name']: (line['initiator'], line['responder']) for line in solver._get_bonus_lines()}
        self.assertEqual(lines['Location Support'], (1, 0))

        # location support adds up to +2 per side; retreat: no damage dealt, doubled resistance
        self.battle_round.sudo().write({
            'defender_command_action_count': 6,
            'defender_command_action_ids': [
                Command.create({'camp': 'defender', 'command_type': 'location_support', 'battle_location_id': location_vw.id})
                for _index in range(2)
            ] + [Command.create({'camp': 'defender', 'command_type': 'retreat', 'battle_location_id': location_vw.id})],
        })
        solver = self._new_solver_form(location_vw).save()
        lines = {line['name']: (line['initiator'], line['responder']) for line in solver._get_bonus_lines()}
        self.assertEqual(lines['Location Support'], (2, 0), '3 actions: +2 at most')
        self.assertEqual(solver._format_command_rates('retreat'), 'Damage -100%, Resistance +100%')
        self.assertEqual(solver._get_side_damage('initiator', tie), 0, 'Retreating: no damage dealt')

    @users('battle_admin')
    def test_bonus_traits(self):
        """ Battle bonus traits: unique ones (commandement) count once per
        side; location effects apply to their faction for their round,
        depending on stance; diversion removes its value from the enemy
        characteristic (once per side), tactique gives dice rerolls """
        Effect = self.env['battle.location.effect'].sudo()
        round_number = self.battle_round.round_number
        Effect.create([{'battle_location_id': self.location_vw.id, **values} for values in [
            {'battle_faction_id': self.faction_bad.id, 'battle_trait_id': self.trait_breakthrough.id, 'round_number': round_number},
            {'battle_faction_id': self.faction_good.id, 'battle_trait_id': self.trait_heroic_defense.id, 'round_number': round_number},
            {'battle_faction_id': self.faction_good.id, 'battle_trait_id': self.trait_breakthrough.id, 'round_number': round_number - 1},
        ]])
        solver = self._new_solver_form(self.location_vw).save()
        lines = {line['name']: (line['initiator'], line['responder']) for line in solver._get_bonus_lines()}
        breakthrough, heroic_defense = self.trait_breakthrough.name, self.trait_heroic_defense.name
        self.assertEqual(lines['Commandement'], (1, 0), 'Commandement: 2 old vampires, once')
        self.assertEqual((lines[breakthrough], lines[heroic_defense]), ((1, 0), (0, 1)), 'Previous round effect ignored')
        self.assertEqual(self._get_bonus(solver), (3.5, 1, 2))

        # effects depend on stance: attacking responders lose heroic defense, and have no breakthrough (not theirs)
        solver.responder_stance = 'attack'
        lines = {line['name']: (line['initiator'], line['responder']) for line in solver._get_bonus_lines()}
        self.assertEqual(lines[breakthrough], (1, 0))
        self.assertNotIn(heroic_defense, lines)

        # diversion: -2 spread over the responders size (2): -1 to their willpower average, once per side (both vampires)
        self.vw_vampires.sudo().battle_trait_ids = [Command.link(self.trait_diversion.id)]
        solver.responder_stance = 'defense'
        solver.invalidate_recordset()
        self.assertIn('Rage 1.5 vs Willpower 0 (diversion -1)', solver.bonus_summary)
        lines = {line['name']: (line['initiator'], line['responder']) for line in solver._get_bonus_lines()}
        self.assertEqual(lines['Characteristics'], (1.5, 0))
        self.assertEqual((solver.initiator_rerolls, solver.responder_rerolls), (0, 0))

        # advantage (e.g. Retranché): half a bonus point
        entrenched = self.env.ref('odoo_battle.battle_trait_entrenched')
        self.location_vw.sudo().battle_trait_ids = entrenched
        solver.invalidate_recordset()
        lines = {line['name']: (line['initiator'], line['responder']) for line in solver._get_bonus_lines()}
        self.assertEqual(lines[entrenched.name], (0, 0.5), 'Holders defending: +0.5')

        # negative advantage, e.g. Moral Vacillant (after a major defeat): -0.5
        self.env['battle.location.effect'].sudo().create({
            'battle_location_id': self.location_vw.id, 'battle_faction_id': self.faction_good.id,
            'round_number': round_number, 'battle_trait_id': self.trait_wavering.id,
        })
        solver.invalidate_recordset()
        lines = {line['name']: (line['initiator'], line['responder']) for line in solver._get_bonus_lines()}
        self.assertEqual(lines[self.trait_wavering.name], (0, -0.5))

        # tactique: one reroll per holder (2 defense werewolves)
        solver = self._new_solver_form(self.location_ww).save()
        self.assertEqual((solver.initiator_rerolls, solver.responder_rerolls), (0, 2))

    @users('battle_admin')
    def test_errors(self):
        """ Battles require complete and distinct sides, support not larger
        than frontline, a location on the battlefield, and a round to be logged
        (not simulations) """
        defense, henchman, offense = self.ww_defense[0], self.ww_henchmen[0], self.ww_offense[0]
        solver = self._new_solver_form(self.location_ww).save()
        for factions, frontline, support in [
            (self.faction_bad, defense + offense, None),  # unit on both sides
            (self.faction_bad, None, None),  # missing units
            (self.env['battle.faction'], defense, None),  # missing factions
            (self.faction_good + self.faction_bad, defense, None),  # faction on both sides
            (self.faction_bad, defense, henchman),  # support larger than frontline (2 vs 1)
        ]:
            with self.subTest(factions=factions.mapped('name'), frontline=frontline and frontline.mapped('name'), support=support and support.mapped('name')):
                solver.responder_faction_ids = factions
                self._set_lines(solver, 'responder', frontline, support)
                with self.assertRaises(UserError):
                    solver.action_simulate()
                with self.assertRaises(UserError):
                    solver.action_launch()
                self.assertFalse(solver.mode)

        solver = self._new_solver_form(self.location_ww).save()
        solver.battle_round_id = False
        solver.action_simulate()
        with self.assertRaises(UserError):
            solver.action_launch()

        self.location_ww.sudo().is_external = True
        with self.assertRaises(UserError):
            self._new_solver_form(self.location_ww).save().action_simulate()

    @users('battle_admin')
    def test_location_summary(self):
        """ Location summary displays status, holder, Umbra, twin; then traits
        with their rules, and effects applying this round (not the ones of
        other rounds) """
        self.location_ww.sudo().write({
            'battle_trait_ids': self.trait_fortified.ids,
            'is_umbra': True,
            'linked_location_id': self.location_hw.id,
            'held_by_faction_id': self.faction_bad.id,
            'status': 'held',
            'battle_location_effect_ids': [
                Command.create({'battle_faction_id': self.faction_good.id, 'battle_trait_id': self.trait_breakthrough.id, 'round_number': self.battle_round.round_number}),
                Command.create({'battle_faction_id': self.faction_bad.id, 'battle_trait_id': self.trait_heroic_defense.id, 'round_number': self.battle_round.round_number + 1}),
            ],
        })
        solver = self._new_solver_form(self.location_ww).save()
        summary, traits = str(solver.battle_location_summary), str(solver.battle_location_traits)
        for expected in ('Held', 'Test Bad', 'Umbra', 'Human Wars'):
            self.assertIn(expected, summary)
        for expected in (self.trait_fortified.name, self.trait_fortified.description, f'Test Good: {self.trait_breakthrough.name}'):
            self.assertIn(expected, traits)
        self.assertNotIn(self.trait_heroic_defense.name, traits, 'Next round effect')

    @users('battle_admin')
    def test_sides(self):
        """ Free location: the defender camp responds, other factions
        initiate. Initiators attack, responders defend. Sides can be swapped
        and are reloaded when changing location (held: holders respond). """
        solver_form = self._new_solver_form(self.location_ww)
        self.assertEqual(solver_form.initiator_faction_ids.ids, self.faction_good.ids)
        self.assertEqual(solver_form.responder_faction_ids.ids, self.faction_bad.ids)
        self.assertEqual((solver_form.initiator_stance, solver_form.responder_stance), ('attack', 'defense'))
        self.assertEqual((solver_form.initiator_menace, solver_form.responder_menace), (9, 8))
        solver = solver_form.save()
        self.assertEqual(self._get_units(solver, 'initiator'), self.ww_offense)
        self.assertEqual(self._get_units(solver, 'responder'), self.ww_defense + self.ww_henchmen)
        self.assertEqual(set(solver.initiator_line_ids.mapped('position')), {'frontline'}, 'All units in frontline by default')

        solver.write({'initiator_faction_ids': self.faction_bad.ids, 'responder_faction_ids': self.faction_good.ids})
        self.assertEqual(self._get_units(solver, 'initiator'), self.ww_defense + self.ww_henchmen)
        self.assertEqual(self._get_units(solver, 'responder'), self.ww_offense)

        # held by good ones: bad ones initiate
        solver.battle_location_id = self.location_vw
        self.assertEqual((solver.initiator_faction_ids, solver.responder_faction_ids), (self.faction_bad, self.faction_good))
        self.assertEqual(self._get_units(solver, 'initiator'), self.vw_vampires + self.vw_ghouls)
        self.assertEqual(self._get_units(solver, 'responder'), self.vw_werewolves)

        # only responders in Londinium
        solver.battle_location_id = self.location_londinium
        self.assertFalse(solver.initiator_faction_ids)
        self.assertEqual(self._get_units(solver, 'responder'), self.unit_vampire_2)

    @users('battle_admin')
    def test_sides_out_of_battle(self):
        """ Units can be put out of the battle manually (e.g. scouts), by
        ambush (from support) or by assassination (frontline holder,
        wounding its target before rolling, possibly out of combat) """
        self.ww_henchmen[0].sudo().battle_trait_ids = self.trait_ambush
        solver = self._new_solver_form(self.location_ww).save()
        self._set_lines(solver, 'responder', frontline=self.ww_defense + self.ww_henchmen[1], support=self.ww_henchmen[0])
        offense_1, offense_2, offense_3 = solver.initiator_line_ids.sorted(lambda line: line.battle_unit_id.id)
        defense_1 = solver.responder_line_ids.filtered(lambda line: line.battle_unit_id == self.ww_defense[0])
        ambusher = solver.responder_line_ids.filtered(lambda line: line.position == 'support')
        self.assertTrue(all((offense_1 + offense_2 + offense_3).mapped('can_target')), 'Offense werewolves are assassins')

        offense_1.target_unit_id = self.ww_defense[0]
        self.assertEqual(defense_1.battle_status, '-1 wound')
        self.assertEqual((offense_2.needs_target, offense_2.battle_status), (True, 'Target?'))
        offense_3.target_unit_id = self.ww_defense[0]
        self.assertEqual(defense_1.battle_status, '-2 wound', 'Assassinations stack')
        offense_3.target_unit_id = False
        self.assertEqual((ambusher.needs_target, ambusher.battle_status), (True, 'Target?'))
        self.assertEqual(self._get_units_in_battle(solver, 'responder'), self.ww_defense + self.ww_henchmen)
        self.ww_defense[0].sudo().wound_state = '1'
        solver.invalidate_recordset()
        (defense_1 + ambusher).invalidate_recordset()
        self.assertEqual((defense_1.battle_status, defense_1.is_out), ('Killed', True))
        self.assertEqual(self._get_units_in_battle(solver, 'responder'), self.ww_defense[1] + self.ww_henchmen)

        ambusher.target_unit_id = self.ww_offense[1]
        offense_1.is_excluded = True  # out: its assassination does not happen anymore
        self.assertEqual(offense_2.battle_status, 'Ambushed')
        self.assertEqual(offense_1.battle_status, 'Out')
        self.assertEqual(self._get_units_in_battle(solver, 'initiator'), self.ww_offense[2])
        self.assertEqual(self._get_units_in_battle(solver, 'responder'), self.ww_defense + self.ww_henchmen)

    @users('battle_admin')
    def test_sides_allies_and_holders(self):
        """ Allies fight along their faction; held location: holders and
        their allies respond; units without faction do not fight """
        unit_neutral = self.env['battle.unit'].sudo().create({
            'name': 'Test Neutral Unit', 'unit_type': 'spirit',
            'battle_faction_id': self.faction_neutral_good.id, 'battle_location_id': self.location_ww.id,
        })
        self.ww_offense[2].sudo().battle_faction_id = False

        solver = self._new_solver_form(self.location_ww).save()
        self.assertEqual(solver.initiator_faction_ids, self.faction_good + self.faction_neutral_good)
        self.assertEqual(self._get_units(solver, 'initiator'), self.ww_offense[:2] + unit_neutral)

        self.location_ww.sudo().write({'status': 'held', 'held_by_faction_id': self.faction_good.id})
        solver = self._new_solver_form(self.location_ww).save()
        self.assertEqual(solver.responder_faction_ids, self.faction_good + self.faction_neutral_good)
        self.assertEqual(self._get_units(solver, 'initiator'), self.ww_defense + self.ww_henchmen)

    @users('battle_admin')
    def test_simulate(self):
        """ Simulation gives chances of each score, capped to outcomes range;
        changing sides, units or stances outdates it """
        solver = self._new_solver_form(self.location_vw).save()
        solver.action_simulate()
        self.assertRecordValues(solver, [{'mode': 'simulate', 'battle_outcome_id': False}])

        # bonus +2: scores above +4 are capped
        chances = solver._get_score_chances()
        self.assertEqual({score: round(chance * 27) for score, chance in chances.items()}, {-1: 1, 0: 3, 1: 6, 2: 7, 3: 6, 4: 4})
        self.assertIn('Major Victory', solver.simulation_summary)
        self.assertIn('14.8', solver.simulation_summary)

        self.assertFalse(solver.is_outdated)
        self._set_lines(solver, 'initiator', self.vw_vampires[0])
        self.assertTrue(solver.is_outdated)
        solver.action_simulate()
        self.assertFalse(solver.is_outdated)
        solver.initiator_line_ids.position = 'support'
        self.assertTrue(solver.is_outdated)
        solver.initiator_line_ids.position = 'frontline'
        self.assertFalse(solver.is_outdated, 'Back as simulated')
        solver.responder_stance = 'attack'
        self.assertTrue(solver.is_outdated)


class TestBattleSolverAccess(BattleSolverCommon):

    @users('battle_user')
    def test_access_regular_user(self):
        """ Only admins may run battles """
        with self.assertRaises(AccessError):
            self.env['battle.solver'].create({'battle_location_id': self.location_ww.id})


class TestBattleSolverInternals(BattleSolverCommon):

    def test_bonus_rules(self):
        """ Comparison rules used by bonuses, including edge cases """
        Solver = self.env['battle.solver']
        for rule, values, expected in [
            # characteristic averages, in half points
            (Solver._get_characteristic_advantage, (4, 4), (0, 0)),
            (Solver._get_characteristic_advantage, (5, 4), (0.5, 0)),  # advantage (half point)
            (Solver._get_characteristic_advantage, (6, 4), (1, 0)),
            (Solver._get_characteristic_advantage, (4, 7), (0, 1.5)),
            (Solver._get_characteristic_advantage, (10, 2), (2, 0)),  # capped to 2 points
            (Solver._get_characteristic_advantage, (-1, 3), (0, 2)),
            (Solver._get_bonus_per_half_more, (3, 3), (0, 0)),
            (Solver._get_bonus_per_half_more, (4, 3), (0, 0)),  # less than 50% more
            (Solver._get_bonus_per_half_more, (3, 2), (1, 0)),  # 50% more
            (Solver._get_bonus_per_half_more, (4, 2), (1, 0)),  # max +1
            (Solver._get_bonus_per_half_more, (7, 2), (1, 0)),
            (Solver._get_bonus_per_half_more, (2, 3), (0, 1)),
            (Solver._get_bonus_per_half_more, (1, 0), (1, 0)),
        ]:
            with self.subTest(rule=rule.__name__, values=values):
                self.assertEqual(rule(*values), expected)

    def test_location_shift(self):
        """ A location moves one step towards a side: held by another camp,
        it becomes contested, then held by the side main faction; contested
        and held by the side, it is held again """
        location, good, bad = self.location_ww, self.faction_good, self.faction_bad
        for status, holder, expected in [
            ('free', None, ('held', good)),
            ('held', bad, ('contested', bad)),
            ('contested', bad, ('held', good)),
            ('contested', good, ('held', good)),
            ('held', good, ('held', good)),
        ]:
            with self.subTest(status=status, holder=holder and holder.name):
                location.write({'status': status, 'held_by_faction_id': holder.id if holder else False})
                self.assertEqual(location._get_shifted_status(good, good), expected)

    def test_dice(self):
        """ 3 dice from -1 to +1: -3 to +3, centered on 0 """
        chances = self.env['battle.solver']._get_roll_chances()
        self.assertEqual({total: round(chance * 27) for total, chance in chances.items()}, {-3: 1, -2: 3, -1: 6, 0: 7, 1: 6, 2: 3, 3: 1})

    def test_side_main_faction(self):
        """ Several factions in a side: majority wins, first faction on tie,
        side faction without units """
        good, bad = self.faction_good, self.faction_bad
        for units, factions, expected in [
            (self.ww_offense[0] + self.ww_defense[0] + self.ww_henchmen[0], good + bad, bad),  # majority
            (self.ww_offense[0] + self.ww_defense[0], good + bad, good),  # tie
            (self.env['battle.unit'], bad, bad),  # no units
        ]:
            with self.subTest(units=units.mapped('name')):
                self.assertEqual(self.env['battle.solver']._get_side_main_faction(units, factions), expected)

    def test_side_result(self):
        """ Score is given from initiators point of view """
        for side, score, expected in [
            ('initiator', 2, 'win'),
            ('responder', 2, 'lose'),
            ('initiator', -1, 'lose'),
            ('responder', -1, 'win'),
            ('initiator', 0, 'tie'),
            ('responder', None, None),
        ]:
            with self.subTest(side=side, score=score):
                self.assertEqual(self.env['battle.solver']._get_side_result(side, score), expected)

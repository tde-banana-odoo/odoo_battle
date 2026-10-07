# LG Battle: game reference

Rules, traits, templates and units as implemented in `odoo_battle`, with the
balance analysis and the decisions taken so far.

Snapshot of 2026-10-07 (evening, after the template rework), from the data loaded in `m-tde-battle` (module 1.0).
Counts of "units" are units still fighting (not dead, not out of combat),
including traits they get from their template.

---

## 1. How a battle is solved

A battle opposes two sides in a location:
- the **initiators**;
- the **responders**: the holders of the location and their allies, or the
  defender camp.

Each side picks a **stance**, Attack or Defend. Each of its units is in the
**frontline**, in **support** (second line), or out of the battle. Support
size can't exceed frontline size.

### Bonus

Each side gets a bonus. The initiators' bonus minus the responders' bonus is
added to the dice.

| Source | Rule |
|---|---|
| Characteristics | Sum over the side's units: **Gnosis** in the Umbra, otherwise **Rage** when attacking, **Willpower** when defending. Wound maluses and the enemy's Diversion are subtracted, the Bonus Characteristic (GM input) is added. **+1** to the side having more, **+2** if more than double; a positive value is "more than double" a null or negative one. |
| Size | **+1** to the side having at least 50% more size (never +2, so hordes don't stack size and characteristics). Size rates apply first, e.g. Obstacles −25% for attackers. |
| Morale | **−1** if the camp's morale is 2 (Shaken) or less. |
| Command actions | Location Support: +1 per action. |
| Traits | `bonus` traits of units and location, and those granted for the round (Percée, Défense Héroïque). |

### Dice and score

- **3 dice** with faces −1 / 0 / +1, total from −3 to +3. Rerolls apply when
  rolling: Tactique and Balisé are counted for the table, Moral Vacillant
  rerolls the side's best die.
- **Score** = dice + bonus, capped to −4 … +4, read from the initiators'
  point of view. Responders read the opposite score.

### Damage

For each side, frontline damage and frontline resistance are computed the
same way:

1. sum over frontline units, minus wound maluses;
2. × the side's outcome rate (depends on its stance) × command action rates ×
   trait rates; all rates are multiplied, then rounded down once;
3. \+ flat trait values (Fureur, Discipline…) and support (Appui adds to
   damage, Couverture to resistance). These are **never multiplied** by
   rates.

Damage dealt to a side = enemy damage − own resistance, at least 0.

### Consequences on units

Applied in this order:

1. Wounds before the roll (Assassin).
2. Damage: spread one point at a time over fighting frontline units, then
   over support units once the frontline is down. Every **3 points** add a
   wound and reset the counter.
3. Direct wounds (Wound Enemy): frontline first, least wounded first.
4. **Heal**: −1 wound.
5. **Mend**: damage counter back to 0.

Heal and Mend are choices in the solver, prefilled from Régénération and
Nécrophage (most wounded / most damaged unit first) and editable before
applying.

### Wound states and maluses

| State | Malus |
|---|---|
| 4 Unhurt, 3 Wounded | none |
| 2 Badly Wounded | −1 characteristic |
| 1 Critical | −1 characteristic, −1 damage and −1 resistance (never below 0) |
| 0 Out of Combat | doesn't take part |

Maluses use the wound state at the start of the battle; an assassination
doesn't add a malus for that battle.

---

## 2. Outcomes

Rates (%) apply to the frontline, for the side's stance.

| Score | Outcome | Attack dmg / res | Defense dmg / res | Grants next round (attack / defense) | Location shift |
|---|---|---|---|---|---|
| −4 | Major Defeat | 100 / 50 | 50 / 100 | Moral Vacillant / Moral Vacillant | — |
| −3 | Clear-Cut Defeat | 100 / 50 | 50 / 100 | — | — |
| −2 | Defeat | 100 / 50 | 50 / 125 | — | — |
| −1 | Narrow Defeat | 100 / 50 | 50 / 125 | — | — |
| 0 | Tied | 100 / 50 | 50 / 150 | — | — |
| +1 | Narrow Victory | 100 / 50 | 100 / 150 | — | — |
| +2 | Victory | 150 / 100 | 100 / 200 | — | 1 |
| +3 | Clear-Cut Victory | 150 / 100 | 150 / 200 | Percée / Défense Héroïque | 1 |
| +4 | Major Victory | 200 / 150 | 200 / 250 | Percée / Défense Héroïque | 1 |

- The location shift only happens if the winner attacked.
- **Attacking exposes:** full damage, but resistance halved up to a Narrow
  Victory; an attacker only gains from a Victory on.
- **Defending protects:** damage halved unless winning, resistance ×1.5 from
  a tie on, but it falls with the defeat (×1.25, then ×1 on a Clear-Cut or
  Major Defeat): a routed defender is less protected, never exposed.
- **Both defending:** damage halved, resistance ×1.5 or more on both sides,
  so little happens: a standoff.

With two equal sides (16 frontline damage, 14 resistance), attack against
defense gives, by the attacker's score:

| Attacker's score | −4 | −3 | −2 | −1 | 0 | +1 | +2 | +3 | +4 |
|---|---|---|---|---|---|---|---|---|---|
| Damage to attackers | 25 | 17 | 9 | 9 | 1 | 1 | 0 | 0 | 0 |
| Damage to defenders | 0 | 0 | 0 | 0 | 0 | 0 | 7 | 10 | 18 |

---

## 3. Command actions

Picked by a camp for a location and a round. Each counts against the camp's
command actions (its leadership successes).

| Action | Effect |
|---|---|
| Location Support | +1 bonus per action (cumulative) |
| Hold On | damage ×75%, resistance ×150% |
| Full Attack | damage ×150%, resistance ×75% |
| Unstoppable Attack (RP) | damage ×125%, only when attacking; allowed by role-play |
| Retreat | no battle effect: only noted (the solver shows a "Retreat" line without bonus), resolved by the DM |

Rates apply once per side, whatever the number of actions, and multiply the
outcome rates.

### Effectiveness (analysis of 2026-10-08)

Model: two equal sides (16 frontline damage, 14 resistance), no other
bonus, current outcome rates, average damage over the dice distribution.

| Attacker's command (defender: none) | Dealt | Taken | Victory or better |
|---|---|---|---|
| none | 1.1 | 4.1 | 15% |
| Location Support | 3.3 | 1.8 | **37%** |
| Full Attack | 5.9 | 5.8 | 15% |
| Unstoppable Attack | 2.7 | 4.1 | 15% |
| Hold On | 0.3 | 2.5 | 15% |

| Defender's command (attacker: none) | Dealt | Taken |
|---|---|---|
| none | 4.1 | 1.1 |
| Location Support | 7.5 | 0.3 |
| Hold On | 2.1 | 0.1 |
| Full Attack | 9.1 | 2.9 |

- **Location Support is by far the strongest:** +1 shifts the whole dice
  distribution (Victory or better: 15% → 37%). Cumulative, it reaches 70%
  with two actions and 96% with three: a camp with 3 actions can all but
  decide one battle. This is the main balance issue.
- **Full Attack is a fair gamble:** about twice the damage dealt and taken.
- **Hold On is a delaying action:** both sides take less; very efficient for
  defenders holding a position, nearly useless for an attacker.
- **Unstoppable Attack (RP):** pure bonus with no downside, acceptable as it
  is granted by role-play.
- **On equal forces, attacking without support is costly** (dealt 1.1,
  taken 4.1): by design, an attacker needs a bonus advantage or a command.

---

## 4. Unit traits

Unit traits apply to their holder's side, whichever it is; "side" is only used
on location traits. "Per holder" values add up per unit; unique traits count
once per side.

| Trait | When | Effect | Templates | Units |
|---|---|---|---|---|
| **Tactics** | | | | |
| Commandement | always | +1 bonus, once per side | 4 | 12 |
| Diversion | always | −2 to the enemy's compared characteristic, once per side | 4 | 5 |
| Terreur | always | −1 to the enemy's compared characteristic, once per side (adds to Diversion) | 2 | 3 |
| Tactique | always | 1 die reroll per holder | 2 | 4 |
| **Before the roll** | | | | |
| Assassin | frontline | 1 wound to a chosen enemy unit | 2 | 5 |
| Embuscade | defending, support | removes a chosen enemy unit from the battle | 2 | 2 |
| **Damage** | | | | |
| Contre-Attaque | defending, frontline, on a win | +2 damage | 4 | 14 |
| Fureur | attacking, frontline, on a win | +2 damage | 5 | 16 |
| Massacre | frontline, on a win | 1 wound to an enemy unit after the battle (frontline, least wounded first) | 2 | 6 |
| Appui | attacking, support | adds the unit's damage to the side's damage | 2 | 8 |
| **Resistance** | | | | |
| Assaut Tactique | attacking, frontline | +1 resistance | 4 | 9 |
| Dernier Carré | frontline, on a loss | 1 wound to an enemy unit after the battle (frontline, least wounded first) | 2 | 5 |
| Discipline | defending, frontline | +2 resistance | 2 | 4 |
| Repli Défensif | frontline, on a loss | +2 resistance | 3 | 2 |
| Couverture | defending, support | adds the unit's damage to the side's resistance | 1 | 4 |
| **After the battle** | | | | |
| Nécrophage | always | prefills a Mend: counter reset on a unit of the side | 1 | 2 |
| Régénération | always | prefills a Heal: −1 wound on a unit of the side | 1 | 1 |
| Effroi | on a win | role-play: enemy units may flee | 2 | 6 |
| **Lore / role-play** (listed under "To resolve") | | | | |
| Fétiche | — | narrative | 2 | 6 |
| Fanatique, Feu | — | narrative | 2, 1 | 7, 5 |
| Argent, Béni, Eclaireur | — | narrative | 0 | 0 |

A tie is neither a win nor a loss: "on a win" and "on a loss" traits don't
apply.

Each battle trait covers one situation; no trait is an "always on" statistic
bonus (Rage was removed for that reason, see 9).

| | Attacking | Defending | On a loss |
|---|---|---|---|
| Damage | Fureur +2 (on a win) | Contre-Attaque +2 (on a win) | Dernier Carré (wound to the winner) |
| Wounds on a win (any stance) | Massacre | Massacre | — |
| Resistance | Assaut Tactique +1 | Discipline +2 | Repli Défensif +2 |
| Support | Appui | Couverture, Embuscade | — |

Assaut Tactique stays at +1 while Discipline gets +2, because an attacker's
resistance is mostly halved and a defender's multiplied by 150% or more: with
10 frontline resistance, +1 is worth +20% when attacking (5 → 6), +2 about
+13% when defending (15 → 17).

**Effects available to traits:** Damage Rate, Resistance Rate (±% on
frontline) and Size Rate (±% on size), used by location traits
(Impraticable, Obstacles) but by no unit trait yet.

---

## 5. Location traits

| Trait | When | Effect | Locations |
|---|---|---|---|
| Fortifié | responders, defending | +1 bonus | 6 |
| Balisé | responders | 1 die reroll | 6 |
| Ravitaillé | responders | prefills a Heal: −1 wound on their most wounded unit after the battle | 6 |
| Impraticable | everyone | resistance −25% (hostile ground, e.g. flooded by Loch Chon's water spirit) | 4 |
| Piégé | responders, defending | 1 wound to an attacking unit after the battle, whatever the result | 3 |
| Obstacles | attacking | size −25% for the size bonus (the advance is slowed) | 2 |
| **Granted manually** to a faction for a round, as a location effect | | | |
| Esprit des Eaux | always | resistance +25%, once per side (Loch Chon's water spirit; offsets most of Impraticable: 75% × 125% ≈ 94%) | — |
| **Granted by outcomes** for the next round, to the side's factions | | | |
| Percée | attacking | +1 bonus, once per side | — |
| Défense Héroïque | defending | +1 bonus, once per side | — |
| Moral Vacillant | always | the side's best die is rerolled | — |

Responders are the holders and their allies. Location traits apply once
(they have no holders), and the descriptions printed on location sheets are
in French.

**Faction-specific help** (e.g. the water spirit siding with Loch Chon) goes
through round effects: a trait granted to a faction at a location for a
round, entered in the round's Location Effects tab (or the location's Effects
tab), like the traits granted by
outcomes.

Locations without traits: Enclos, Bois (Umbra), Walkhill (Umbra), King
Industries, Penumbra, Abysses, Loch Chon Regional Environment Park, Comté de
Walkhill, Lommond Hills.

---

## 6. Templates

Statistics: Menace / Size / Rage / Willpower / Gnosis / Damage / Resistance.
Units: fighting units using the template. Names are in French (printed);
the short name is printed below the glyph on unit sheets, without the
variant (traits tell variants apart), "+" marking an elite version.

**Design rules:**
- Leaders (rank 4, G7) have 3 battle traits; other templates have 0 to 2.
- A template without trait gets a better statistic (e.g. rank 2: damage 4).
- Variants of a family mix offensive and defensive units: Ruse trades traits
  for statistics, Corrupt / Respect trades statistics for action traits.
- Assassin is for specialists (BSD Corrupt, G8 Ruse); leaders frighten
  through Massacre, earned by winning.

| Template | Short name | Stats | Traits | Units |
|---|---|---|---|---|
| **Black Spiral Dancers** | | | | |
| Danseurs de la Spirale Noire Rang 4 | DSN 4 | 5/1/3/2/2/5/4 | Commandement, Fureur, Massacre, Fétiche | 3 |
| Danseurs de la Spirale Noire Rang 3 | DSN 3 | 4/1/3/2/1/4/3 | Tactique, Fureur | 0 (1 dead) |
| Danseurs de la Spirale Noire Rang 3 (Ruse) | DSN 3 | 4/1/2/3/1/4/4 | Embuscade | 1 (2 dead) |
| Danseurs de la Spirale Noire Rang 3 (Corrompus) | DSN 3 | 4/1/2/2/2/3/3 | Diversion, Assassin | 2 |
| Danseurs de la Spirale Noire Rang 2 | DSN 2 | 3/1/2/1/1/4/2 | — | 2 |
| Danseurs de la Spirale Noire Rang 2 (Ruse) | DSN 2 | 3/1/1/2/1/2/3 | Contre-Attaque | 2 |
| Danseurs de la Spirale Noire Rang 2 (Corrompus) | DSN 2 | 3/1/1/1/2/2/2 | Repli Défensif | 0 |
| **Werewolves** | | | | |
| Loups-Garous Rang 4 | LG 4 | 5/1/3/2/2/5/4 | Commandement, Contre-Attaque, Massacre, Fétiche | 3 |
| Loups-Garous Rang 3 | LG 3 | 4/1/3/2/1/4/3 | Tactique, Contre-Attaque | 4 |
| Loups-Garous Rang 3 (Ruse) | LG 3 | 4/1/2/3/1/4/4 | Embuscade | 1 |
| Loups-Garous Rang 3 (Respect) | LG 3 | 4/1/2/2/2/3/3 | Diversion, Dernier Carré | 2 |
| Loups-Garous Rang 2 | LG 2 | 3/1/2/1/1/4/2 | — | 1 |
| Loups-Garous Rang 2 (Ruse) | LG 2 | 3/1/1/2/1/2/3 | Assaut Tactique | 2 |
| Loups-Garous Rang 2 (Respect) | LG 2 | 3/1/1/1/2/2/2 | Discipline | 1 |
| **Fera** | | | | |
| Fera Rang 3 | Fera 3 | 4/1/2/2/2/3/3 | Diversion, Repli Défensif | 1 |
| **Vampires and ghouls** | | | | |
| Coterie Vampire G7 | Vamp. G7 | 5/1/2/3/2/4/6 | Commandement, Terreur, Fureur, Régénération | 1 |
| Coterie Vampire G8 | Vamp. G8 | 4/1/2/2/2/4/3 | Assaut Tactique, Effroi | 3 |
| Coterie Vampire G8 (Ruse) | Vamp. G8 | 4/1/1/3/2/2/4 | Assassin, Effroi | 3 |
| Goules de Combat | Goules+ | 3/1/2/2/0/4/2 | Terreur, Nécrophage | 2 |
| Goules | Goules | 2/1/1/1/1/3/1 | Dernier Carré | 3 |
| **Humans** | | | | |
| Infanterie Mécanisée | Méca | 3/2/2/2/1/3/3 | Appui, Assaut Tactique | 2 |
| Forces Spéciales | FS | 2/2/1/1/1/2/2 | Assaut Tactique | 2 |
| Forces Spéciales (Ruse) | FS | 2/2/1/1/1/2/2 | Discipline | 3 |
| Hommes de Main | HdM | 1/2/0/0/0/1/1 | Appui | 6 (4 dead) |
| Hommes de Main (Ruse) | HdM | 1/2/0/0/0/1/1 | Couverture | 4 (2 dead) |
| Humains | Humains | 0/2/0/0/0/1/1 | — | 8 (2 dead) |
| **Fomori and possessed** | | | | |
| Fomoris Améliorés | Fomoris+ | 2/1/2/1/0/2/4 | Repli Défensif | 1 |
| Fomoris | Fomoris | 1/2/1/0/0/1/2 | Fanatique | 2 |
| Possédés Élite | Possédés+ | 2/1/1/1/1/3/1 | Fureur | 3 |
| Possédés | Possédés | 1/2/0/1/0/2/0 | Fanatique, Feu | 5 |
| **Spirits** | | | | |
| Incarna | Incarna | 5/1/1/2/4/4/4 | Commandement | 5 |
| Jaglin | Jaglin | 2/2/1/1/2/3/2 | Fureur | 9 |
| Jaglin (Ruse) | Jaglin | 2/2/0/2/2/2/3 | Contre-Attaque | 5 |
| Jaglin (Corrompus) | Jaglin | 2/2/0/1/3/2/2 | Diversion | 0 |
| Gaflin | Gaflin | 1/2/0/0/1/1/2 | — | 6 |
| Gaflin (Ruse) | Gaflin | 1/2/0/0/1/2/1 | — | 5 |

**BSD and werewolves** share statistics per rank and variant, their traits
differ:
- BSD lean offensive: Fureur on rank 4 and 3, Assassin on Corrupt.
- Werewolves lean defensive: Contre-Attaque on rank 4 and 3, Dernier Carré on
  Respect.
- Both rank 4 have Massacre.
- Rank 2 variants mix both: BSD Ruse Contre-Attaque and Corrupt Repli
  Défensif, werewolf Ruse Assaut Tactique and Respect Discipline.

**Vampires:** Terreur (a real effect) only on the G7 elder and the Combat
Ghouls; the G8 coteries have Effroi, which is role-play.

No template has negative characteristics anymore.

---

## 7. Units

103 units are fighting (62 aggressors, 41 defenders), and 11 are dead or out
of combat. Neutral factions follow their ally: Hel, Yamazaki and Scotland
fight with the aggressors (Kiker), Weaver and Gaia with the defenders (Loch
Chon).

**Overrides on templates:**
- Les Damnés de Y Ddraig Wen: Rage +1.
- French Connection: Willpower −1.
- Celui-qui-Clot: a unique boss on the Incarna template, at 6/1/4/4/4/7/5.

### Forces per location

Units, size and menace of fighting units; Rage / Willpower / Gnosis summed;
frontline damage / resistance if everyone fights; battle traits (unique ones
like Commandement or Terreur count once per side in battle). Wound maluses
aren't counted.

| Location | Camp | Units | Size | Menace | R / W / G | Dmg / Res | Battle traits |
|---|---|---|---|---|---|---|---|
| **Hills** (contested; Fortifié, Ravitaillé, Balisé) | Kiker | 8 | 10 | M27 | 13 / 16 / 12 | 28 / 24 | Commandement, Terreur ×3, Fureur ×3, Régénération, Assassin, Assaut Tactique ×2, Nécrophage ×2 |
|  | Loch Chon | 5 | 7 | M11 | 7 / 6 / 3 | 14 / 11 | Tactique, Contre-Attaque, Embuscade |
| **Hills (Umbra)** (contested, Umbra; Dangereux) | Kiker | 7 | 13 | M16 | 6 / 10 / 14 | 19 / 19 | Commandement, Fureur ×2, Contre-Attaque ×2 |
|  | Loch Chon | 7 | 13 | M12 | 2 / 3 / 11 | 15 / 13 | Commandement, Fureur |
| **Rivière du Loch** (held; Dangereux, Piégé) | Loch Chon | 2 | 4 | M4 | 1 / 3 / 4 | 5 / 5 | Contre-Attaque, Fureur |
| **Bois** (held; Piégé, Ravitaillé) | Kiker | 2 | 2 | M4 | 2 / 2 / 2 | 6 / 2 | Dernier Carré ×2 |
|  | Loch Chon | 2 | 3 | M4 | 1 / 2 / 1 | 3 / 4 | Assaut Tactique, Appui |
| **Route du Centre** (held; Obstacles, Fortifié, Ravitaillé, Balisé) | Kiker | 4 | 4 | M16 | 9 / 8 / 6 | 14 / 14 | Commandement, Fureur, Massacre, Diversion, Assassin, Embuscade, Contre-Attaque |
|  | Loch Chon | 7 | 11 | M14 | 9 / 6 / 4 | 17 / 14 | Tactique ×2, Contre-Attaque ×3, Commandement, Massacre, Appui |
| **Marais** (held; Dangereux) | Kiker | 1 | 1 | M5 | 3 / 2 / 2 | 5 / 4 | Commandement, Fureur, Massacre |
| **Park Center** (held; Fortifié, Ravitaillé, Balisé) | Loch Chon, Weaver | 7 | 9 | M24 | 12 / 12 / 10 | 22 / 21 | Commandement ×2, Contre-Attaque ×4, Massacre ×2, Diversion, Dernier Carré, Tactique, Assaut Tactique, Couverture |
| **Walkhill** (held; Fortifié, Balisé) | Hel, Kiker, Scotland, Yamazaki | 23 | 40 | M40 | 19 / 19 / 14 | 43 / 41 | Appui ×6, Assaut Tactique ×4, Discipline ×3, Fureur ×3, Repli Défensif, Diversion, Assassin ×2, Couverture |
| **Walkhill (Umbra)** (contested, Umbra) | Weaver | 3 | 6 | M6 | 2 / 4 / 6 | 8 / 7 | Fureur ×2, Contre-Attaque |
| **King Industries** (held) | Scotland | 1 | 2 | M0 | 0 / 0 / 0 | 1 / 1 | — |
|  | Loch Chon | 4 | 5 | M13 | 4 / 5 / 9 | 10 / 11 | Diversion, Dernier Carré, Discipline, Commandement |
| **Penumbra** (contested, Umbra) | Gaia | 2 | 2 | M9 | 3 / 4 / 6 | 7 / 7 | Commandement, Diversion, Repli Défensif |
| **Abysses** (held, Umbra) | Kiker | 5 | 9 | M10 | 2 / 3 / 9 | 12 / 10 | Commandement, Fureur |
| **Loch Chon Regional Environment Park** (held) | Loch Chon | 2 | 4 | M2 | 0 / 0 / 0 | 2 / 2 | Couverture ×2 |
| **Lommond Hills** (held) | Kiker | 11 | 15 | M28 | 12 / 16 / 10 | 32 / 19 | Commandement, Fureur, Massacre, Contre-Attaque, Assassin, Assaut Tactique, Dernier Carré |

### Traits per camp (fighting units)

| Camp | Units | Battle traits |
|---|---|---|
| Aggressors | 62 | Fureur 12, Assaut Tactique 7, Commandement 6, Appui 6, Assassin 5, Contre-Attaque 4, Massacre 3, Terreur 3, Dernier Carré 3, Discipline 3, Diversion 2, Nécrophage 2, Embuscade 1, Régénération 1, Repli Défensif 1, Couverture 1 |
| Defenders | 41 | Contre-Attaque 10, Commandement 6, Tactique 4, Fureur 4, Diversion 3, Massacre 3, Couverture 3, Dernier Carré 2, Assaut Tactique 2, Appui 2, Embuscade 1, Discipline 1, Repli Défensif 1 |

---

## 8. Analysis

### Resolved by the template rework

- **Embuscade is rare:** 2 units (BSD and werewolf Ruse), down from 7.
- **Assassin is rare:** 5 units (BSD Corrupt, G8 Ruse), down from 11.
  Leaders get Massacre instead: a wound after a won battle, no longer a
  chosen target before the roll.
- **No trait stacking on cheap units:** one role per human template.
- **No negative characteristics:** civilians bring size only.
- **Umbra battles have traits:** Jaglin (Fureur), Jaglin (Ruse)
  (Contre-Attaque).
- **Fear has two levels:** Terreur (−1 to the enemy characteristic, once per
  side) on 3 units; Effroi (role-play: the enemy may flee when losing) on the
  G8 coteries.
- **Names and menaces:** template names are distinct, Jaglins are menace 2,
  Possédés Elite menace 2.

### Points to look at

1. **BSD Rank 3 (Ruse) rarely uses its trait.** Embuscade only applies
   when defending, while Kiker mostly attacks: French Connection at Route du
   Centre has no usable trait there. Its better statistics (4/4) compensate.

2. **Rank 2 Corrupt / Respect look weak outside the Umbra.** 2 damage / 2
   resistance plus a conditional trait, against 4 / 2 with no trait for the
   base rank 2, and 2 / 3 plus a trait for Ruse. Resistance 3 would put them
   level with Ruse.

3. **Fear at Hills.** Kiker brings Terreur and Diversion is absent, so Loch
   Chon gets −1: Willpower 6 → 5 against Kiker's Rage 13 or Willpower 16.
   Kiker already has more than double; Terreur matters more in close
   battles.

4. **Dernier Carré and Massacre bite at small scale.** At Bois, Kiker's 2
   Ghouls each wound a Loch Chon unit when losing, on a side of 2 units. In
   bigger battles it's diluted.

5. **The Walkhill garrison is meant to implode.** Hel and Yamazaki
   (8 units, M16) follow Kiker today. Setting their allied faction to Loch
   Chon (in the faction data file, which is force-updated) makes Walkhill a
   battle: Kiker and Scotland (15 units, M24) against them. Hel brings 2
   Assassins (Hel's Angels, Baron den Linden) and a Diversion.

6. **Attackers gain nothing from a Narrow Victory.** Up to +1 they keep 100%
   damage and 50% resistance. Unchanged, mentioned so it stays a choice.

### Data hygiene

- "Jaglin (Corr)" vs "Black Spiral Dancer Rank 3 (Corrupt)": two spellings.
- "Fera 3" doesn't follow the "Rank 3" naming.
- Unused templates: BSD Rank 2 (Corrupt), Jaglin (Corr).
- Unused traits: Argent, Béni, Eclaireur.

---

## 8b. Balance tests

`tests/test_battle_balance.py` builds units from the data templates (with
their traits) and evaluates battles exactly over all dice rolls: win / tie /
loss chances, and expected wounds received by each side (damage and wound
traits; Assassin, Embuscade, heal and mend not counted). Locations: open
ground, Fortifié, Umbra, held by the defender. Run the report with
`--test-tags /odoo_battle:TestBattleBalance.test_balance_report`.

Results on 2026-10-08 data:

| Scenario | Bonus | Win / tie / loss | Wounds received (initiators / responders) | Why |
|---|---|---|---|---|
| 3 BSD3 attack 3 WW3, open | +1 | 63 / 22 / 15 | 0.44 / 1.48 | Rage 9 vs Willpower 6 |
| same, Fortifié | 0 | 37 / 26 / 37 | 1.22 / 0.67 | Fortifié cancels it |
| 3 WW3 attack 3 BSD3, open | +1 | 63 / 22 / 15 | 0.30 / 0.67 | symmetric chances, BSD deal more |
| both attack / both defend | 0 | 37 / 26 / 37 | 1.85 / 2.52 — 0.44 / 0.11 | BSD more damage, WW better defense |
| BSD 4+3+3c vs WW 4+3+3r, either attacking | +1 | 63 / 22 / 15 | | Diversions cancel |
| Vampires (G7 + 2 G8) attack 3 WW3 | **+2** | **85** / 11 / 4 | 0.11 / 2.19 | Commandement, Terreur (6 vs 5) |
| 3 WW3 attack vampires | 0 | 37 / 26 / 37 | 0.78 / 0.00 | vampires very tanky (G7 resistance 6) |
| … + 2 Combat Ghouls | −3 | 0 / 4 / 96 | 7.85 / 0.00 | Willpower, size, Commandement |
| … + 2 Hommes de Main | −1 | 15 / 22 / 63 | 2.22 / 0.00 | size |
| 2 WW3 attack humans (2 FS, 2 HdM in support) | +1 | 63 / 22 / 15 | 0.00 / 0.81 | humans cannot hurt werewolves |
| same, Fortifié | 0 | 37 / 26 / 37 | 0.00 / 0.30 | |
| 3 WW3 attack 3 Jaglins, Umbra | **−2** | **4** / 11 / 85 | 1.11 / 0.00 | Gnosis 3 vs 6, size 3 vs 6 |
| same, outside the Umbra | +1 | 63 / 22 / 15 | 0.00 / 1.22 | |

Asserted: shapeshifters symmetric and balanced on Fortifié, attackers
favored on open ground, BSD more damage / WW better defense, agents help
vampires, werewolves beat humans, spirits stronger in the Umbra.

**Soft targets not met** (logged as warnings, not failures):
- **Vampires too strong:** they win 85% attacking werewolves (target: at
  most 63%, like werewolves attacking BSD). The swing is Terreur on the G7:
  without it, characteristics are even (6 vs 6) and the bonus drops to +1
  (63%). Agents also turn into reinforcements (Willpower, size) rather than
  damage collectors.
- **Jaglins overwhelming in the Umbra:** 3 Jaglins (menace 6) beat 3
  werewolves packs (menace 12) 85% of the time (target: werewolves keep at
  least 15%). Jaglin size 2 → 1 would remove the size bonus (−1: 15%).

**Structural observation:** between shapeshifters (Rage 3, Willpower 2), the
attacker always gets +1 on open ground. Attacking is favored unless the
location is fortified; intended or to discuss.

---

## 9. Decisions

**Game rules**
- Each side reads its own outcome; rates depend on its stance. Defenders can
  deal damage too.
- A defender's resistance falls with its defeat: 125% on a Narrow Defeat or
  Defeat, 100% on a Clear-Cut or Major Defeat. Before, it never went below
  150% and took almost no damage when losing; a first try going down to 50%
  was too harsh (Route du Centre: a Kiker Victory dealt 14, now 11).
- Trait values and support fire are added after the rates, which are
  multiplied together and rounded down once.
- Hold On and Full Attack apply once per side and multiply outcome rates.
  Location Support is cumulative. Unstoppable Attack is granted by
  role-play, noted "(RP)" in its name, with no extra code.
- Morale and leadership are per camp, on the round; there's no camp model.
- Wound maluses: Badly Wounded −1 characteristic; Critical −1 characteristic
  and −1 damage/resistance. Assassin wounds don't add a malus for the same
  battle.
- Diversion: −2 to the enemy's characteristic, once per side. Meant to be
  rare.
- Traits carry identity, statistics carry power: no "always on" stat traits.
  Rage removed (no base damage compensation); Fureur and Contre-Attaque +2;
  Discipline defending only, +2; Assaut Tactique stays +1; Dernier Carré
  added (frontline, on a loss, 1 wound to the enemy); Embuscade unchanged
  (defending, support).
- Support traits named Appui (attacking) and Couverture (defending).
- Location traits have battle effects: Piégé (1 wound to attackers),
  Ravitaillé (1 heal), Obstacles (attackers' size −25%), Impraticable
  (formerly Dangereux: resistance −25% for everyone). Fortifié and Balisé
  unchanged.
- Esprit des Eaux: +25% resistance, granted manually to Loch Chon at a
  location for a round (location effect), when the water spirit intervenes.
- Templates (see 6): leaders (rank 4, G7) have 3 battle traits, other
  templates 0 to 2; a template without trait gets a better statistic.
  Variants give a family both offensive and defensive units.
- No negative characteristics: civilians (Humains) are 0/0/0 and bring size
  only.
- Assassin only on specialists (BSD Corrupt, G8 Ruse). Leaders (rank 4) get
  Massacre: frontline, on a win, 1 wound to an enemy unit after the battle.
- Terreur is a real effect (−1 to the enemy characteristic, once per side),
  only on G7 vampires and Combat Ghouls. Effroi (role-play, the enemy may flee
  when losing) replaces it on the G8 coteries.
- Heal and Mend are solver choices, prefilled from traits and editable; they
  apply after damage and wounds.
- Location effects of past rounds aren't worth recording; results in data are
  summaries only.
- Round 4 Marais: Défense Héroïque for Loch Chon, granted by role-play.

**Module**
- No new models when avoidable; keep things simple and generic, and avoid new
  code when data can do it.
- Trait names in French (they're printed), xml ids in English, no
  translations. Descriptions follow one pattern: conditions in a fixed order
  (side for location traits, "Occupants" = responders; stance; position;
  result), then " : " and the effect, "(une fois par camp)" for unique
  traits. Location descriptions stay under ~40 characters to fit sheets.
- `battle.leader` is labelled "Leader" everywhere, with no model rename.
  Fields are renamed only when confusing.
- Unit types stay a selection; rules live on templates.
- No migrations, version 1.0. Data is force-updated during development.
- Printed sheets: square cards, black-and-white glyphs to color by hand (red /
  green / orange), wounds and damage filled in by hand.

---

## 10. Open discussions

Not decided; to come back to.

- **Points of section 8** to decide: BSD Ruse Embuscade, Rank 2 Corrupt /
  Respect statistics.
- **Command actions** (see 3, effectiveness):
  - **Cap Location Support:** at most +2 per side (preferred: still rewards
    a big leadership roll, but 3 actions cannot lock a battle), or once per
    side, or diminishing. Small code change (a cap constant) and a test.
  - **Give Retreat a meaning:** either a "covered retreat" (damage ×0%,
    resistance ×200%: the side leaves without fighting back and takes
    little; the DM then moves its units out and the location is lost; only
    a constant), or pure role-play (without a Retreat action, a fleeing side
    suffers a pursuit, e.g. Massacre-like wounds). The first is clearer for
    players: spend a command to get out alive.
  - Hold On, Full Attack and Unstoppable Attack are fine as they are.
- **Balance targets** (see 8b): vampires (Terreur on G7?), Jaglins in the
  Umbra (size 1?), attacker advantage between shapeshifters, agents as damage
  collectors. More scenarios to add as needed.
- **Walkhill implosion:** when Hel and Yamazaki turn, set their allied
  faction to Loch Chon in the faction data file.
- **Former proposals, kept for reference:**
  - Diversion as a Gnosis-based support for both stances (replaced by the
    flat −2).
  - "Break the wall" (−2 enemy resistance): identical to +2 damage, so it
    would be a Damage trait.
  - Self-only Régénération / Nécrophage: no longer needed, since Heal and
    Mend are solver choices.
- **Technical roadmap:**
  - move battle rules from the transient solver into a reusable rules model,
    for balance tests and batch solving;
  - named balance scenario tests asserting outcome probability ranges, with
    scenarios provided by the GM.

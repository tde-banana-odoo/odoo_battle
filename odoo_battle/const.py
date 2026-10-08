""" Battle vocabulary and rules constants, shared by models, wizards and
reports. Kept apart from models to avoid circular imports, and to find game
rules in one place. Technical constants used by a single file (e.g. fields
lists for computes) stay in that file. """
from typing import Literal

# ------------------------------------------------------------
# FACTIONS AND ROUNDS
# ------------------------------------------------------------

# the two camps of the war; neutral factions fight along the camp of their ally
CAMPS = [('aggressor', 'Aggressors'), ('defender', 'Defenders')]
FACTION_ROLES = [('aggressor', 'Aggressor'), ('defender', 'Defender'), ('neutral', 'Neutral')]
# camp morale, from best to worst; integer-like keys ease comparisons, 2 or less being a battle malus
MORALES = [('4', 'Outstanding'), ('3', 'Steady'), ('2', 'Shaken'), ('1', 'Wavering'), ('0', 'Routing')]
# integrity of the Caern defended by players (Loch Chon), from full power to corrupted
CAERN_STATES = [('4', 'Full Power'), ('3', 'Weakened'), ('2', 'Damaged'), ('1', 'Failing'), ('0', 'Corrupted')]

# command actions picked by camps in locations, thanks to leadership successes
COMMAND_TYPES = [
    ('location_support', 'Location Support'),
    ('hold_on', 'Hold On'),
    ('full_attack', 'Full Attack'),
    ('retreat', 'Retreat'),
    ('attack_unstoppable', 'Unstoppable Attack (RP)'),  # allowed by role-play only
]
# rates (%) applied on a side frontline damage and resistance, on top of
# outcome rates; once per side whatever the number of actions
COMMAND_RATES = {
    'hold_on': {'damage': 75, 'resistance': 150},
    'full_attack': {'damage': 150, 'resistance': 75},
    'attack_unstoppable': {'damage': 125, 'resistance': 100},
    'retreat': {'damage': 0, 'resistance': 200},  # covered retreat; the DM then moves units out
}
# command actions applying only for a stance of the side (others: any stance)
COMMAND_STANCES = {'attack_unstoppable': 'attack'}
# battle bonus given by each action (cumulative, up to a maximum per side)
COMMAND_BONUS = {'location_support': 1}
COMMAND_BONUS_MAX = {'location_support': 2}

# ------------------------------------------------------------
# UNITS, LEADERS AND LOCATIONS
# ------------------------------------------------------------

# types of units, also used for leaders
UNIT_TYPES = [
    ('werewolf', 'Werewolf'),
    ('bsd', 'Black Spiral Dancer'),
    ('vampire', 'Vampire'),
    ('ghoul', 'Ghoul'),
    ('human', 'Human'),
    ('human_armored', 'Armored Human'),
    ('spirit', 'Spirit'),
    ('possessed', 'Possessed'),
    ('fomori', 'Fomori'),
    ('fera', 'Fera'),
]
# from unhurt to out of combat, for units and leaders
WOUND_STATES = [('4', 'Unhurt'), ('3', 'Wounded'), ('2', 'Badly Wounded'), ('1', 'Critical'), ('0', 'Out of Combat')]
# damage accumulates on units: every DAMAGE_PER_WOUND points, a wound is added
DAMAGE_PER_WOUND = 3
# battle maluses of wounded units, per wound state (unhurt and wounded: none,
# out of combat: does not fight); damage and resistance never go below 0
WOUND_MALUSES = {
    '2': {'characteristic': 1},
    '1': {'characteristic': 1, 'damage': 1, 'resistance': 1},
}
# narrative status of leaders
NARRATIVE_STATES = [('alive', 'Alive'), ('routing', 'Routing'), ('dead', 'Dead'), ('mia', 'Missing')]
LOCATION_STATUSES = [('free', 'Free'), ('contested', 'Contested'), ('held', 'Held')]

# ------------------------------------------------------------
# BATTLES
# ------------------------------------------------------------

SIDE_SELECTION = [('initiator', 'Initiators'), ('responder', 'Responders')]
SIDES = ('initiator', 'responder')
STANCES = [('attack', 'Attack'), ('defense', 'Defend')]
POSITIONS = [('frontline', 'Frontline'), ('support', 'Support')]
# bonus given by the DM to a side (e.g. a good idea), as a bonus line: an
# advantage is half a point, adding up with others (the final bonus is rounded
# toward zero)
DM_BONUSES = [
    ('0', 'None'),
    ('0.5', 'Advantage (+0.5)'),
    ('1', 'Bonus (+1)'),
    ('1.5', 'Bonus and Advantage (+1.5)'),
    ('2', 'Double Bonus (+2)'),
    ('3', 'Overwhelming (+3)'),
]
# a battle is solved using a single throw of DICE_COUNT dice, each giving one of DICE_FACES
DICE_FACES = (-1, 0, 1)
DICE_COUNT = 3
# battle score, from initiators point of view: from major defeat to major victory
OUTCOME_SCORE_MIN, OUTCOME_SCORE_MAX = -4, 4

# ------------------------------------------------------------
# TYPING
# ------------------------------------------------------------

type Camp = Literal['aggressor', 'defender']
type Side = Literal['initiator', 'responder']
type Stance = Literal['attack', 'defense']
type Position = Literal['frontline', 'support']
type SideResult = Literal['win', 'lose', 'tie']
# state of a unit regarding damage: (damage counter, wound state)
type UnitState = tuple[int, str]

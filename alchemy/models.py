"""Alchemy module - Harmony crafting tracker.

Tracks elixir stock and calculates base materials needed to craft a target
number of Harmonies. 1 Harmony = 1x each of the 5 draughts.
Each draught = 4 elixirs. Each elixir has its own base ingredients.

Additionally, 4 standalone elixirs (Semihumano, Voluntad, Grifo, Caza de Humano)
are tracked separately from the Harmony structure (3 of each needed per Harmony).

Ingredient hierarchy
--------------------
- Raw materials: gathered/bought directly, no recipe (e.g. Ash Sap, Salt).
- Swap groups: a set of interchangeable raw items (BloodType, SwapGroup).
  Blood stock is tracked as a single value per tier (blood_t1 .. blood_t5).
  The user enters a total count per tier; individual animal list shown as tooltip.
- Craftable intermediates: items with their own sub-recipes (CraftableItem).
  When calculating total raw materials the tree is expanded recursively until
  only raw materials and swap groups remain.

Craftable intermediates in this module:
  Reagents      → Clear Liquid Reagent, Pure Powder Reagent
  Crafted Bloods → Clown Blood, Sinner's Blood, Tyrant Blood,
                   Divine Beast Blood, Wise Man's Blood
  Oils          → Oil of Corruption, Oil of Regeneration, Oil of Storms,
                   Oil of Fortitude, Oil of Tranquility

Data sourced from BDO.xlsx (ELIXIRES sheet), Spanish names translated to English.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Swap groups  (interchangeable raw items — any member satisfies the recipe)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SwapGroup:
    """A set of interchangeable raw items.

    Any single member can be used to satisfy a recipe requirement.
    Stock is tracked as a single aggregate value keyed by `key`.

    Attributes:
        key: Stable identifier used in recipe Ingredient.key and as DB key.
        members: Display names of individual items in this group (tooltip only).
    """

    key: str
    members: List[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        """Short label: first two members joined with ' / '."""
        parts = " / ".join(self.members[:2])
        if len(self.members) > 2:
            parts += f" / +{len(self.members) - 2} more"
        return parts

    @property
    def member_keys(self) -> List[str]:
        return [m.lower().replace(" ", "_") for m in self.members]

    @property
    def tooltip(self) -> str:
        return "Valid items: " + ", ".join(self.members)


# ---------------------------------------------------------------------------
# Blood type groups  (subclass of the swap group concept, same mechanics)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BloodType:
    """A group of interchangeable raw bloods.

    Stock is tracked as a single value keyed by `key` (e.g. 'blood_t1').
    Individual member names are stored only for tooltip display.

    Attributes:
        key: Stable identifier used in recipe Ingredient.key and as DB key.
        members: Individual blood names (shown in tooltip only).
    """

    key: str
    members: List[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        short = " / ".join(m.replace(" Blood", "") for m in self.members[:3])
        if len(self.members) > 3:
            short += f" / +{len(self.members) - 3} more"
        return f"{short} Blood"

    @property
    def member_keys(self) -> List[str]:
        """Member keys — for tooltip display only, NOT used as DB stock keys."""
        return [m.lower().replace(" ", "_") for m in self.members]

    @property
    def tooltip(self) -> str:
        return "Valid bloods: " + ", ".join(self.members)


# Five raw blood groups ordered by tier (matches in-game icons).
BLOOD_TYPES: List[BloodType] = [
    BloodType(
        key="blood_t1",
        members=[
            "Weasel Blood",
            "Raccoon Blood",
            "Marmot Blood",
            "Scorpion Blood",
            "Fox Blood",
        ],
    ),
    BloodType(
        key="blood_t2",
        members=[
            "Llama Blood",
            "Sheep Blood",
            "Pig Blood",
            "Ox Blood",
            "Deer Blood",
            "Goat Blood",
            "Waragon Blood",
        ],
    ),
    BloodType(
        key="blood_t3",
        members=["Rhino Blood", "Wolf Blood", "Flamingo Blood", "Cheetah Dragon Blood"],
    ),
    BloodType(
        key="blood_t4",
        members=[
            "Bear Blood",
            "Troll Blood",
            "Ogre Blood",
            "Dinosaur Blood",
            "Yak Blood",
            "Lion Blood",
        ],
    ),
    BloodType(
        key="blood_t5",
        members=["Kuku Bird Blood", "Lizard Blood", "Bat Blood", "Cobra Blood"],
    ),
]

BLOOD_TYPE_BY_KEY: Dict[str, BloodType] = {bt.key: bt for bt in BLOOD_TYPES}

# Wild Grass / Weeds swap group (used in reagent recipes).
WEEDS_GROUP = SwapGroup(key="weeds", members=["Wild Grass", "Weeds"])

# All swap groups (blood types + non-blood swap groups) for unified lookup.
ALL_SWAP_GROUPS: Dict[str, object] = {
    **BLOOD_TYPE_BY_KEY,
    WEEDS_GROUP.key: WEEDS_GROUP,
}


# ---------------------------------------------------------------------------
# Ingredient
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ingredient:
    """One ingredient line in a recipe.

    For swap-group / blood-type ingredients, key == the group key and
    swap_group_key is set. Stock is aggregated across all group members.

    Attributes:
        key: Stable snake_case identifier.
        name: Display name.
        quantity: Amount needed per 1 craft of the parent item.
        swap_group_key: If set, this ingredient is a swap group.
    """

    key: str
    name: str
    quantity: int
    swap_group_key: Optional[str] = None

    @property
    def is_swap_group(self) -> bool:
        return self.swap_group_key is not None

    # Kept for backwards-compat with existing code that checks is_blood_type.
    @property
    def is_blood_type(self) -> bool:
        return self.swap_group_key in BLOOD_TYPE_BY_KEY

    @property
    def blood_type_key(self) -> Optional[str]:
        return self.swap_group_key if self.is_blood_type else None


def blood(blood_type_key: str, quantity: int) -> Ingredient:
    """Convenience constructor for a blood-type ingredient."""
    bt = BLOOD_TYPE_BY_KEY[blood_type_key]
    return Ingredient(
        key=blood_type_key,
        name=bt.display_name,
        quantity=quantity,
        swap_group_key=blood_type_key,
    )


def swap(group: SwapGroup, quantity: int) -> Ingredient:
    """Convenience constructor for a non-blood swap-group ingredient."""
    return Ingredient(
        key=group.key,
        name=group.display_name,
        quantity=quantity,
        swap_group_key=group.key,
    )


# ---------------------------------------------------------------------------
# Craftable intermediate items
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CraftableItem:
    """An item that can be crafted from sub-ingredients.

    The crafting tree is expanded recursively by explode_to_raw().
    Stock for craftable items is tracked separately so the calculator can
    account for already-crafted intermediates.

    Attributes:
        key: Stable snake_case identifier.
        name: Display name.
        ingredients: Sub-ingredients needed to craft 1 unit.
    """

    key: str
    name: str
    ingredients: List[Ingredient] = field(default_factory=list)


# Reagents
CLEAR_LIQUID_REAGENT = CraftableItem(
    key="clear_liquid_reagent",
    name="Clear Liquid Reagent",
    ingredients=[
        Ingredient("salt", "Salt", 1),
        Ingredient("sunrise_herb", "Sunrise Herb", 1),
        Ingredient("purified_water", "Purified Water", 1),
        swap(WEEDS_GROUP, 1),
    ],
)

PURE_POWDER_REAGENT = CraftableItem(
    key="pure_powder_reagent",
    name="Pure Powder Reagent",
    ingredients=[
        Ingredient("sugar", "Sugar", 1),
        Ingredient("silver_azalea", "Silver Azalea", 1),
        Ingredient("purified_water", "Purified Water", 1),
        swap(WEEDS_GROUP, 1),
    ],
)

# Crafted Bloods
CLOWN_BLOOD = CraftableItem(
    key="clown_blood",
    name="Clown Blood",
    ingredients=[
        blood("blood_t3", 2),  # Wolf / Rhino Blood
        Ingredient("clear_liquid_reagent", "Clear Liquid Reagent", 1),
        Ingredient("spirit_leaf", "Spirit Leaf", 1),
        Ingredient("darkness_powder", "Darkness Powder", 1),
    ],
)

SINNERS_BLOOD = CraftableItem(
    key="sinners_blood",
    name="Sinner's Blood",
    ingredients=[
        blood("blood_t2", 2),  # Goat / Deer Blood
        Ingredient("clear_liquid_reagent", "Clear Liquid Reagent", 1),
        Ingredient("bloody_tree_knot", "Bloody Tree Knot", 1),
        Ingredient("fire_powder", "Fire Powder", 1),
    ],
)

TYRANT_BLOOD = CraftableItem(
    key="tyrant_blood",
    name="Tyrant Blood",
    ingredients=[
        blood("blood_t4", 2),  # Bear / Troll / Lion Blood
        Ingredient("pure_powder_reagent", "Pure Powder Reagent", 1),
        Ingredient("monk_branch", "Monk's Branch", 1),
        Ingredient("nature_trace", "Trace of Nature", 1),
    ],
)

DIVINE_BEAST_BLOOD = CraftableItem(
    key="divine_beast_blood",
    name="Divine Beast Blood",
    ingredients=[
        blood("blood_t5", 2),  # Lizard / Kuku Bird Blood
        Ingredient("pure_powder_reagent", "Pure Powder Reagent", 1),
        Ingredient("spirit_leaf", "Spirit Leaf", 1),
        Ingredient("nature_trace", "Trace of Nature", 1),
    ],
)

WISE_MANS_BLOOD = CraftableItem(
    key="wise_man_blood",
    name="Wise Man's Blood",
    ingredients=[
        blood("blood_t1", 2),  # Fox Blood
        Ingredient("clear_liquid_reagent", "Clear Liquid Reagent", 1),
        Ingredient("monk_branch", "Monk's Branch", 1),
        Ingredient("nature_trace", "Trace of Nature", 1),
    ],
)

# Oils
OIL_OF_CORRUPTION = CraftableItem(
    key="corruption_oil",
    name="Oil of Corruption",
    ingredients=[
        Ingredient("sinners_blood", "Sinner's Blood", 1),
        Ingredient("fruit_of_nature", "Fruit of Nature", 1),
        Ingredient("spirit_leaf", "Spirit Leaf", 1),
        Ingredient("darkness_powder", "Darkness Powder", 1),
    ],
)

OIL_OF_REGENERATION = CraftableItem(
    key="regeneration_oil",
    name="Oil of Regeneration",
    ingredients=[
        Ingredient("divine_beast_blood", "Divine Beast Blood", 1),
        Ingredient("fruit_of_nature", "Fruit of Nature", 1),
        Ingredient("red_tree_lump", "Red Tree Lump", 1),
        Ingredient("rifts_dust", "Rift's Dust", 1),
    ],
)

OIL_OF_STORMS = CraftableItem(
    key="storm_oil",
    name="Oil of Storms",
    ingredients=[
        Ingredient("tyrant_blood", "Tyrant Blood", 1),
        Ingredient("fruit_of_nature", "Fruit of Nature", 1),
        Ingredient("old_tree_bark", "Old Tree Bark", 1),
        Ingredient("time_powder", "Time Powder", 1),
    ],
)

OIL_OF_FORTITUDE = CraftableItem(
    key="fortitude_oil",
    name="Oil of Fortitude",
    ingredients=[
        Ingredient("clown_blood", "Clown Blood", 1),
        Ingredient("fruit_of_nature", "Fruit of Nature", 1),
        Ingredient("monk_branch", "Monk's Branch", 1),
        Ingredient("fire_powder", "Fire Powder", 1),
    ],
)

OIL_OF_TRANQUILITY = CraftableItem(
    key="tranquility_oil",
    name="Oil of Tranquility",
    ingredients=[
        Ingredient("wise_man_blood", "Wise Man's Blood", 1),
        Ingredient("fruit_of_nature", "Fruit of Nature", 1),
        Ingredient("bloody_tree_knot", "Bloody Tree Knot", 1),
        Ingredient("earth_powder", "Earth Powder", 1),
    ],
)

# Registry: key → CraftableItem  (used by the tree exploder)
CRAFTABLES: Dict[str, CraftableItem] = {
    c.key: c
    for c in [
        CLEAR_LIQUID_REAGENT,
        PURE_POWDER_REAGENT,
        CLOWN_BLOOD,
        SINNERS_BLOOD,
        TYRANT_BLOOD,
        DIVINE_BEAST_BLOOD,
        WISE_MANS_BLOOD,
        OIL_OF_CORRUPTION,
        OIL_OF_REGENERATION,
        OIL_OF_STORMS,
        OIL_OF_FORTITUDE,
        OIL_OF_TRANQUILITY,
    ]
}


# ---------------------------------------------------------------------------
# Elixir / Draught model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Elixir:
    """One of the 4 elixirs that compose a draught."""

    key: str
    name: str
    market_id: int
    ingredients: List[Ingredient] = field(default_factory=list)


@dataclass(frozen=True)
class Draught:
    """One of the 5 draughts that compose a Harmony."""

    key: str
    name: str
    market_id: int
    elixirs: List[Elixir] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Standalone elixir model (not part of any Draught / Harmony)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StandaloneElixir:
    """An elixir tracked independently from the Harmony / Draught structure.

    Attributes:
        key: Stable snake_case identifier (used as DB key).
        name: Display name.
        ingredients: Recipe ingredients needed per 1 craft.
        target_per_harmony: How many units are needed per Harmony target.
    """

    key: str
    name: str
    ingredients: List[Ingredient] = field(default_factory=list)
    target_per_harmony: int = 3


# ---------------------------------------------------------------------------
# Draught catalogue
# ---------------------------------------------------------------------------

DRAUGHTS: List[Draught] = [
    Draught(
        key="berserk",
        name="Berserk Draught",
        market_id=0,
        elixirs=[
            Elixir(
                key="fury",
                name="Elixir of Fury",
                market_id=0,
                ingredients=[
                    Ingredient("ash_sap", "Ash Sap", 1),
                    Ingredient("dwarf_mushroom", "Dwarf Mushroom", 4),
                    blood("blood_t4", 4),
                    Ingredient("purified_water", "Purified Water", 3),
                ],
            ),
            Elixir(
                key="concentration",
                name="Elixir of Concentration",
                market_id=0,
                ingredients=[
                    Ingredient("clear_liquid_reagent", "Clear Liquid Reagent", 1),
                    Ingredient("cloud_mushroom", "Cloud Mushroom", 3),
                    blood("blood_t4", 3),
                    Ingredient("wild_plant", "Wild Plant", 2),
                ],
            ),
            Elixir(
                key="frenzy",
                name="Elixir of Frenzy",
                market_id=0,
                ingredients=[
                    Ingredient("regeneration_oil", "Oil of Regeneration", 1),
                    Ingredient("nature_trace", "Trace of Nature", 3),
                    Ingredient("clear_liquid_reagent", "Clear Liquid Reagent", 5),
                    Ingredient("cedar_sap", "Cedar Sap", 5),
                    Ingredient("ghost_mushroom", "Ghost Mushroom", 2),
                ],
            ),
            Elixir(
                key="destruction",
                name="Elixir of Destruction",
                market_id=0,
                ingredients=[
                    Ingredient("storm_oil", "Oil of Storms", 1),
                    Ingredient("clear_liquid_reagent", "Clear Liquid Reagent", 5),
                    Ingredient("nature_trace", "Trace of Nature", 3),
                    Ingredient("snowy_cedar_sap", "Snowy Cedar Sap", 7),
                    Ingredient("fire_powder", "Fire Powder", 5),
                ],
            ),
        ],
    ),
    Draught(
        key="potential",
        name="Potential Draught",
        market_id=0,
        elixirs=[
            Elixir(
                key="wind",
                name="Elixir of Wind",
                market_id=0,
                ingredients=[
                    Ingredient("wise_man_blood", "Wise Man's Blood", 1),
                    Ingredient("darkness_powder", "Darkness Powder", 2),
                    Ingredient("fortune_teller_mush", "Fortune Teller Mushroom", 5),
                    Ingredient("pine_sap", "Pine Sap", 5),
                ],
            ),
            Elixir(
                key="shock",
                name="Elixir of Shock",
                market_id=0,
                ingredients=[
                    Ingredient("clown_blood", "Clown Blood", 1),
                    Ingredient("time_powder", "Time Powder", 3),
                    Ingredient("tiger_mushroom", "Tiger Mushroom", 5),
                    Ingredient("cedar_sap", "Cedar Sap", 7),
                ],
            ),
            Elixir(
                key="spells",
                name="Elixir of Spells",
                market_id=0,
                ingredients=[
                    Ingredient("tyrant_blood", "Tyrant Blood", 1),
                    Ingredient("darkness_powder", "Darkness Powder", 2),
                    Ingredient("fire_flake_flower", "Fire Flake Flower", 5),
                    Ingredient("maple_sap", "Maple Sap", 3),
                ],
            ),
            Elixir(
                key="swiftness",
                name="Elixir of Swiftness",
                market_id=0,
                ingredients=[
                    Ingredient("divine_beast_blood", "Divine Beast Blood", 1),
                    Ingredient("darkness_powder", "Darkness Powder", 2),
                    Ingredient("arrow_mushroom", "Arrow Mushroom", 5),
                    Ingredient("birch_sap", "Birch Sap", 5),
                ],
            ),
        ],
    ),
    Draught(
        key="corruption",
        name="Corruption Draught",
        market_id=0,
        elixirs=[
            Elixir(
                key="perforation",
                name="Elixir of Perforation",
                market_id=0,
                ingredients=[
                    Ingredient("corruption_oil", "Oil of Corruption", 1),
                    Ingredient("nature_trace", "Trace of Nature", 2),
                    Ingredient("clear_liquid_reagent", "Clear Liquid Reagent", 4),
                    Ingredient("pine_sap", "Pine Sap", 5),
                    Ingredient("braggart_mushroom", "Braggart Mushroom", 5),
                ],
            ),
            Elixir(
                key="death",
                name="Elixir of Death",
                market_id=0,
                ingredients=[
                    Ingredient("tranquility_oil", "Oil of Tranquility", 1),
                    Ingredient("nature_trace", "Trace of Nature", 2),
                    Ingredient("clear_liquid_reagent", "Clear Liquid Reagent", 6),
                    Ingredient("ash_sap", "Ash Sap", 7),
                    Ingredient("ancestral_mushroom", "Ancestral Mushroom", 2),
                ],
            ),
            Elixir(
                key="grim_reaper",
                name="Grim Reaper's Elixir",
                market_id=0,
                ingredients=[
                    Ingredient("fortitude_oil", "Oil of Fortitude", 1),
                    Ingredient("nature_trace", "Trace of Nature", 4),
                    Ingredient("pure_powder_reagent", "Pure Powder Reagent", 4),
                    Ingredient("monk_branch", "Monk's Branch", 2),
                    Ingredient("sky_mushroom", "Sky Mushroom", 2),
                ],
            ),
            Elixir(
                key="draining",
                name="Elixir of Draining",
                market_id=0,
                ingredients=[
                    Ingredient("fortitude_oil", "Oil of Fortitude", 1),
                    Ingredient("nature_trace", "Trace of Nature", 2),
                    Ingredient("clear_liquid_reagent", "Clear Liquid Reagent", 4),
                    Ingredient("birch_sap", "Birch Sap", 4),
                    Ingredient("swelling_mushroom", "Swelling Mushroom", 3),
                ],
            ),
        ],
    ),
    Draught(
        key="adaptation",
        name="Adaptation Draught",
        market_id=0,
        elixirs=[
            Elixir(
                key="defense",
                name="Defense Elixir",
                market_id=0,
                ingredients=[
                    Ingredient("clear_liquid_reagent", "Clear Liquid Reagent", 1),
                    blood("blood_t2", 5),
                    Ingredient("ash_sap", "Ash Sap", 6),
                    Ingredient("purified_water", "Purified Water", 3),
                ],
            ),
            Elixir(
                key="life",
                name="Elixir of Life",
                market_id=0,
                ingredients=[
                    Ingredient("pure_powder_reagent", "Pure Powder Reagent", 1),
                    Ingredient("silver_azalea", "Silver Azalea", 3),
                    Ingredient("life_potion_s", "Life Potion (S)", 3),
                    blood("blood_t1", 5),
                ],
            ),
            Elixir(
                key="helix",
                name="Helix Elixir",
                market_id=0,
                ingredients=[
                    Ingredient("thuja_sap", "Thuja Sap", 6),
                    Ingredient("fire_powder", "Fire Powder", 2),
                    Ingredient("monk_branch", "Monk's Branch", 3),
                    Ingredient("purified_water", "Purified Water", 3),
                    Ingredient("clown_blood", "Clown Blood", 2),
                ],
            ),
            Elixir(
                key="endurance",
                name="Elixir of Endurance",
                market_id=0,
                ingredients=[
                    Ingredient("pure_powder_reagent", "Pure Powder Reagent", 1),
                    Ingredient("dwarf_mushroom", "Dwarf Mushroom", 2),
                    blood("blood_t4", 4),
                    Ingredient("birch_sap", "Birch Sap", 5),
                ],
            ),
        ],
    ),
    Draught(
        key="fury",
        name="Fury Draught",
        market_id=0,
        elixirs=[
            Elixir(
                key="assassination",
                name="Elixir of Assassination",
                market_id=0,
                ingredients=[
                    Ingredient("regeneration_oil", "Oil of Regeneration", 1),
                    Ingredient("nature_trace", "Trace of Nature", 2),
                    Ingredient("pure_powder_reagent", "Pure Powder Reagent", 5),
                    Ingredient("red_tree_lump", "Red Tree Lump", 2),
                    Ingredient("clown_mushroom", "Clown Mushroom", 4),
                ],
            ),
            Elixir(
                key="detection",
                name="Elixir of Detection",
                market_id=0,
                ingredients=[
                    Ingredient("storm_oil", "Oil of Storms", 1),
                    Ingredient("nature_trace", "Trace of Nature", 3),
                    Ingredient("pure_powder_reagent", "Pure Powder Reagent", 6),
                    Ingredient("old_tree_bark", "Old Tree Bark", 2),
                    Ingredient("truffle_mushroom", "Truffle Mushroom", 3),
                ],
            ),
            Elixir(
                key="carnage",
                name="Elixir of Carnage",
                market_id=0,
                ingredients=[
                    Ingredient("corruption_oil", "Oil of Corruption", 1),
                    Ingredient("nature_trace", "Trace of Nature", 3),
                    Ingredient("pure_powder_reagent", "Pure Powder Reagent", 7),
                    Ingredient("spirit_leaf", "Spirit Leaf", 2),
                    Ingredient("tiger_mushroom", "Tiger Mushroom", 2),
                ],
            ),
            Elixir(
                key="sky",
                name="Elixir of Sky",
                market_id=0,
                ingredients=[
                    Ingredient("tranquility_oil", "Oil of Tranquility", 1),
                    Ingredient("nature_trace", "Trace of Nature", 4),
                    Ingredient("pure_powder_reagent", "Pure Powder Reagent", 6),
                    Ingredient("bloody_tree_knot", "Bloody Tree Knot", 2),
                    Ingredient("emperor_mushroom", "Emperor Mushroom", 1),
                ],
            ),
        ],
    ),
]

DRAUGHT_BY_KEY: Dict[str, Draught] = {d.key: d for d in DRAUGHTS}


# ---------------------------------------------------------------------------
# Standalone elixirs catalogue (tracked separately from Harmony)
# ---------------------------------------------------------------------------

STANDALONE_ELIXIRS: List[StandaloneElixir] = [
    StandaloneElixir(
        key="semihumano",
        name="Demihuman Hunt Elixir",
        target_per_harmony=3,
        ingredients=[
            Ingredient("sinners_blood", "Sinner's Blood", 1),
            Ingredient("arrow_mushroom", "Arrow Mushroom", 4),
            Ingredient("darkness_powder", "Darkness Powder", 3),
            Ingredient("fir_sap", "Fir Sap", 4),
        ],
    ),
    StandaloneElixir(
        key="voluntad",
        name="Elixir of Will",
        target_per_harmony=3,
        ingredients=[
            Ingredient("clear_liquid_reagent", "Clear Liquid Reagent", 1),
            Ingredient("sunrise_herb", "Sunrise Herb", 4),
            blood("blood_t3", 6),  # Wolf Blood
            Ingredient("purified_water", "Purified Water", 3),
        ],
    ),
    StandaloneElixir(
        key="grifo",
        name="Griffon's Elixir",
        target_per_harmony=3,
        ingredients=[
            Ingredient("griffon_claw", "Griffon Claw", 1),
            Ingredient("purified_water", "Purified Water", 3),
            Ingredient("cedar_sap", "Cedar Sap", 6),
            Ingredient("nature_trace", "Trace of Nature", 3),
            Ingredient("sinners_blood", "Sinner's Blood", 2),
        ],
    ),
    StandaloneElixir(
        key="caza_humano",
        name="Human Hunt Elixir",
        target_per_harmony=3,
        ingredients=[
            Ingredient("clown_blood", "Clown Blood", 1),
            Ingredient("fortune_teller_mush", "Fortune Teller Mushroom", 4),
            Ingredient("darkness_powder", "Darkness Powder", 3),
            Ingredient("maple_sap", "Maple Sap", 4),
        ],
    ),
]

STANDALONE_ELIXIR_BY_KEY: Dict[str, StandaloneElixir] = {
    e.key: e for e in STANDALONE_ELIXIRS
}


# ---------------------------------------------------------------------------
# Helpers for stock editors
# ---------------------------------------------------------------------------


def all_blood_member_keys() -> List[Tuple[str, str, str]]:
    """Return (blood_type_key, member_key, member_name) for every raw blood.

    NOTE: For tooltip/reference display only. Blood stock is tracked per tier
    (blood_t1 .. blood_t5), not per individual animal.
    """
    return [
        (bt.key, mk, name)
        for bt in BLOOD_TYPES
        for name, mk in zip(bt.members, bt.member_keys)
    ]


def all_swap_member_keys() -> List[Tuple[str, str, str]]:
    """Return (group_key, member_key, member_name) for non-blood swap groups."""
    return [
        (WEEDS_GROUP.key, mk, name)
        for name, mk in zip(WEEDS_GROUP.members, WEEDS_GROUP.member_keys)
    ]


# ---------------------------------------------------------------------------
# Crafting tree explosion
# ---------------------------------------------------------------------------


def _count_demand(
    key: str,
    qty: int,
    demand: Dict[str, int],
    _visited: frozenset[str],
) -> None:
    """Recursively accumulate total demand for every craftable in the tree."""
    if key not in CRAFTABLES or key in _visited:
        return
    demand[key] = demand.get(key, 0) + qty
    new_visited = _visited | {key}
    for sub in CRAFTABLES[key].ingredients:
        _count_demand(sub.key, sub.quantity * qty, demand, new_visited)


def explode_to_raw(
    top_level_needs: Dict[str, int],
    stock: Dict[str, int],
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Expand a dict of top-level ingredient needs into raw material totals.

    Uses a two-pass algorithm:
    1. Walk the full tree to count gross demand for every craftable.
    2. For each craftable (leaves first), subtract available stock to get
       net units to craft.

    Args:
        top_level_needs: {ingredient_key: total_qty_needed}.
        stock: Full material stock {key: qty}, including craftable intermediates.

    Returns:
        Tuple of:
        - raw_totals: {raw_key: qty} — non-craftable items only.
        - crafted_totals: {craftable_key: qty_to_craft}.
    """
    # --- Pass 1: count gross demand for every craftable in the tree ---
    gross: Dict[str, int] = {}
    for key, qty in top_level_needs.items():
        if qty > 0:
            _count_demand(key, qty, gross, frozenset())

    # --- Pass 2: resolve net crafts needed, deepest nodes first ---
    net: Dict[str, int] = {}
    remaining_demand: Dict[str, int] = dict(gross)

    def _depth(key: str, _seen: frozenset[str] = frozenset()) -> int:
        if key not in CRAFTABLES or key in _seen:
            return 0
        return 1 + max(
            (_depth(sub.key, _seen | {key}) for sub in CRAFTABLES[key].ingredients),
            default=0,
        )

    sorted_keys = sorted(gross.keys(), key=_depth, reverse=True)

    for key in sorted_keys:
        needed = remaining_demand.get(key, 0)
        have = stock.get(key, 0)
        to_craft = max(0, needed - have)
        net[key] = to_craft
        saved = needed - to_craft
        if saved > 0:
            for sub in CRAFTABLES[key].ingredients:
                if sub.key in remaining_demand:
                    remaining_demand[sub.key] = max(
                        0, remaining_demand[sub.key] - sub.quantity * saved
                    )

    # --- Pass 3: accumulate raw material totals ---
    raw_totals: Dict[str, int] = {}

    for key, qty in top_level_needs.items():
        if qty <= 0:
            continue
        if key not in CRAFTABLES:
            raw_totals[key] = raw_totals.get(key, 0) + qty

    for key, to_craft in net.items():
        if to_craft <= 0:
            continue
        for sub in CRAFTABLES[key].ingredients:
            if sub.key not in CRAFTABLES:
                raw_totals[sub.key] = (
                    raw_totals.get(sub.key, 0) + sub.quantity * to_craft
                )

    raw_totals = {k: v for k, v in raw_totals.items() if v > 0}
    crafted_totals = {k: v for k, v in net.items() if v > 0}
    return raw_totals, crafted_totals


# Quantity of each elixir consumed per single draught craft.
ELIXIRS_PER_DRAUGHT = 3


# ---------------------------------------------------------------------------
# Materials calculation
# ---------------------------------------------------------------------------


def calculate_materials_needed(
    harmony_count: int,
    elixir_stock: Dict[str, int],
    material_stock: Dict[str, int] = None,
    draught_stock: Dict[str, int] = None,
) -> Tuple[Dict[str, Dict], Dict[str, int]]:
    """Calculate per-elixir crafts needed and direct ingredient totals.

    Args:
        harmony_count: Target number of Harmonies to produce.
        elixir_stock: Current stock per elixir {elixir_key: qty}.
        material_stock: Current stock per material {key: qty}.
        draught_stock: Current stock per draught {draught_key: qty}.

    Returns:
        Tuple of:
        - per_elixir: {elixir_key: {"crafts_needed", "elixir_missing",
                                    "elixir_target", "materials"}}
        - totals: {ingredient_key: total_qty_needed_across_all_elixirs}
    """
    if material_stock is None:
        material_stock = {}
    if draught_stock is None:
        draught_stock = {}

    per_elixir: Dict[str, Dict] = {}
    totals: Dict[str, int] = {}

    base_elixir_target = harmony_count * ELIXIRS_PER_DRAUGHT

    for draught in DRAUGHTS:
        draughts_have = draught_stock.get(draught.key, 0)
        elixirs_covered = draughts_have * ELIXIRS_PER_DRAUGHT
        effective_target = max(0, base_elixir_target - elixirs_covered)

        for elixir in draught.elixirs:
            stock = elixir_stock.get(elixir.key, 0)
            elixir_missing = max(0, effective_target - stock)
            ing_needs: Dict[str, int] = {}

            for ing in elixir.ingredients:
                total = ing.quantity * elixir_missing
                ing_needs[ing.key] = total
                totals[ing.key] = totals.get(ing.key, 0) + total

            per_elixir[elixir.key] = {
                "crafts_needed": elixir_missing,
                "elixir_missing": elixir_missing,
                "elixir_target": effective_target,
                "materials": ing_needs,
            }

    return per_elixir, totals


def calculate_standalone_materials_needed(
    harmony_count: int,
    elixir_stock: Dict[str, int],
) -> Dict[str, Dict]:
    """Calculate per-standalone-elixir crafts needed and ingredient totals.

    Args:
        harmony_count: Target number of Harmonies (used to scale target).
        elixir_stock: Current stock per elixir {elixir_key: qty}.

    Returns:
        {elixir_key: {"crafts_needed", "elixir_missing", "elixir_target",
                      "materials", "name"}}
    """
    result: Dict[str, Dict] = {}
    for elixir in STANDALONE_ELIXIRS:
        target = elixir.target_per_harmony * harmony_count
        stock = elixir_stock.get(elixir.key, 0)
        missing = max(0, target - stock)
        ing_needs: Dict[str, int] = {
            ing.key: ing.quantity * missing for ing in elixir.ingredients
        }
        result[elixir.key] = {
            "crafts_needed": missing,
            "elixir_missing": missing,
            "elixir_target": target,
            "materials": ing_needs,
            "name": elixir.name,
        }
    return result

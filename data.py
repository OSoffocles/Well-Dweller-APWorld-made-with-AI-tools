"""Names, ids and static tables for the Well Dweller world."""
from typing import NamedTuple

from BaseClasses import ItemClassification as IC

from .game_data import PICKUPS, LEVERS_AND_VESSELS


class ItemData(NamedTuple):
    id: int
    classification: IC
    count: int
    group: str


TRINKETS = [
    "Rusty Fork", "Hunter's Locket", "Scrap of Fabric", "Hair Pin", "Golden Needle", "Fish Hook",
    "Bundle of Hair", "Broken Bell", "Melted Candle", "Spider's Web", "Silver Spoon", "Burnt Shoelace",
    "Molar Tooth", "Postage Stamp", "Nails with Twine", "Pearl Jewelry", "Blue Bow", "Doll's Head",
    "Bird-Shaped Button", "Rusted Compass", "Insect Wing", "Ember Vial", "Paper Clip With String",
    "Cracked Marble", "Glass Shard", "Tiny Witch Sculpture", "Bottle Cap", "Skull Keychain", "Glass Eye",
    "Rusted Thimble", "Weathered Coin", "Silver Ring",
]

P, U, F = IC.progression, IC.useful, IC.filler

ITEMS: dict[str, ItemData] = {
    # abilities
    "Matchstick": ItemData(1, P, 1, "Abilities"),
    "Slingshot": ItemData(2, P, 1, "Abilities"),
    "Progressive Climb": ItemData(3, P, 2, "Abilities"),
    "Wind Ride": ItemData(4, P, 1, "Abilities"),
    "Hover": ItemData(5, P, 1, "Abilities"),
    "Wall Sling": ItemData(6, P, 1, "Abilities"),
    "Soar": ItemData(7, P, 1, "Abilities"),
    "Water Vessel": ItemData(8, P, 1, "Abilities"),
    "Torpedo": ItemData(9, P, 1, "Abilities"),
    "Tent Travel": ItemData(10, P, 1, "Abilities"),  # used by the tent and Drains logic
    # key items
    "Golden Gate Key": ItemData(20, P, 1, "Key Items"),
    "Elevator Part": ItemData(21, P, 3, "Key Items"),
    "Pearl": ItemData(22, P, 3, "Key Items"),
    "Golden Feather": ItemData(23, P, 7, "Key Items"),
    "Flight Time Upgrade": ItemData(24, P, 3, "Key Items"),
    "Looter Part": ItemData(25, P, 4, "Key Items"),
    "Food": ItemData(26, P, 1, "Key Items"),
    "Witch Burning Ticket": ItemData(27, P, 1, "Key Items"),
    "Spirit": ItemData(28, P, 20, "Key Items"),
    "Spirit Fragment": ItemData(29, P, 5, "Key Items"),
    # upgrades and resources
    "Workshop Token": ItemData(40, U, 27, "Upgrades"),
    "Trinket Point": ItemData(41, U, 59, "Upgrades"),
    "Oil Vial": ItemData(42, U, 2, "Upgrades"),
    "Flaming Vessel Upgrade": ItemData(43, U, 2, "Upgrades"),
    "The Queen's Coin": ItemData(44, U, 1, "Upgrades"),
    "Mysterious Markings": ItemData(45, U, 1, "Upgrades"),
    "Hat": ItemData(46, F, 1, "Upgrades"),
    # filler
    "Currency": ItemData(60, F, 0, "Filler"),
    # boons and traps (filler shares)
    "Big Currency": ItemData(70, F, 0, "Boons"),
    "Full Heal": ItemData(71, F, 0, "Boons"),
    "Vial Refill": ItemData(72, F, 0, "Boons"),
    "Thief": ItemData(80, IC.trap, 0, "Traps"),
    "Bruise": ItemData(81, IC.trap, 0, "Traps"),
    "Spill": ItemData(82, IC.trap, 0, "Traps"),
}
for i, name in enumerate(TRINKETS):
    ITEMS[name] = ItemData(100 + i, P, 1, "Trinkets")

# Tents (save points / teleport targets) that can be unlocked by option or as items, in item-id order.
# (map key, room) - Queen's Castle tents are left out: they would skip the Golden Feather gate.
TENTS = [
    ('39,37', 'AB_02', 'The Bog'),
    ('27,36', 'AB_12', 'The Bog'),
    ('35,29', 'AB_19', 'The Bog'),
    ('70,41', 'AC_03', 'Desiccated Castle'),
    ('79.50,51', 'AC_19', 'Desiccated Castle'),
    ('106.50,53', 'AC_33', 'Desiccated Castle'),
    ('80,27', 'AD_05', 'Gravenvalley'),
    ('104,35', 'AE_19', 'The Depths'),
    ('63,13', 'AF_05', 'Autumn Forest'),
    ('78,9', 'AF_20', 'Autumn Forest'),
    ('45,13', 'AG_07', 'Lookout Tower'),
    ('47,3', 'AG_30', 'Lookout Tower'),
    ('63.50,26', 'AH_05', "Hunter's Cabin"),
    ('66,20', 'AH_16', "Hunter's Cabin"),
    ('92,20', 'AK_02', 'The Docks'),
    ('104,23', 'AK_21', 'The Docks'),
    ('88,16', 'AK_34', 'The Docks'),
    ('84.50,37', 'AL_22', 'Midnight Drench'),
    ('77,43', 'AL_35', 'Midnight Drench'),
    ('49.50,23', 'AN_04', 'Night Garden'),
    ('54.50,32', 'AN_14', 'Night Garden'),
    ('52,18', 'AN_27', 'Night Garden'),
    ('52,38', 'AP_07', 'The Drains'),
    ('65,35', 'AP_31', 'The Drains'),
    ('50,50', 'AT_04', 'Burial Vault'),
    ('32,46', 'AT_17', 'Burial Vault'),
    ('12,32', 'AU_04', "Dollmaker's House"),
    ('21,43', 'AU_20', "Dollmaker's House"),
    ('94,46', 'AW_01', 'Webdrench Inn'),
    ('95,38', 'AW_11', 'Webdrench Inn'),
    ('103,48', 'AW_27', 'Webdrench Inn'),
]


def tent_item_name(room: str, area: str) -> str:
    return f"Tent: {area} ({room})"


TENT_ITEMS = [tent_item_name(room, area) for _, room, area in TENTS]
STARTING_TENT = tent_item_name("AN_04", "Night Garden")
# Region a tent puts you in when you teleport there (outer part of the area, so the logic never assumes
# more than the tent gives). Castle tents are left out of the logic until their side is known.
TENT_REGION = {
    "AB": "The Bog", "AD": "Gravenvalley", "AE": "The Depths", "AF": "Autumn Forest", "AG": "Lookout Tower",
    "AH": "Hunter's Cabin", "AK": "The Docks", "AL": "Midnight Drench", "AN": "Night Garden", "AP": "The Drains",
    "AT": "Burial Vault", "AU": "Dollmaker's House", "AW": "Webdrench Inn",
}
# Tents that sit in a deeper part of their area than the area's first region.
TENT_ROOM_REGION = {"AP_31": "Drains Depths", "AN_14": "Night Garden Lower", "AN_27": "Night Garden Upper",
                    "AW_01": "Webdrench Inn Lower", "AW_27": "Webdrench Inn Lower"}   # the East elevator part side, below the Wind Ride gaps
# The lower Night Garden (towards the Groundskeeper, Hunter's Cabin and the Drains) is behind the gate that the
# AN_06 lever opens. With lever items that gate needs "Lever: Night Garden (AN_06)".
NG_LOWER_ROOMS = {"AN_08", "AN_09", "AN_10", "AN_11", "AN_12", "AN_13", "AN_14", "AN_16", "AN_17", "AN_18", "AN_23",
                  "AN_24", "AN_25", "AN_50", "AN_Boss"}
NG_LOWER_NAMED = {"Night Garden: The Groundskeeper"}
NG_GATE_LEVER = "Lever: Night Garden (AN_06)"
WEBDRENCH_GATE_LEVER = "Lever: Webdrench Inn (AW_05)"
WEBDRENCH_LOWER_ROOMS = {"AW_01", "AW_02", "AW_03", "AW_04", "AW_27", "AW_28", "AW_29", "AW_30"}
WEBDRENCH_LOWER_NAMED = {"Webdrench Inn: Golden Feather (Inn Exit)"}
NG_AN04_LEVER = "Lever: Night Garden (AN_04)"
# Past the AN_05 gate (opens when its enemy is killed with the Matchstick): AN_05/AN_06 and the rooms above.
NG_EAST_ROOMS = {"AN_05", "AN_06"}
# Above AN_05/AN_06 (up there: Climb + Slingshot + Hover, or Soar).
NG_UPPER_ROOMS = {"AN_26", "AN_27", "AN_28", "AN_29", "AN_30", "AN_31", "AN_32"}
# AN_40 (above AN_01/AN_02): an invisible wall that its own lever controls blocks the way up from below.
NG_AN40_LEVER = "Lever: Night Garden (AN_40)"
# The AN_04 lever sits on the lower side of its gate.
NG_LOWER_NAMED_LOCS = {"Night Garden: Lever (AN_04)"}
# Areas where you can't move around after teleporting to their tent without these items (testers refine this).
TENT_AREA_NEEDS: dict[str, tuple[str, ...]] = {"The Depths": ("Water Vessel",)}
for i, name in enumerate(TENT_ITEMS):
    ITEMS[name] = ItemData(200 + i, U, 0, "Tents")   # added to the pool only with tent_unlocks: shuffled

# Highest forge level per trinket (upgrade_list index order, from a 100% save); level 1 = not upgraded.
TRINKET_INDEX_ORDER = [
    "Skull Keychain", "Tiny Witch Sculpture", "Bird-Shaped Button", "Hunter's Locket", "Rusty Fork", "Nails with Twine",
    "Scrap of Fabric", "Molar Tooth", "Fish Hook", "Glass Shard", "Pearl Jewelry", "Paper Clip With String",
    "Weathered Coin", "Postage Stamp", "Doll's Head", "Cracked Marble", "Silver Ring", "Broken Bell", "Rusted Thimble",
    "Bundle of Hair", "Bottle Cap", "Glass Eye", "Spider's Web", "Silver Spoon", "Melted Candle", "Ember Vial",
    "Rusted Compass", "Golden Needle", "Insect Wing", "Hair Pin", "Blue Bow", "Burnt Shoelace",
]
TRINKET_MAX_LEVEL = dict(zip(TRINKET_INDEX_ORDER, [3, 1, 3, 1, 3, 3, 3, 1, 2, 1, 1, 3, 3, 1, 1, 3, 3, 1, 2, 1, 2, 1, 1, 1,
                                                    3, 1, 1, 3, 1, 2, 1, 1]))
UPGRADABLE_TRINKETS = [t for t in TRINKET_INDEX_ORDER if TRINKET_MAX_LEVEL[t] > 1]
UPGRADE_ITEMS: dict[str, int] = {}      # item name -> copies (forge_checks)
for i, t in enumerate(TRINKET_INDEX_ORDER):
    if TRINKET_MAX_LEVEL[t] > 1:
        ITEMS[f"Trinket Upgrade: {t}"] = ItemData(500 + i, U, 0, "Trinket Upgrades")
        UPGRADE_ITEMS[f"Trinket Upgrade: {t}"] = TRINKET_MAX_LEVEL[t] - 1

ITEM_NAME_TO_ID = {name: data.id for name, data in ITEMS.items()}
ITEM_GROUPS: dict[str, set[str]] = {}
for name, data in ITEMS.items():
    ITEM_GROUPS.setdefault(data.group, set()).add(name)

FILLER_ITEM = "Currency"


class LocData(NamedTuple):
    id: int
    region: str
    group: str
    rule: tuple = ()     # gate tags, see rules.py
    key: str = ""        # save key that marks the check, if any


# Named locations: bosses, ability eggs, NPC rewards, shop, nest, post-game.
NAMED: dict[str, LocData] = {}


def _named(nid: int, name: str, region: str, group: str, rule: tuple = (), key: str = "") -> None:
    NAMED[name] = LocData(nid, region, group, rule, key)


# bosses (all need the Matchstick)
_named(1, "Night Garden: The Groundskeeper", "Night Garden", "Bosses", ("boss",), "groundskeeper")
_named(2, "The Bog: The Swarm", "Bog Interior", "Bosses", ("boss",), "swarm_boss")
_named(3, "Gravenvalley: Lida the Terrible", "Gravenvalley Witch Burning", "Bosses", ("boss",))
_named(4, "The Drains: Lady of the Drains", "Midnight Drench", "Bosses", ("boss",), "drain_boss")
_named(5, "The Docks: Creature from the Deep", "The Docks", "Bosses", ("boss", "pearls"))
_named(6, "The Depths: The Colony", "The Depths", "Bosses", ("boss", "torpedo"))
_named(7, "Lookout Tower: Starsinger", "Lookout Tower", "Bosses", ("boss", "flight3"), "moon_boss")
_named(8, "Autumn Forest: Forest King", "Forest King", "Bosses", ("boss",), "king_boss")
_named(9, "Dollmaker's House: The Dollmaker", "Dollmaker's House", "Bosses", ("boss",))
_named(10, "Burial Vault: Gravedigger", "Burial Vault", "Bosses", ("boss",), "gravedigger")
_named(11, "Midnight Drench: Shrine of the Seven Sons", "Midnight Drench", "Bosses", ("boss",), "sevensons")
_named(12, "Queen's Castle: Metal Doll", "Queen's Throne", "Bosses", ("boss",))
# ability eggs and abilities from NPCs
_named(20, "Hunter's Cabin: Slingshot Egg", "Hunter's Cabin", "Abilities", (), "wake_sling")
_named(21, "The Bog: Climb Egg", "Bog Interior", "Abilities", ("boss",), "wake_climb")
_named(22, "The Drains: Wind Ride Egg", "Drains Depths", "Abilities", (), "wake_wind")
_named(23, "Desiccated Castle: Hover Egg", "Desiccated Castle Lower", "Abilities", ("slingshot", "climb"), "wake_hover")
_named(24, "Night Garden: Tent Travel", "Night Garden", "Abilities", ("climb",), "tent_travel")
_named(25, "The Docks: Barge (Water Vessel)", "The Docks", "Abilities", ("boss", "pearls"))
_named(26, "The Depths: Barge (Endless Climb)", "The Depths", "Abilities", ("boss", "torpedo"))
_named(27, "Dollmaker's House: Magda (Wall Sling)", "Dollmaker's House", "Abilities", ("boss",), "wake_wsling")
# key items from the world / NPCs
_named(40, "Hunter's Cabin: Food", "Hunter's Cabin Upper", "Key Items", (), "cabin_food")
_named(41, "Gravenvalley: Witch Burning Ticket", "Gravenvalley Interior", "Key Items", (), "witch_ticket")
_named(42, "Autumn Forest: Whisper (Golden Gate Key)", "Whisper's Hut", "Key Items", (), "find_looter_start")
_named(43, "Autumn Forest: Whisper (Looter Feather)", "Whisper's Hut", "Key Items", ("looter4",))
_named(44, "Midnight Drench: Golden Feather (Willow's Friends)", "Midnight Drench", "Key Items", ("boss",), "feather_drain")
_named(45, "Lookout Tower: Golden Feather (Starsinger)", "Lookout Tower", "Key Items", ("boss", "flight3"))
_named(46, "Autumn Forest: Golden Feather (Forest King)", "Forest King", "Key Items", ("boss",))
_named(47, "Burial Vault: Golden Feather (Squinton)", "Burial Vault", "Key Items", ("boss",))
_named(48, "Webdrench Inn: Golden Feather (Inn Exit)", "Webdrench Inn", "Key Items", (), "feather_web")
_named(49, "Midnight Drench: Golden Feather (Seven Sons)", "Midnight Drench", "Key Items", ("boss",))
# post-game
_named(60, "Queen's Castle: The Queen's Coin", "Queen's Chamber", "Post-game")
_named(61, "Queen's Castle: Soar (Trinket Door)", "Queen's Chamber", "Post-game", ("trinkets32",), "wake_fly")
_named(62, "Queen's Castle: Mysterious Markings", "Queen's Chamber", "Post-game", ("soar",))
_named(63, "Dollmaker's House: Spirit Fragment", "Dollmaker's House", "Post-game", ("soar",), "shard_dh")
_named(64, "Night Garden: Spirit Fragment", "Night Garden", "Post-game", ("soar",), "shard_garden")
_named(65, "Autumn Forest: Spirit Fragment", "Autumn Forest", "Post-game", ("soar",), "shard_fall")
_named(66, "The Docks: Spirit Fragment", "The Docks", "Post-game", ("soar",), "dock_frag")
_named(67, "Desiccated Castle: Spirit Fragment", "Desiccated Castle Lower", "Post-game", ("soar",), "shard_castle")

SHOP = [  # (name, region) — Looter's shop in any tent
    "Bottle Cap", "Skull Keychain", "Glass Eye", "Rusted Thimble", "Weathered Coin", "Silver Ring",
    "Oil Vial", "Flaming Vessel Upgrade 1", "Flaming Vessel Upgrade 2",
]
# Vanilla shop prices in the shop's own order (o_looter_popupshop cost_array): the 6 trinkets, Trinket Point (each),
# Flaming Vessel Upgrade (each, assumed the same both times), Oil Vial.
SHOP_ENTRIES = ["Bottle Cap", "Skull Keychain", "Glass Eye", "Rusted Thimble", "Weathered Coin", "Silver Ring",
                "Trinket Point", "Flaming Vessel Upgrade", "Oil Vial"]
VANILLA_SHOP_COSTS = [250, 350, 450, 550, 600, 800, 250, 750, 2000]
# Estimated currency (at 1x) a normal pass through each region gives: enemies and vessels. Placeholder values until
# currency_log.txt from test runs gives real numbers (kept low on purpose until then). The logic counts 75% of the regions you can reach.
CURRENCY_ESTIMATE: dict[str, int] = {
    "Night Garden": 150, "Night Garden East": 75, "Night Garden Upper": 125, "Night Garden Lower": 150,
    "Hunter's Cabin": 75, "Hunter's Cabin Upper": 75, "The Bog": 125, "Bog Interior": 125,
    "Gravenvalley": 125, "Gravenvalley Interior": 125, "Gravenvalley Witch Burning": 0, "The Drains": 125,
    "Drains Depths": 125, "Midnight Drench": 150, "Desiccated Castle West": 125, "Desiccated Castle East": 125,
    "Desiccated Castle Lower": 125, "The Docks": 125, "Whisper's Hut": 0, "The Depths": 125, "Autumn Forest": 150,
    "Forest King": 50, "Lookout Tower": 125, "Dollmaker's House": 125, "Burial Vault": 125, "Webdrench Inn": 125, "Webdrench Inn Lower": 50,
    "Queen's Castle": 150, "Queen's Throne": 0, "Queen's Chamber": 0,
}
CURRENCY_SHARE = 0.75
for i, item in enumerate(SHOP):
    _named(100 + i, f"Looter's Shop: {item}", "Night Garden", "Shop", ("tentexit",))
MAX_SHOP_POINT_CHECKS = 100   # the shop sells 100 trinket points
for i in range(MAX_SHOP_POINT_CHECKS):
    # ids 120-139 for the first 20 (kept from 0.1), 500+ for the rest
    _named(120 + i if i < 20 else 480 + i, f"Looter's Shop: Trinket Point {i + 1}", "Night Garden", "Shop Trinket Points",
           ("tentexit",))
for i in range(20):
    _named(200 + i, f"Spirit Nest: Reward {i + 1}", "Night Garden", "Spirit Nest", (f"spirits{i + 1}",))
FORGE_STEPS = 26
for i in range(FORGE_STEPS):
    # Willow's workshop is in every tent from the start; each forge purchase is a check (the upgrade itself
    # comes from the multiworld as a "Trinket Upgrade" item)
    _named(300 + i, f"Forge: Upgrade {i + 1}", "Night Garden", "Forge", (f"tokens{i + 1}", "upgradable", "tentexit"))
TIME_TRIAL_AREAS = ["The Bog", "Night Garden", "Gravenvalley", "Desiccated Castle", "Midnight Drench",
                    "The Docks", "Hunter's Cabin", "Autumn Forest", "Dollmaker's House", "The Drains"]
TIME_TRIAL_REGION = {"The Bog": "Bog Interior", "Night Garden": "Night Garden", "Gravenvalley": "Gravenvalley Interior",
                     "Desiccated Castle": "Desiccated Castle Lower", "Midnight Drench": "Midnight Drench",
                     "The Docks": "The Docks", "Hunter's Cabin": "Hunter's Cabin Upper", "Autumn Forest": "Autumn Forest",
                     "Dollmaker's House": "Dollmaker's House", "The Drains": "Drains Depths"}
for i, area in enumerate(TIME_TRIAL_AREAS):
    _named(400 + i, f"{area}: Time Trial", TIME_TRIAL_REGION[area], "Time Trials",
           ("climb_plus",) if area == "Night Garden" else ())

# Region for pickups by area (conservative interiors, see rules.py).
AREA_REGION = {
    "The Well": "The Well", "Night Garden": "Night Garden", "Hunter's Cabin": "Hunter's Cabin Upper",
    "The Bog": "Bog Interior", "Gravenvalley": "Gravenvalley Interior", "The Drains": "Drains Depths",
    "Midnight Drench": "Midnight Drench", "Desiccated Castle": "Desiccated Castle Lower",
    "The Docks": "The Docks", "The Depths": "The Depths", "Autumn Forest": "Autumn Forest",
    "Lookout Tower": "Lookout Tower", "Dollmaker's House": "Dollmaker's House", "Burial Vault": "Burial Vault",
    "Webdrench Inn": "Webdrench Inn", "Queen's Castle": "Queen's Castle",
}
# AP_06/AP_16: Drains rooms before the AP_08 gap; r_Well3: bottom of the Well (chase, Drains or Bog side)
ROOM_REGION = {"AP_06": "The Drains", "AP_16": "The Drains", "r_Well3": "The Bog",
               # Hunter's Cabin rooms reached with only the Matchstick (Logic Test, 2026-10-05)
               "AH_02": "Hunter's Cabin", "AH_08": "Hunter's Cabin", "AH_10": "Hunter's Cabin", "AH_11": "Hunter's Cabin"}
# Night Garden rooms walked with only the Matchstick in early test runs; other Night Garden rooms
# need at least Climb until their exact gates are known.
NIGHT_GARDEN_EARLY = {"AN_01", "AN_02", "AN_03", "AN_04", "AN_05", "AN_06", "AN_08", "AN_09", "AN_10",
                      "AN_11", "AN_12", "AN_13", "AN_14", "AN_16", "AN_17", "AN_18", "AN_Boss"}
LOOTER_ROOMS = {"AD_39": (), "AC_40": ("vert",), "AP_35": ("windride_or_vert",), "AB_42": ("vert",)}
FLIGHT_ROOMS = {"AG_11": "flight0", "AG_17": "flight1", "AG_24": "flight2"}

# Per-location extra rules found in testing.
LOCATION_TAGS: dict[str, tuple[str, ...]] = {
    "Night Garden: Spirit (AN_14)": ("height",),   # out of reach from the AN_14 tent floor
    "Night Garden: Lever (AN_12)": ("height",),
    "Night Garden: Lever (AN_16)": ("height",),
    "Night Garden: Vessel (AN_04)": ("height",),   # high up in the tent room
    # behind the door the Night Garden time trial opens
    "Night Garden: Vessel (AN_22 #1)": ("climb_plus",), "Night Garden: Vessel (AN_22 #2)": ("climb_plus",),
    "Night Garden: Vessel (AN_22 #3)": ("climb_plus",), "Night Garden: Big Vessel (AN_22)": ("climb_plus",),
    "Night Garden: Trinket Slot (AN_22)": ("climb_plus",),
    # Bog rooms left of the Well (a tight jump with Climb alone is not counted)
    "The Bog: Big Vessel (AB_46)": ("climb_plus",), "The Bog: Vessel (AB_46)": ("climb_plus",),
    "The Bog: Vessel (AB_30)": ("climb_plus",),
}

PICKUP_LOCATIONS: dict[str, LocData] = {}
for i, (area, label, key, room, kind, tags) in enumerate(PICKUPS):
    rule = tuple(tags)
    if kind == "Looter Part" and room in LOOTER_ROOMS:
        rule += ("gatekey",) + LOOTER_ROOMS[room]
    if kind == "Combat Room":
        rule += ("hit",)
    if kind == "Flight Time Upgrade":
        rule += (FLIGHT_ROOMS.get(room, "flight2"),)
    if kind == "Ilda's Siblings":
        rule += ("siblings",)
    if room == "AP_16" and kind == "Elevator Part":
        rule += ("windride_or_vert",)
    if area == "Night Garden" and room not in NIGHT_GARDEN_EARLY:
        rule += ("climb",)
    if room == "AZ_98":   # spirit fragment rooms above the Well
        rule += ("soar",)
    region = ROOM_REGION.get(room, AREA_REGION[area])
    rule += LOCATION_TAGS.get(f"{area}: {label}", ())
    PICKUP_LOCATIONS[f"{area}: {label}"] = LocData(1000 + i, region, kind, rule, key)

EXTRA_LOCATIONS: dict[str, LocData] = {}
for i, (area, label, key, room, kind, tags) in enumerate(LEVERS_AND_VESSELS):
    group = "Levers" if kind == "Lever" else "Vessels"
    region = ROOM_REGION.get(room, AREA_REGION[area])
    tags = tuple(tags) + ("hit",)
    if area == "Night Garden" and room not in NIGHT_GARDEN_EARLY:
        tags = tags + ("climb",)
    tags += LOCATION_TAGS.get(f"{area}: {label}", ())
    EXTRA_LOCATIONS[f"{area}: {label}"] = LocData(3000 + i, region, group, tuple(tags), key)

# Lever items (option lever_items): one item per lever; the gate only opens once its item is received.
# lever_logic.json (generated from the GG map's lever -> gate lines and the room graph): room -> lever keys
# whose gates stand between that room and its area's entrances. Castle gate levers stay vanilla.
import json as _json
import pkgutil as _pkgutil
LEVER_LOGIC = _json.loads(_pkgutil.get_data(__name__, "lever_logic.json").decode())
CASTLE_LEVER_ROOMS = set(LEVER_LOGIC["castle"])
LEVER_ITEMS: dict[str, str] = {}      # lever save key -> item name
for i, (area, label, key, room, kind, tags) in enumerate(l for l in LEVERS_AND_VESSELS if l[4] == "Lever"):
    if room in CASTLE_LEVER_ROOMS:
        continue
    name = f"Lever: {area} {label[len('Lever '):]}"
    LEVER_ITEMS[key] = name
for i, name in enumerate(LEVER_ITEMS.values()):
    ITEMS[name] = ItemData(400 + i, P, 0, "Levers")
ITEM_NAME_TO_ID = {name: data.id for name, data in ITEMS.items()}
for name, data in ITEMS.items():
    ITEM_GROUPS.setdefault(data.group, set()).add(name)
# rooms of named locations (for lever requirements)
NAMED_ROOMS = {
    "Hunter's Cabin: Slingshot Egg": "AH_08", "The Bog: Climb Egg": "AB_29", "The Drains: Wind Ride Egg": "AP_12",
    "Desiccated Castle: Hover Egg": "AC_33", "Night Garden: Tent Travel": "AN_02",
    "Dollmaker's House: Magda (Wall Sling)": "AU_27", "Queen's Castle: Soar (Trinket Door)": "AQ_44",
    "Queen's Castle: Mysterious Markings": "AQ_45", "Queen's Castle: The Queen's Coin": "AQ_41",
    "Midnight Drench: Golden Feather (Willow's Friends)": "AL_01", "Midnight Drench: Golden Feather (Seven Sons)": "AL_37",
    "Webdrench Inn: Golden Feather (Inn Exit)": "AL_38", "Lookout Tower: Golden Feather (Starsinger)": "AG_32",
    "Autumn Forest: Golden Feather (Forest King)": "AF_34", "Dollmaker's House: Spirit Fragment": "AU_53",
    "Autumn Forest: Spirit Fragment": "AF_52", "Desiccated Castle: Spirit Fragment": "AC_52",
}


LOCATION_ROOMS = {f"{area}: {label}": room for area, label, key, room, kind, tags in PICKUPS + LEVERS_AND_VESSELS}


def lever_items_for(location_name: str) -> list[str]:
    room = LOCATION_ROOMS.get(location_name) or NAMED_ROOMS.get(location_name)
    if not room:
        return []
    return [LEVER_ITEMS[k] for k in LEVER_LOGIC["room_req"].get(room, []) if k in LEVER_ITEMS]


ALL_LOCATIONS = {**NAMED, **PICKUP_LOCATIONS, **EXTRA_LOCATIONS}
LOCATION_NAME_TO_ID = {name: d.id for name, d in ALL_LOCATIONS.items()}
LOCATION_GROUPS: dict[str, set[str]] = {}
for name, d in ALL_LOCATIONS.items():
    LOCATION_GROUPS.setdefault(d.group, set()).add(name)

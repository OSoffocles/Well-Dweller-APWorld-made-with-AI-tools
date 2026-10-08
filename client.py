"""Well Dweller client.

Connects to the Archipelago server and talks to the game mod (WellDwellerAP.dll) through text files in
<Well Dweller>\\archipelago\\ (items.txt written here; checks.txt and state.txt written by the mod).
"""
from __future__ import annotations

import asyncio
import collections
import json
import os
import shutil
import time
from typing import Any

import Utils
from CommonClient import (ClientCommandProcessor, CommonContext, get_base_parser, gui_enabled, handle_url_arg, logger,
                          server_loop)
from MultiServer import mark_raw
from NetUtils import ClientStatus

from .data import ALL_LOCATIONS, ITEM_NAME_TO_ID, ITEMS, LOCATION_NAME_TO_ID, PICKUP_LOCATIONS, TRINKETS
from .tracker import DEFAULT_MARKER, Logic, load_map_points, marker_for

GAME = "Well Dweller"
CONFIG_FILE = "well_dweller_client.json"
DEFAULT_GAME_DIRS = [
    r"C:\Program Files (x86)\Steam\steamapps\common\Well Dweller",
    r"C:\Program Files\Steam\steamapps\common\Well Dweller",
    r"D:\Steam\steamapps\common\Well Dweller",
    r"D:\SteamLibrary\steamapps\common\Well Dweller",
    r"E:\SteamLibrary\steamapps\common\Well Dweller",
    r"C:\GOG Games\Well Dweller",
    r"D:\GOG Games\Well Dweller",
    r"C:\Program Files (x86)\GOG Galaxy\Games\Well Dweller",
]


def find_game_dir() -> str:
    """The Well Dweller folder: known Steam/GOG locations, then every Steam library (libraryfolders.vdf)."""
    for d in DEFAULT_GAME_DIRS:
        if os.path.isfile(os.path.join(d, "WellDweller.exe")):
            return d
    import re
    for steam in (r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"):
        vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
        try:
            with open(vdf, encoding="utf-8", errors="replace") as f:
                libraries = re.findall(r'"path"\s+"([^"]+)"', f.read())
        except OSError:
            continue
        for lib in libraries:
            d = os.path.join(lib.replace("\\\\", "\\"), "steamapps", "common", "Well Dweller")
            if os.path.isfile(os.path.join(d, "WellDweller.exe")):
                return d
    return ""

# Trinket item -> index in the game's upgrade_list arrays (frame order of the s_trinkets sprite);
# <game>\archipelago\trinket_map.txt ("Name = index" per line) overrides/extends this table.
TRINKET_INDEX: dict[str, int] = {
    "Skull Keychain": 0,
    "Tiny Witch Sculpture": 1,
    "Bird-Shaped Button": 2,
    "Hunter's Locket": 3,
    "Rusty Fork": 4,
    "Nails with Twine": 5,
    "Scrap of Fabric": 6,
    "Molar Tooth": 7,
    "Fish Hook": 8,
    "Glass Shard": 9,
    "Pearl Jewelry": 10,
    "Paper Clip With String": 11,
    "Weathered Coin": 12,
    "Postage Stamp": 13,
    "Doll's Head": 14,
    "Cracked Marble": 15,
    "Silver Ring": 16,
    "Broken Bell": 17,
    "Rusted Thimble": 18,
    "Bundle of Hair": 19,
    "Bottle Cap": 20,
    "Glass Eye": 21,
    "Spider's Web": 22,
    "Silver Spoon": 23,
    "Melted Candle": 24,
    "Ember Vial": 25,
    "Rusted Compass": 26,
    "Golden Needle": 27,
    "Insect Wing": 28,
    "Hair Pin": 29,
    "Blue Bow": 30,
    "Burnt Shoelace": 31,
}


SHOP_TRINKET_BY_INDEX = {TRINKET_INDEX[n]: n for n in
                         ("Bottle Cap", "Skull Keychain", "Glass Eye", "Rusted Thimble", "Weathered Coin", "Silver Ring")}


def _loc(name: str) -> int:
    return LOCATION_NAME_TO_ID[name]


def _pickup_of_kind(kind: str) -> int | None:
    for name, d in PICKUP_LOCATIONS.items():
        if d.group == kind:
            return d.id
    return None


# "grant <var> <room>" lines from the mod: the game handed out something the multiworld owns.
GRANT_LOCATIONS: dict[str, int | None] = {
    "up_sling": _loc("Hunter's Cabin: Slingshot Egg"),
    "up_climb": _loc("The Bog: Climb Egg"),
    "up_wind_ride": _loc("The Drains: Wind Ride Egg"),
    "up_hover": _loc("Desiccated Castle: Hover Egg"),
    "tent_travel": _loc("Night Garden: Tent Travel"),
    "up_boat": _loc("The Docks: Barge (Water Vessel)"),
    "up_unlimited_stamina": _loc("The Depths: Barge (Endless Climb)"),
    "up_wall_sling": _loc("Dollmaker's House: Magda (Wall Sling)"),
    "up_fly": _loc("Queen's Castle: Soar (Trinket Door)"),
    "has_match": _pickup_of_kind("Matchstick"),
    "torpedo": _pickup_of_kind("Torpedo"),
    "collected_potions": _pickup_of_kind("Oil Vial"),
}
# Time trial statue room -> location (the mod reports the room the trial was entered from).
TIME_TRIAL_ROOMS: dict[str, int] = {
    "AB_31": _loc("The Bog: Time Trial"), "AN_22": _loc("Night Garden: Time Trial"),
    "AD_26": _loc("Gravenvalley: Time Trial"), "AC_16": _loc("Desiccated Castle: Time Trial"),
    "AL_26": _loc("Midnight Drench: Time Trial"), "AK_28": _loc("The Docks: Time Trial"),
    "AH_15": _loc("Hunter's Cabin: Time Trial"), "AF_13": _loc("Autumn Forest: Time Trial"),
    "AU_15": _loc("Dollmaker's House: Time Trial"), "AP_24": _loc("The Drains: Time Trial"),
}
FEATHER_ROOMS: dict[str, int] = {
    "AL_01": _loc("Midnight Drench: Golden Feather (Willow's Friends)"),
    "AL_37": _loc("Midnight Drench: Golden Feather (Seven Sons)"),
    "AL_38": _loc("Webdrench Inn: Golden Feather (Inn Exit)"),
    "r_inside_shoe": _loc("Autumn Forest: Whisper (Looter Feather)"),
    "AG_32": _loc("Lookout Tower: Golden Feather (Starsinger)"),
    "AF_34": _loc("Autumn Forest: Golden Feather (Forest King)"),
    "AT_InsideTomb": _loc("Burial Vault: Golden Feather (Squinton)"),
    "AT_InsideTomb_after": _loc("Burial Vault: Golden Feather (Squinton)"),
}


# In-game feed icons for this game's items: (sprite, frame). Other games' items use the Archipelago logo.
ITEM_ICON_BY_NAME: dict[str, tuple[str, int]] = {
    "Matchstick": ("s_matchstick", 0), "Water Vessel": ("s_water_vessel", 0), "Golden Gate Key": ("s_goldengate_key", 0),
    "Elevator Part": ("s_elevator_part_1", 0), "Pearl": ("s_pearl", 0), "Golden Feather": ("s_golden_feather", 0),
    "Spirit": ("s_spirits_icon", 0), "Spirit Fragment": ("s_spirits_icon", 0), "Workshop Token": ("s_upgrade_token", 0),
    "Trinket Point": ("s_ui_slots_small", 0), "Oil Vial": ("s_heal_vial_full", 0),
    "Flaming Vessel Upgrade": ("s_healvessel", 0), "Torpedo": ("s_torpedo", 0), "Currency": ("s_currency_spark", 0),
    "Big Currency": ("s_currency_spark", 0), "Full Heal": ("s_heal_vial_full", 0), "Vial Refill": ("s_heal_vial_full", 0),
    "Thief": ("s_lockicon", 0), "Bruise": ("s_lockicon", 0), "Spill": ("s_lockicon", 0),
    "Page": ("s_page_pic", 0), "Tent Travel": ("s_save_tenttravel", 0),
}
ITEM_ICON_BY_GROUP: dict[str, tuple[str, int]] = {
    "Abilities": ("s_abil_egg", 0), "Tents": ("s_save_tenttravel", 0), "Levers": ("s_lever", 0),
    "Trinket Upgrades": ("s_small_ug_icon", 0), "Key Items": ("s_item_marker", 0), "Upgrades": ("s_item_marker", 0),
}
# Archipelago item colours (progression / useful / trap / filler) and names.
COLOR_PROG, COLOR_USEFUL, COLOR_TRAP, COLOR_FILLER = "AF99EF", "6D8BE8", "FA8072", "00EEEE"
COLOR_ME, COLOR_PLAYER, COLOR_TEXT = "EE00EE", "FAFAD2", "FFFFFF"


def item_icon(name: str) -> tuple[str, int]:
    if name in TRINKETS:
        return "s_trinkets", TRINKET_INDEX.get(name, 0)
    if name in ITEM_ICON_BY_NAME:
        return ITEM_ICON_BY_NAME[name]
    d = ITEMS.get(name)
    if d is not None and d.group in ITEM_ICON_BY_GROUP:
        return ITEM_ICON_BY_GROUP[d.group]
    return "s_item_marker", 0


def item_color(flags: int) -> str:
    if flags & 0b001:
        return COLOR_PROG
    if flags & 0b010:
        return COLOR_USEFUL
    if flags & 0b100:
        return COLOR_TRAP
    return COLOR_FILLER


class WellDwellerCommandProcessor(ClientCommandProcessor):
    @mark_raw
    def _cmd_game_dir(self, path: str = "") -> bool:
        """Show or set the Well Dweller install folder (spaces are fine, quotes optional)."""
        ctx: WellDwellerContext = self.ctx  # type: ignore[assignment]
        path = path.strip().strip('"').strip("'")
        if path:
            if not os.path.isdir(path):
                self.output(f"Folder not found: {path}")
                return False
            ctx.set_game_dir(path)
        self.output(f"Game folder: {ctx.game_dir or '(not set)'}")
        return True

    def _cmd_claim(self) -> bool:
        """Bind the currently loaded save to this slot (only needed for a save that was not started fresh)."""
        ctx: WellDwellerContext = self.ctx  # type: ignore[assignment]
        ctx.claim_requested = True
        self.output("The next save loaded in-game (or the current one) will be bound to this slot.")
        return True

    def _cmd_goal(self) -> bool:
        """Mark your goal as completed (until the game's ending flags are known)."""
        ctx: WellDwellerContext = self.ctx  # type: ignore[assignment]
        asyncio.create_task(ctx.send_goal())
        return True

    def _cmd_wd_status(self) -> bool:
        """Show what the game mod reports."""
        ctx: WellDwellerContext = self.ctx  # type: ignore[assignment]
        if not ctx.state:
            self.output("No state from the game yet (is the mod installed and the game running?).")
            return False
        for key in ("mod", "time", "room", "ingame", "save", "slot", "received", "applied"):
            self.output(f"{key}: {ctx.state.get(key, '?')}")
        return True

    def _cmd_why(self, *name: str) -> bool:
        """Show what the logic needs for a location: /why <part of the location name>."""
        ctx: WellDwellerContext = self.ctx  # type: ignore[assignment]
        query = " ".join(name).strip().lower()
        if not query:
            self.output("Usage: /why <part of a location name>, e.g. /why Vessel (AN_03)")
            return False
        logic = ctx.get_logic()
        if not logic:
            self.output("The logic is not available (connect first).")
            return False
        names = sorted(loc.name for loc in logic.locations if query in loc.name.lower())
        if not names:
            self.output(f"No location matches '{query}'.")
            return False
        if len(names) > 8:
            self.output(f"{len(names)} locations match; be more specific. First few: " + "; ".join(names[:8]))
            return False
        held = ctx.received_names()
        reachable = logic.in_logic(held)
        for n in names:
            loc_id = LOCATION_NAME_TO_ID.get(n)
            done = loc_id in ctx.checked_locations
            loc = logic.location(n)
            region = loc.parent_region.name if loc else "?"
            if done:
                self.output(f"{n} [{region}]: already checked.")
            elif loc_id in reachable:
                self.output(f"{n} [{region}]: IN logic.")
            else:
                missing = logic.missing_for(n, held)
                need = ", ".join(missing) if missing else "more than one item"
                self.output(f"{n} [{region}]: OUT of logic. One of these would put it in logic: {need}")
        return True

    def _cmd_logic(self) -> bool:
        """Show per area how many unchecked locations are in logic."""
        ctx: WellDwellerContext = self.ctx  # type: ignore[assignment]
        logic = ctx.get_logic()
        if not logic:
            self.output("The logic is not available (connect first).")
            return False
        reachable = logic.in_logic(ctx.received_names())
        areas: dict[str, list[int]] = {}
        for loc in logic.locations:
            if loc.address in ctx.checked_locations:
                continue
            a = areas.setdefault(loc.name.split(":")[0], [0, 0])
            a[1] += 1
            if loc.address in reachable:
                a[0] += 1
        for area, (inl, total) in sorted(areas.items()):
            self.output(f"{area}: {inl} of {total} unchecked in logic")
        return True

    def _cmd_breaklog(self, onoff: str = "") -> bool:
        """Turn the local sequence-break log (archipelago\\logic_breaks.txt) on or off."""
        ctx: WellDwellerContext = self.ctx  # type: ignore[assignment]
        if onoff.lower() in ("on", "off"):
            ctx.break_log = onoff.lower() == "on"
            ctx.save_config()
        self.output(f"Sequence-break log is {'on' if ctx.break_log else 'off'}.")
        return True

    def _cmd_resync(self) -> bool:
        """Re-read every check the game has reported."""
        ctx: WellDwellerContext = self.ctx  # type: ignore[assignment]
        ctx.checks_offset = 0
        self.output("Re-reading checks.txt.")
        return True


class WellDwellerContext(CommonContext):
    command_processor = WellDwellerCommandProcessor
    game = GAME
    items_handling = 0b111  # everything, including starting inventory and own items

    def __init__(self, server_address: str | None, password: str | None) -> None:
        super().__init__(server_address, password)
        self.slot_data: dict[str, Any] = {}
        self.room_seed: str = ""
        self.location_keys: dict[str, int] = {}
        self.game_dir: str = ""
        self.checks_offset = 0
        self.last_items_text = ""
        self.state: dict[str, str] = {}
        self.state_vars: dict[str, str] = {}
        self.unknown_keys: set[str] = set()
        self.unmapped_grants: set[str] = set()
        self.warned_trinkets: set[str] = set()
        self.claim_requested = False
        self.kills_requested = 0      # death links to carry out in game (counts up)
        self.deaths_pending = 0       # own deaths not sent yet (amnesty)
        self.death_links_received = 0
        self.trial_rooms: set[str] = set()
        self.initial_read = True
        self.last_save_status = ""
        self.state_live = False
        self.feed: collections.deque = collections.deque(maxlen=5)   # last item messages for the in-game HUD
        self.last_hud_text = ""
        self.last_marks_text = ""
        self.logic: Logic | None = None
        self.map_points = load_map_points()
        self.logic_key: tuple = ()
        self.reachable: set[int] | None = None   # locations in logic, from the last map update
        self.break_log = True
        self.load_config()

    # ------------------------------------------------------------ config
    def config_path(self) -> str:
        return Utils.user_path(CONFIG_FILE)

    def load_config(self) -> None:
        try:
            with open(self.config_path(), encoding="utf-8") as f:
                cfg = json.load(f)
                self.game_dir = cfg.get("game_dir", "")
                self.break_log = bool(cfg.get("break_log", True))
        except (OSError, ValueError):
            pass
        if not self.game_dir:
            self.game_dir = find_game_dir()

    def set_game_dir(self, path: str) -> None:
        self.game_dir = path
        self.checks_offset = 0
        self.last_items_text = ""
        self.save_config()

    def save_config(self) -> None:
        try:
            with open(self.config_path(), "w", encoding="utf-8") as f:
                json.dump({"game_dir": self.game_dir, "break_log": self.break_log}, f)
        except OSError as e:
            logger.warning(f"Could not save the client settings: {e}")

    @property
    def ipc_dir(self) -> str:
        return os.path.join(self.game_dir, "archipelago") if self.game_dir else ""

    # ------------------------------------------------------------ server
    async def server_auth(self, password_requested: bool = False) -> None:
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict) -> None:
        if cmd == "RoomInfo":
            self.room_seed = str(args.get("seed_name", ""))
        elif cmd == "Connected":
            self.slot_data = args.get("slot_data", {}) or {}
            self.location_keys = {k: int(v) for k, v in self.slot_data.get("location_keys", {}).items()}
            self.checks_offset = 0
            self.last_items_text = ""
            if self.slot_data.get("death_link"):
                asyncio.create_task(self.update_death_link(True))
            shop = [LOCATION_NAME_TO_ID[n] for n in ALL_LOCATIONS
                    if n.startswith(("Looter's Shop:", "Forge:")) and LOCATION_NAME_TO_ID[n] in self.server_locations]
            if shop:
                asyncio.create_task(self.send_msgs([{"cmd": "LocationScouts", "locations": shop, "create_as_hint": 0}]))
            if not self.game_dir:
                logger.warning("Well Dweller folder not found. Use /game_dir <path to the game folder>.")
            else:
                logger.info(f"Game folder: {self.game_dir}")

    def on_print_json(self, args: dict) -> None:
        super().on_print_json(args)
        if args.get("type") != "ItemSend" or self.slot is None:
            return
        try:
            item = args["item"]
            receiver = int(args.get("receiving", 0))
            finder = int(item.player)
            if self.slot not in (receiver, finder):
                return
            rgame = self.slot_info[receiver].game if receiver in self.slot_info else ""
            name = self.item_names.lookup_in_slot(item.item, receiver)
            icon = item_icon(name) if rgame == GAME else ("ap", 0)
            color = item_color(int(item.flags))
            if receiver == self.slot and finder == self.slot:
                segs = [(COLOR_TEXT, "You found your "), (color, name)]
            elif receiver == self.slot:
                segs = [(COLOR_PLAYER, self.player_names.get(finder, "?")), (COLOR_TEXT, " sent you "), (color, name)]
            else:
                segs = [(COLOR_TEXT, "You sent "), (color, name), (COLOR_TEXT, " to "),
                        (COLOR_PLAYER, self.player_names.get(receiver, "?"))]
            self.feed.append((icon, segs))
        except Exception as e:  # the HUD is a nicety; never break the client
            logger.debug(f"HUD feed: {e}")

    def on_deathlink(self, data: dict[str, Any]) -> None:
        super().on_deathlink(data)
        self.death_links_received += 1
        wish = max(1, int(self.slot_data.get("death_wish", 1)))
        if self.death_links_received % wish == 0:
            self.kills_requested += 1
            logger.info(f"Death Link from {data.get('source', '?')}: you die.")
        else:
            left = wish - self.death_links_received % wish
            logger.info(f"Death Link from {data.get('source', '?')} absorbed ({left} more until one kills you).")

    async def own_death(self) -> None:
        if not self.slot_data.get("death_link"):
            return
        amnesty = int(self.slot_data.get("death_link_amnesty", 0))
        self.deaths_pending += 1
        if self.deaths_pending > amnesty:
            self.deaths_pending = 0
            await self.send_death(f"{self.auth} fell in the Well.")
            logger.info("Death Link sent.")
        else:
            logger.info(f"Death not sent (amnesty {self.deaths_pending}/{amnesty}).")

    async def disconnect(self, allow_autoreconnect: bool = False) -> None:
        self.slot_data = {}
        self.logic = None
        self.logic_key = ()
        self.reachable = None
        self.location_keys = {}
        await super().disconnect(allow_autoreconnect)

    def make_gui(self):
        ui = super().make_gui()
        ui.base_title = "Well Dweller Client"
        return ui

    async def send_goal(self) -> None:
        if self.finished_game or not self.slot:
            return
        await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
        self.finished_game = True
        logger.info("Goal completed!")

    # ------------------------------------------------------------ files
    def trinket_index(self) -> dict[int, int]:
        table = dict(TRINKET_INDEX)
        path = os.path.join(self.ipc_dir, "trinket_map.txt")
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if "=" in line and not line.lstrip().startswith("#"):
                        name, idx = line.rsplit("=", 1)
                        table[name.strip()] = int(idx)
        except (OSError, ValueError):
            pass
        return {ITEM_NAME_TO_ID[name]: idx for name, idx in table.items() if name in ITEM_NAME_TO_ID}

    def write_items(self) -> None:
        seed = self.room_seed
        if not self.ipc_dir or self.slot is None or not seed:
            return
        lines = [f"slot {seed} {self.slot}", "opt skip_tutorials 1", "opt open_shops 1", "opt reveal_map 1",
                 f"opt tents {int(self.slot_data.get('tent_unlocks', 0))}",
                 f"opt skip_intro {int(bool(self.slot_data.get('skip_intro', True)))}",
                 f"opt shop_points {self.slot_data.get('shop_trinket_point_checks', 0)}",
                 f"opt currency_multiplier {int(self.slot_data.get('currency_multiplier', 100))}",
                 f"opt currency_item {int(self.slot_data.get('currency_item_amount', 500))}",
                 *[f"opt shopcost{i} {int(v)}" for i, v in enumerate(self.slot_data.get("shop_costs") or [])],
                 f"opt kill {self.kills_requested}",
                 f"opt lever_items {int(bool(self.slot_data.get('lever_items', False)))}",
                 f"opt shop_per {int(self.slot_data.get('shop_trinket_points_per_check', 1))}",
                 f"opt forge_items {int(bool(self.slot_data.get('forge_checks', False)))}"]
        levels = self.slot_data.get("trinket_max_levels") or []
        lines += [f"maxlevel {i} {v}" for i, v in enumerate(levels)]
        if self.claim_requested:
            lines.append("opt claim 1")
        index = self.trinket_index()
        lines += [f"trinket {item} {idx}" for item, idx in sorted(index.items())]
        # The shop's Oil Vial is locked to its own location and the purchase already gives the vial in game:
        # that copy coming back from the server is not applied again (id 0 = nothing).
        shop_vial = LOCATION_NAME_TO_ID.get("Looter's Shop: Oil Vial")
        lines += [f"{i} {0 if (item.player == self.slot and item.location == shop_vial) else item.item}"
                  for i, item in enumerate(self.items_received)]
        for item in self.items_received:
            name = self.item_names.lookup_in_game(item.item)
            if name in TRINKETS and item.item not in index and name not in self.warned_trinkets:
                self.warned_trinkets.add(name)
                logger.info(f"{name} received, but its in-game index is not known yet; it will be given later.")
        text = "\n".join(lines) + "\n"
        if text == self.last_items_text:
            return
        os.makedirs(self.ipc_dir, exist_ok=True)
        tmp = os.path.join(self.ipc_dir, "items.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, os.path.join(self.ipc_dir, "items.txt"))
        self.last_items_text = text

    # ------------------------------------------------------------ in-game HUD and map tracker
    def write_file(self, name: str, text: str) -> None:
        os.makedirs(self.ipc_dir, exist_ok=True)
        tmp = os.path.join(self.ipc_dir, name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, os.path.join(self.ipc_dir, name))

    def write_hud(self) -> None:
        logo = os.path.join(self.ipc_dir, "ap_logo.png")
        if not os.path.exists(logo):
            try:
                shutil.copyfile(Utils.local_path("data", "icon.png"), logo)
            except OSError:
                pass
        found = len(self.checked_locations)
        total = found + len(self.missing_locations)
        lines = [f"checks\t{found}\t{total}"]
        for (sprite, frame), segs in self.feed:
            parts = ["msg", sprite, str(frame)]
            for color, text in segs:
                parts += [color, text.replace("\t", " ").replace("\n", " ")]
            lines.append("\t".join(parts))
        text = "\n".join(lines) + "\n"
        if text != self.last_hud_text:
            self.write_file("hud.txt", text)
            self.last_hud_text = text

    def get_logic(self) -> Logic | None:
        if self.logic is None and self.slot_data:
            try:
                self.logic = Logic(self.slot_data, self.auth or "Player")
            except Exception as e:
                logger.warning(f"Tracker: could not rebuild the logic ({e}).")
                self.logic = False  # type: ignore[assignment]
        return self.logic or None

    def received_names(self) -> list[str]:
        return [self.item_names.lookup_in_game(i.item) for i in self.items_received]

    def write_marks(self) -> None:
        mode = 0   # the map tracker starts off; F6 on the map cycles all items / uncollected / in logic / off
        names = self.received_names()
        key = (len(names), len(self.checked_locations), mode)
        if key == self.logic_key and self.last_marks_text:
            return
        self.logic_key = key
        logic = self.get_logic()
        self.reachable = logic.in_logic(names) if logic else None
        lines: list[str] = []
        # every map point is written; the mod filters (F6 cycles: all items / uncollected / in logic / off)
        points: dict[tuple, list] = {}
        for loc in set(self.missing_locations) | set(self.checked_locations):
            name = self.location_names.lookup_in_game(loc)
            pt = self.map_points.get(name)
            if not pt:
                continue
            points.setdefault((pt[0], pt[1]), []).append((loc, name, pt[2]))
        for (x, y), locs in sorted(points.items()):
            open_locs = [l for l in locs if l[0] not in self.checked_locations]
            if not open_locs:
                state = 0
            elif self.reachable is None or any(l[0] in self.reachable for l in open_locs):
                state = 1
            else:
                state = 2
            shown = open_locs or locs
            markers = {marker_for(n, g) for _, n, g in shown}
            marker = markers.pop() if len(markers) == 1 else DEFAULT_MARKER
            names = sorted(n for _, n, _ in shown)
            label = "; ".join(names[:3]) + (f" (+{len(names) - 3} more)" if len(names) > 3 else "")
            lines.append(f"m\t{x}\t{y}\t{marker[0]}\t{marker[1]}\t{state}\t{label.replace(chr(9), ' ')}")
        text = f"mode\t{mode}\n" + "\n".join(lines) + "\n"
        if text != self.last_marks_text:
            self.write_file("marks.txt", text)
            self.last_marks_text = text

    def item_text(self, loc_name: str) -> tuple[str, str] | None:
        """Name and description for the shop window: what this location gives the multiworld."""
        loc_id = LOCATION_NAME_TO_ID.get(loc_name)
        item = self.locations_info.get(loc_id) if loc_id is not None else None
        if item is None:
            return None
        receiver = int(item.player)
        name = self.item_names.lookup_in_slot(item.item, receiver)
        owner = "Your" if receiver == self.slot else f"{self.player_names.get(receiver, '?')}'s"
        flags = int(item.flags)
        kind = "Progression" if flags & 1 else "Useful" if flags & 2 else "Trap" if flags & 4 else "Filler"
        color = item_color(flags)
        game = self.slot_info[receiver].game if receiver in self.slot_info else ""
        who = "you" if receiver == self.slot else f"{self.player_names.get(receiver, '?')} ({game})"
        return f"{owner} {name}", f"[#{color}]{kind}[c_white] item for {who}."

    def write_shop(self) -> None:
        """shop.txt for the mod: what each Looter's Shop entry gives (by the shop's item id)."""
        if not self.locations_info:
            return
        lines: list[str] = []
        def add(sel: int, loc_name: str, extra: str = "") -> None:
            if LOCATION_NAME_TO_ID.get(loc_name) in self.checked_locations:
                return
            t = self.item_text(loc_name)
            if t:
                lines.append("\t".join(("s", str(sel), t[0], t[1] + extra)).replace("\n", " "))
        for idx, trinket in SHOP_TRINKET_BY_INDEX.items():
            add(idx, f"Looter's Shop: {trinket}")
        per = max(1, int(self.slot_data.get("shop_trinket_points_per_check", 1)))
        bought = int(self.var_number("bought_slots") or 0)
        for k in range(1, int(self.slot_data.get("shop_trinket_point_checks", 0)) + 1):
            name = f"Looter's Shop: Trinket Point {k}"
            if LOCATION_NAME_TO_ID.get(name) not in self.checked_locations:
                left = k * per - bought
                add(6, name, f" ({left} more to buy)" if left > 1 else "")
                break
        for k in (1, 2):
            name = f"Looter's Shop: Flaming Vessel Upgrade {k}"
            if LOCATION_NAME_TO_ID.get(name) not in self.checked_locations:
                add(7, name)
                break
        add(8, "Looter's Shop: Oil Vial")
        # forge: the next unchecked "Forge: Upgrade N"
        if self.slot_data.get("forge_checks"):
            for k in range(1, 27):
                name = f"Forge: Upgrade {k}"
                if LOCATION_NAME_TO_ID.get(name) in self.server_locations and \
                        LOCATION_NAME_TO_ID.get(name) not in self.checked_locations:
                    t = self.item_text(name)
                    if t:
                        lines.append("\t".join(("f", "0", t[0], t[1])))
                    break
        text = "\n".join(lines) + "\n"
        if text != getattr(self, "last_shop_text", ""):
            self.write_file("shop.txt", text)
            self.last_shop_text = text

    def log_breaks(self, new: set[int]) -> None:
        """Local sequence-break log: checks gained while the logic said they were out of logic."""
        if not self.break_log or self.reachable is None or not new:
            return
        breaks = [loc for loc in new if loc not in self.reachable]
        if not breaks:
            return
        import time
        held = sorted(n for n in set(self.received_names()) if not n.startswith(("Currency", "Big Currency")))
        try:
            with open(os.path.join(self.ipc_dir, "logic_breaks.txt"), "a", encoding="utf-8") as f:
                for loc in sorted(breaks):
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M')}\tseed {self.room_seed}\t"
                            f"{self.location_names.lookup_in_game(loc)}\titems: {', '.join(held)}\n")
        except OSError:
            pass

    def read_checks(self) -> set[int]:
        found: set[int] = set()
        self.initial_read = self.checks_offset == 0
        path = os.path.join(self.ipc_dir, "checks.txt")
        try:
            size = os.path.getsize(path)
        except OSError:
            return found
        if size < self.checks_offset:
            self.checks_offset = 0
        with open(path, encoding="utf-8", errors="replace") as f:
            f.seek(self.checks_offset)
            data = f.read()
            self.checks_offset = f.tell()
        slot_tag = f"[{self.room_seed} {self.slot}] "
        for line in data.splitlines():
            # Only lines the mod wrote for this seed and slot count (checks.txt outlives seeds).
            if not line.startswith(slot_tag):
                continue
            line = line[len(slot_tag):]
            parts = line.split()
            if len(parts) >= 2 and parts[0] == "key":
                key = line.split(" ", 1)[1].strip()  # keys can contain spaces ("Night Garden")
                if key in self.location_keys:
                    found.add(self.location_keys[key])
                elif key not in self.unknown_keys:
                    self.unknown_keys.add(key)
                    self.log_unknown(f"key {key}")
            elif len(parts) >= 2 and parts[0] == "forge":
                if self.slot_data.get("forge_checks"):
                    count = min(int(parts[1]), 26)
                    found |= {_loc(f"Forge: Upgrade {k}") for k in range(1, count + 1)}
            elif len(parts) >= 2 and parts[0] == "shop" and parts[1] == "oilvial":
                found.add(_loc("Looter's Shop: Oil Vial"))
            elif parts and parts[0] == "death":
                if not self.initial_read:
                    asyncio.create_task(self.own_death())
            elif len(parts) >= 2 and parts[0] == "trial":
                loc = TIME_TRIAL_ROOMS.get(parts[1])
                if loc is not None:
                    found.add(loc)
                elif line not in self.unmapped_grants:
                    self.unmapped_grants.add(line)
                    self.log_unknown(line)
            elif len(parts) >= 3 and parts[0] == "shop" and parts[1] == "trinket":
                name = SHOP_TRINKET_BY_INDEX.get(int(parts[2]))
                if name:
                    found.add(_loc(f"Looter's Shop: {name}"))
            elif len(parts) >= 3 and parts[0] == "grant":
                loc = self.grant_location(parts[1], parts[2], parts[3:])
                if loc is not None:
                    found.add(loc)
                elif line not in self.unmapped_grants:
                    self.unmapped_grants.add(line)
                    self.log_unknown(line)
        return found

    def grant_location(self, var: str, room: str, extra: list[str]) -> int | None:
        if var == "golden_feathers":
            return FEATHER_ROOMS.get(room)
        if var == "health_vials_max" and room == "r_inside_tent":
            return _loc("Looter's Shop: Oil Vial")
        return GRANT_LOCATIONS.get(var)

    def log_unknown(self, line: str) -> None:
        # Flags the game sets that are not locations yet; used to map the remaining checks.
        try:
            with open(os.path.join(self.ipc_dir, "unknown.txt"), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def read_state(self) -> None:
        path = os.path.join(self.ipc_dir, "state.txt")
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            return
        state: dict[str, str] = {}
        state_vars: dict[str, str] = {}
        for line in text.splitlines():
            if line.startswith("var "):
                _, name, *rest = line.split(" ", 2) + [""]
                state_vars[name] = rest[0] if rest else ""
            elif " " in line:
                k, v = line.split(" ", 1)
                state[k] = v
        self.state, self.state_vars = state, state_vars
        # state.txt stays behind after the game closes; only trust it while the mod keeps rewriting it
        # (every second) for this seed and slot, with a save loaded.
        try:
            fresh = time.time() - os.path.getmtime(path) < 5
        except OSError:
            fresh = False
        self.state_live = (fresh and state.get("ingame") == "1" and
                           state.get("slot", "").strip() == f"{self.room_seed} {self.slot}")
        status = state.get("save", "")
        if status != self.last_save_status:
            self.last_save_status = status
            if status:
                logger.info(f"Game: {status}")
            if status == "ok":
                self.claim_requested = False

    def var_list(self, name: str) -> list[float]:
        text = self.state_vars.get(name, "")
        if not text.startswith("["):
            return []
        out = []
        for part in text.strip("[]").split(","):
            try:
                out.append(float(part))
            except ValueError:
                pass
        return out

    def var_number(self, name: str) -> float | None:
        try:
            return float(self.state_vars[name])
        except (KeyError, ValueError):
            return None

    def state_checks(self) -> set[int]:
        found: set[int] = set()
        if not self.state_live or self.state.get("save") != "ok":
            return found
        bought = self.var_number("bought_slots")
        if bought:
            per = max(1, int(self.slot_data.get("shop_trinket_points_per_check", 1)))
            limit = min(int(bought) // per, int(self.slot_data.get("shop_trinket_point_checks", 0)))
            found |= {_loc(f"Looter's Shop: Trinket Point {k}") for k in range(1, limit + 1)}
        potions = self.var_number("bought_potions")   # Flaming Vessel upgrades bought
        if potions:
            found |= {_loc(f"Looter's Shop: Flaming Vessel Upgrade {k}") for k in range(1, min(int(potions), 2) + 1)}

        rewards = self.var_number("spirits_collected_reward")
        if rewards:
            found |= {_loc(f"Spirit Nest: Reward {k}") for k in range(1, min(int(rewards), 20) + 1)}
        return found

    def goal_reached(self) -> bool:
        goal = int(self.slot_data.get("goal", 0))
        if goal == 2 and self.state_live and self.state.get("save") == "ok":  # secret treasure: every trinket received and equipped
            names = {self.item_names.lookup_in_game(i.item) for i in self.items_received}
            active = self.state_vars.get("upgrade_list_active", "")
            return all(t in names for t in TRINKETS) and active.count("1") >= len(TRINKETS)
        return False


async def game_watcher(ctx: WellDwellerContext) -> None:
    while not ctx.exit_event.is_set():
        try:
            if ctx.ipc_dir and ctx.slot is not None and ctx.location_keys:
                ctx.write_items()
                ctx.read_state()
                found = ctx.read_checks() | ctx.state_checks()
                new = await ctx.check_locations(found)
                if not ctx.initial_read:
                    ctx.log_breaks(set(new))
                for loc in sorted(new):
                    logger.debug(f"Checked: {ctx.location_names.lookup_in_game(loc)}")
                ctx.write_hud()
                ctx.write_marks()
                ctx.write_shop()
                if not ctx.finished_game and ctx.goal_reached():
                    await ctx.send_goal()
        except PermissionError:
            pass  # file busy, try again next round
        except Exception as e:  # keep the watcher alive
            logger.exception(f"Well Dweller watcher error: {e}")
        await asyncio.sleep(0.5)


def launch(*args: str) -> None:
    async def main(parsed) -> None:
        ctx = WellDwellerContext(parsed.connect, parsed.password)
        ctx.auth = parsed.name
        if parsed.game_dir:
            ctx.set_game_dir(parsed.game_dir)
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()
        watcher = asyncio.create_task(game_watcher(ctx), name="Well Dweller watcher")
        await ctx.exit_event.wait()
        ctx.server_address = None
        await watcher
        await ctx.shutdown()

    import colorama

    Utils.init_logging("WellDwellerClient", exception_logger="Client")

    parser = get_base_parser(description="Well Dweller Archipelago client.")
    parser.add_argument("--name", default=None, help="Slot name to connect as.")
    parser.add_argument("--game_dir", default=None, help="Well Dweller install folder.")
    parser.add_argument("url", nargs="?", help="Archipelago connection url")
    parsed, _ = parser.parse_known_args(args)
    parsed = handle_url_arg(parsed, parser=parser)
    colorama.just_fix_windows_console()
    asyncio.run(main(parsed))
    colorama.deinit()

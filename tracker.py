"""In-game tracker support for the client: which locations are in logic, and where they are on the map."""
from __future__ import annotations

import json
import pkgutil
from typing import Any

from BaseClasses import CollectionState, MultiWorld

GAME = "Well Dweller"

# Map marker per location (game sprite, frame); the mod draws them over the map.
GROUP_MARKER: dict[str, tuple[str, int]] = {
    "Vessels": ("s_vessel", 0),
    "Levers": ("s_lever", 0),
    "Time Trials": ("s_timer_icon", 0),
    "Combat Room": ("s_markers_outline", 1),
    "Spirit": ("s_item_marker_spirit", 0),
    "Spirit Nest": ("s_item_marker_spirit", 0),
    "Workshop Token": ("s_item_marker_token", 0),
    "Trinket": ("s_item_marker_trinket", 0),
    "Trinket Slot": ("s_item_marker_slot", 0),
    "Page": ("s_item_marker_page", 0),
    "Bosses": ("s_map_major_mark", 0),
    "Abilities": ("s_abil_egg", 0),
    "Pearl": ("s_pearl_map", 0),
    "Elevator Part": ("s_elevator_part_unfound1", 0),
    "Matchstick": ("s_matchstick", 0),
    "Oil Vial": ("s_heal_vial_full", 0),
    "Torpedo": ("s_torpedo", 0),
    "Candied Egg": ("s_candied_spider_egg", 0),
    "Post-game": ("s_spirits_icon", 0),
}
NAME_MARKER: list[tuple[str, tuple[str, int]]] = [
    ("Golden Feather", ("s_golden_feather_outline", 0)),
    ("Golden Gate Key", ("s_goldengate_key", 0)),
]
DEFAULT_MARKER = ("s_item_marker", 0)
OUT_OF_LOGIC_MARKER = ("s_lockicon", 0)


def marker_for(name: str, group: str) -> tuple[str, int]:
    for part, marker in NAME_MARKER:
        if part in name:
            return marker
    return GROUP_MARKER.get(group, DEFAULT_MARKER)


def load_map_points() -> dict[str, list]:
    """Location name -> [map x, map y, group] (map cells, as the game's map marks use)."""
    data = pkgutil.get_data(__name__.rsplit(".", 1)[0], "map_points.json")
    return json.loads(data.decode("utf-8")) if data else {}


class Logic:
    """Rebuilds this slot's regions and rules from slot_data (like a universal tracker)."""

    def __init__(self, slot_data: dict[str, Any], player_name: str) -> None:
        from .world import WellDwellerWorld
        mw = MultiWorld(1)
        mw.game = {1: GAME}
        mw.player_name = {1: player_name}
        mw.set_seed(0)
        values = slot_data.get("options", {})
        od = WellDwellerWorld.options_dataclass
        kwargs = {}
        for name, cls in od.type_hints.items():
            kwargs[name] = cls.from_any(values[name] if name in values else cls.default)
        world = WellDwellerWorld(mw, 1)
        world.options = od(**kwargs)
        if slot_data.get("shop_costs"):
            world.shop_costs = list(slot_data["shop_costs"])
        mw.worlds[1] = world
        world.create_regions()
        self.mw, self.world = mw, world
        self.locations = [loc for loc in mw.get_locations(1) if loc.address is not None]

    def state(self, item_names: list[str]) -> CollectionState:
        state = CollectionState(self.mw)
        for name in item_names:
            try:
                state.collect(self.world.create_item(name), True)
            except Exception:
                pass
        return state

    def in_logic(self, item_names: list[str]) -> set[int]:
        state = self.state(item_names)
        return {loc.address for loc in self.locations if loc.can_reach(state)}

    def location(self, name: str):
        return next((loc for loc in self.locations if loc.name == name), None)

    def missing_for(self, loc_name: str, item_names: list[str]) -> list[str]:
        """Single items that would put the location in logic (given what is held now)."""
        from .data import ITEMS
        from BaseClasses import ItemClassification
        loc = self.location(loc_name)
        if loc is None:
            return []
        out = []
        for name, d in ITEMS.items():
            if not d.classification & ItemClassification.progression:
                continue
            if loc.can_reach(self.state(item_names + [name])):
                out.append(name)
                continue
            have = item_names.count(name)
            total = max(1, int(getattr(d, "count", 1) or 1))
            if total - have > 1 and loc.can_reach(self.state(item_names + [name] * (total - have))):
                out.append(f"{name} (x{total - have} more)")
        return out

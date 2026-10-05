from typing import TYPE_CHECKING

from BaseClasses import Entrance, Region

from .data import NG_GATE_LEVER, NG_AN04_LEVER, WEBDRENCH_GATE_LEVER
from .rules import climb, height, sling, vert, wall_sling_gate, wsling

if TYPE_CHECKING:
    from .world import WellDwellerWorld

REGIONS = [
    "Menu", "The Well", "Night Garden", "Night Garden East", "Night Garden Upper", "Night Garden Lower", "Hunter's Cabin", "Hunter's Cabin Upper", "The Bog", "Bog Interior",
    "Gravenvalley", "Gravenvalley Interior", "Gravenvalley Witch Burning", "The Drains", "Drains Depths",
    "Midnight Drench", "Desiccated Castle West", "Desiccated Castle East", "Desiccated Castle Lower",
    "The Docks", "Whisper's Hut", "The Depths", "Autumn Forest", "Forest King", "Lookout Tower",
    "Dollmaker's House", "Burial Vault", "Webdrench Inn", "Webdrench Inn Lower", "Queen's Castle", "Queen's Throne", "Queen's Chamber",
]


def create_regions(world: "WellDwellerWorld") -> None:
    mw, p = world.multiworld, world.player
    regions = {name: Region(name, p, mw) for name in REGIONS}
    mw.regions += regions.values()

    def link(a: str, b: str, rule=None) -> Entrance:
        return regions[a].connect(regions[b], f"{a} -> {b}", rule)

    link("Menu", "The Well")
    link("The Well", "Night Garden")
    # The AN_05 gate opens once you kill its enemy, so everything east of it (AN_05/AN_06 and up) needs the Matchstick.
    link("Night Garden", "Night Garden East", lambda s: s.has("Matchstick", p))
    # The AN_06 lever opens the gate down to the lower Night Garden (hit it, or receive its lever item).
    gate = (lambda s: s.has(NG_GATE_LEVER, p)) if world.options.lever_items else (lambda s: s.has("Matchstick", p))
    link("Night Garden East", "Night Garden Lower", gate)
    # Up from AN_05/AN_06 to AN_26-AN_32.
    link("Night Garden East", "Night Garden Upper",
         lambda s: s.has("Soar", p) or (climb(s, p) and sling(s, p) and s.has("Hover", p)))
    # The AN_04 gate (AN_04 -> AN_09) is opened from below; with lever items its item opens it from the top too,
    # but getting down to AN_08/AN_09 that way needs vertical movement.
    if world.options.lever_items:
        link("Night Garden", "Night Garden Lower", lambda s: s.has(NG_AN04_LEVER, p) and height(s, p))
    link("Night Garden Lower", "Hunter's Cabin", lambda s: s.has("Matchstick", p))
    link("Hunter's Cabin", "Hunter's Cabin Upper", lambda s: s.has("Soar", p) or sling(s, p) or climb(s, p))
    # Climb from the AN_04 tent down to the Bog, or the one-time chase down the Well with the Food.
    link("Night Garden", "The Bog", lambda s: climb(s, p) or s.has("Food", p))
    link("The Bog", "Bog Interior", lambda s: height(s, p))
    link("Hunter's Cabin", "Gravenvalley", lambda s: s.has_any(("Hover", "Soar"), p) or climb(s, p))
    link("Gravenvalley", "Gravenvalley Interior", lambda s: climb(s, p) or s.has("Soar", p))
    link("Gravenvalley Interior", "Gravenvalley Witch Burning", lambda s: s.has("Witch Burning Ticket", p))
    # Into the Drains from AN_23/AN_24 (Climb); the AN_16 door only opens from the Drains side (lever in AP_16).
    link("Night Garden Lower", "The Drains", lambda s: climb(s, p) or s.has("Soar", p))
    link("The Drains", "Drains Depths", lambda s: s.has("Wind Ride", p))
    # AN_24 -> AP_03 drops all the way to the bottom of the Drains with nothing; climbing back out needs
    # Wind Ride or VERT, otherwise Tent Travel gets you out.
    link("Night Garden Lower", "Drains Depths",
         lambda s: (climb(s, p) or s.has("Soar", p)) and (s.has_any(("Wind Ride", "Tent Travel"), p) or vert(s, p)))
    link("Drains Depths", "Midnight Drench", lambda s: s.has("Elevator Part", p, 3) and s.has("Matchstick", p))
    link("Gravenvalley Interior", "Desiccated Castle West")
    link("Midnight Drench", "Desiccated Castle East")
    lower = link("Desiccated Castle East", "Desiccated Castle Lower",
                 lambda s: s.can_reach_region("Desiccated Castle West", p))
    mw.register_indirect_condition(regions["Desiccated Castle West"], lower)
    link("Gravenvalley Interior", "The Docks",
         lambda s: s.has("Soar", p) or (climb(s, p) and s.has("Hover", p)))
    link("The Docks", "Whisper's Hut", lambda s: vert(s, p))
    link("The Docks", "The Depths", lambda s: s.has("Water Vessel", p))
    link("Gravenvalley Interior", "Autumn Forest", lambda s: vert(s, p))
    link("Night Garden Upper", "Autumn Forest", lambda s: vert(s, p) and climb(s, p) and s.has("Hover", p))
    link("Autumn Forest", "Whisper's Hut")
    link("Autumn Forest", "Forest King", lambda s: wsling(s, p) and climb(s, p))
    link("Night Garden Upper", "Lookout Tower", lambda s: s.has("Hover", p) and (sling(s, p) or climb(s, p)))
    link("Bog Interior", "Dollmaker's House", lambda s: vert(s, p))
    link("Midnight Drench", "Burial Vault", lambda s: wall_sling_gate(s, p))
    link("Night Garden East", "Webdrench Inn", lambda s: wall_sling_gate(s, p))
    # AW_01-AW_04 and the way out to the Golden Feather chase: behind the AW_05 lever gate (the boss-key gate under
    # the AW_06 lever only opens from below).
    aw05 = (lambda s: s.has(WEBDRENCH_GATE_LEVER, p)) if world.options.lever_items else None
    link("Webdrench Inn", "Webdrench Inn Lower", aw05)
    link("Bog Interior", "Queen's Castle", lambda s: s.has("Golden Feather", p, 7))
    link("Queen's Castle", "Queen's Throne",
         lambda s: s.has("Matchstick", p) and (s.has("Soar", p) or (
             sling(s, p) and wsling(s, p) and s.has("Hover", p) and climb(s, p))))
    link("Queen's Throne", "Queen's Chamber", lambda s: s.has("Matchstick", p))

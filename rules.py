"""Access rules. Shorthands follow the logic notes:

PC  = Progressive Climb count (1 = Climb, 2 = Endless Climb)
VERT = Soar OR Endless Climb OR (Climb AND Wall Sling)
HEIGHT = Slingshot OR Climb OR Soar
Slingshot and Wall Sling are used by hitting with the Matchstick, so both always need it.
"""
from BaseClasses import CollectionState


def sling(s: CollectionState, p: int) -> bool:
    return s.has_all(("Slingshot", "Matchstick"), p)


def wsling(s: CollectionState, p: int) -> bool:
    return s.has_all(("Wall Sling", "Matchstick"), p)


def climb(s: CollectionState, p: int) -> bool:
    return s.has("Progressive Climb", p)


def endless(s: CollectionState, p: int) -> bool:
    return s.has("Progressive Climb", p, 2)


def vert(s: CollectionState, p: int) -> bool:
    return s.has("Soar", p) or endless(s, p) or (climb(s, p) and wsling(s, p))


def height(s: CollectionState, p: int) -> bool:
    return s.has("Soar", p) or sling(s, p) or climb(s, p)


def wall_sling_gate(s: CollectionState, p: int) -> bool:
    # Wall Sling does nothing without at least one Climb
    return s.has("Soar", p) or endless(s, p) or (climb(s, p) and wsling(s, p))


MOVEMENT = ("Slingshot", "Wind Ride", "Hover", "Wall Sling", "Soar")


def abilities(s: CollectionState, p: int) -> int:
    """Movement abilities held (Climb and Endless Climb count as two)."""
    return sum(1 for a in MOVEMENT if s.has(a, p)) + min(2, s.count("Progressive Climb", p))


def currency_budget(s: CollectionState, p: int) -> float:
    """Estimated currency at 1x from the regions in reach (enemies and vessels need the Matchstick).
    Currency items are not counted."""
    from .data import CURRENCY_ESTIMATE, CURRENCY_SHARE
    if not s.has("Matchstick", p):
        return 0
    return CURRENCY_SHARE * sum(v for r, v in CURRENCY_ESTIMATE.items() if v and s.can_reach_region(r, p))


def trinket_count(s: CollectionState, p: int, trinkets: list[str]) -> int:
    return sum(1 for t in trinkets if s.has(t, p))


def tag_ok(tag: str, s: CollectionState, p: int, trinkets: list[str]) -> bool:
    if tag == "boss":
        return s.has("Matchstick", p)
    if tag == "climb":
        return climb(s, p) or s.has("Soar", p)
    if tag == "height":
        return height(s, p)
    if tag == "vert":
        return vert(s, p)
    if tag == "webdrench":   # getting around Webdrench Inn: Hover + Slingshot + (Climb or Soar)
        return s.has("Hover", p) and sling(s, p) and (climb(s, p) or s.has("Soar", p))
    if tag == "climb_plus":   # Climb + Slingshot, Climb + Wall Sling, Endless Climb or Soar
        return vert(s, p) or (climb(s, p) and sling(s, p))
    if tag == "hover":
        return s.has("Hover", p)
    if tag == "windride":
        return s.has("Wind Ride", p)
    if tag == "windride_or_vert":
        return s.has("Wind Ride", p) or vert(s, p)
    if tag == "wallsling":
        return wall_sling_gate(s, p)
    if tag == "soar":
        return s.has("Soar", p)
    if tag == "slingshot":
        return sling(s, p)
    if tag == "hit":   # levers, vessels and combat rooms are hit with the Matchstick
        return s.has("Matchstick", p)
    if tag == "gatekey":
        return s.has("Golden Gate Key", p)
    if tag == "pearls":
        return s.has("Pearl", p, 3)
    if tag == "torpedo":
        return s.has("Torpedo", p)
    if tag == "looter4":
        return s.has("Looter Part", p, 4)
    if tag == "siblings":
        return sling(s, p) and wsling(s, p) and s.has("Hover", p) and climb(s, p)
    if tag == "tentexit":   # the tent shops sit on a ledge: leave by Climb/Slingshot/Soar or teleport
        return climb(s, p) or sling(s, p) or s.has_any(("Soar", "Tent Travel"), p)
    if tag == "upgradable":   # forging needs an owned trinket that can still be upgraded
        from .data import UPGRADABLE_TRINKETS
        return s.has_any(UPGRADABLE_TRINKETS, p)
    if tag == "trinkets32":
        return trinket_count(s, p, trinkets) >= 32
    if tag.startswith("flight"):
        return s.has("Flight Time Upgrade", p, int(tag[6:]))
    if tag.startswith("spirits"):
        return s.has("Spirit", p, int(tag[7:]))
    if tag.startswith("tokens"):
        return s.has("Workshop Token", p, int(tag[6:]))
    raise ValueError(f"unknown rule tag {tag}")


def make_rule(tags: tuple, player: int, trinkets: list[str]):
    if not tags:
        return None
    return lambda s: all(tag_ok(t, s, player, trinkets) for t in tags)

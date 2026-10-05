from typing import Any, ClassVar

from BaseClasses import Item, ItemClassification, Location, LocationProgressType, Tutorial
from worlds.AutoWorld import WebWorld, World

from .data import (TRINKET_MAX_LEVEL, TRINKET_INDEX_ORDER, UPGRADE_ITEMS, LEVER_ITEMS, lever_items_for, STARTING_TENT, TENT_ITEMS, TENTS, TENT_REGION, TENT_ROOM_REGION, TENT_AREA_NEEDS, NG_LOWER_ROOMS, NG_LOWER_NAMED, NG_EAST_ROOMS, NG_UPPER_ROOMS, WEBDRENCH_LOWER_ROOMS, WEBDRENCH_LOWER_NAMED, NG_GATE_LEVER, NG_AN40_LEVER, NG_LOWER_NAMED_LOCS, LOCATION_ROOMS, NAMED_ROOMS, ALL_LOCATIONS, EXTRA_LOCATIONS, FILLER_ITEM, ITEM_GROUPS, ITEM_NAME_TO_ID, ITEMS,
                   LOCATION_GROUPS, LOCATION_NAME_TO_ID, NAMED, PICKUP_LOCATIONS, TRINKETS)
from .options import WellDwellerOptions
from .regions import create_regions
from .data import SHOP_ENTRIES, VANILLA_SHOP_COSTS, CURRENCY_ESTIMATE, CURRENCY_SHARE, FORGE_STEPS

MAX_BUDGET = CURRENCY_SHARE * sum(CURRENCY_ESTIMATE.values())
FORGE_SPREAD = 0.9   # the last forge upgrade needs 90% of the map
SHOP_START = 0.15      # no shop checks before 15% of the map is in reach ...
SHOP_EARLY_ABILITIES = 2   # ... and this many movement abilities (keeps the shop from filling the first spheres)
SHOP_AFFORDABLE = 0.5  # shop_progression: affordable - only checks needing less than half the map hold progression
SHOP_CAP = 0.95      # no shop check needs more than 95% of the map; one that would only holds filler
EARLY_GAME = 0.25    # no forge or Spirit Nest checks before a quarter of the map is in reach
MENU_KEYS = {"Workshop Token", "Spirit"}
from .rules import abilities, currency_budget, make_rule, tag_ok

SHOP_POINTS_IN_LOGIC = 10


def _location_room(name: str, d) -> str | None:
    """The room a location is in (from its save key, or the room tables)."""
    import re
    m = re.match(r"^([A-Za-z]{2}_\w+?)-\d+-\d+$", str(d.key))
    return m.group(1) if m else (LOCATION_ROOMS.get(name) or NAMED_ROOMS.get(name))

VANILLA_KEY_ITEMS = {
    "Food": "Hunter's Cabin: Food",
    "Witch Burning Ticket": "Gravenvalley: Witch Burning Ticket",
    # the golden gates open on Whisper's own flag (find_looter_start)
    "Golden Gate Key": "Autumn Forest: Whisper (Golden Gate Key)",
    # the shop's Oil Vial stays sold only while the vial is kept, so that purchase keeps its vial
    "Oil Vial": "Looter's Shop: Oil Vial",
}


class WellDwellerItem(Item):
    game = "Well Dweller"


class WellDwellerLocation(Location):
    game = "Well Dweller"


class WellDwellerWeb(WebWorld):
    theme = "stone"
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "How to set up Well Dweller for Archipelago.",
        "English", "setup_en.md", "setup/en", ["Soffocles"],
    )]


class WellDwellerWorld(World):
    """A hand-drawn metroidvania about Glimmer, a tiny bird with a matchstick, saving their family
    from the wicked queen."""
    game = "Well Dweller"
    web = WellDwellerWeb()
    options_dataclass = WellDwellerOptions
    options: WellDwellerOptions
    topology_present = True
    item_name_to_id: ClassVar[dict[str, int]] = ITEM_NAME_TO_ID
    location_name_to_id: ClassVar[dict[str, int]] = LOCATION_NAME_TO_ID
    item_name_groups = ITEM_GROUPS
    location_name_groups = LOCATION_GROUPS

    def _included_locations(self) -> dict[str, Any]:
        o = self.options
        out = {}
        for name, d in NAMED.items():
            if d.group == "Shop Trinket Points":
                k = int(name.rsplit(" ", 1)[1])
                if k > o.shop_trinket_point_checks or k * o.shop_trinket_points_per_check > 100:
                    continue
            if d.group == "Forge" and not o.forge_checks:
                continue
            if d.group == "Time Trials" and not o.time_trial_checks:
                continue
            out[name] = d
        out.update(PICKUP_LOCATIONS)
        for name, d in EXTRA_LOCATIONS.items():
            if (d.group == "Levers" and (o.lever_checks or o.lever_items)) or (d.group == "Vessels" and o.vessel_checks):
                out[name] = d
        return out

    # Universal Tracker: rebuild this slot from slot_data instead of a YAML (same options, same shop prices).
    ut_can_gen_without_yaml = True

    @staticmethod
    def interpret_slot_data(slot_data: dict[str, Any]) -> dict[str, Any]:
        return slot_data

    def generate_early(self) -> None:
        passthrough = getattr(self.multiworld, "re_gen_passthrough", {}).get(self.game)
        if not passthrough:
            return
        for name, value in passthrough.get("options", {}).items():
            current = getattr(self.options, name, None)
            if current is None:
                continue
            try:
                setattr(self.options, name, type(current).from_any(value))
            except Exception:
                pass
        if passthrough.get("shop_costs"):
            self.shop_costs = list(passthrough["shop_costs"])

    def _shop_costs(self) -> list[int]:
        """This seed's shop prices (shop order, see SHOP_ENTRIES); the client's tracker passes them in."""
        if getattr(self, "shop_costs", None):
            return self.shop_costs
        o = self.options
        costs = list(VANILLA_SHOP_COSTS)
        if o.shop_prices == o.shop_prices.option_randomized:
            lo, hi = sorted((int(o.shop_price_minimum), int(o.shop_price_maximum)))
            costs = [max(10, int(round(c * self.random.randint(lo, hi) / 100 / 10)) * 10) for c in costs]
        self.shop_costs = costs
        return costs

    def _shop_needs(self, names: list[str]) -> dict[str, float]:
        """Currency (at 1x) needed in logic for each shop check: every purchase that costs no more than it is
        assumed to be bought first, so a check needs its own price plus all cheaper ones. Divided by the
        Currency Multiplier. Trinket points past the first SHOP_POINTS_IN_LOGIC (filler only) come last and do not
        add to the others. Nothing needs more than SHOP_CAP of the whole map; a check that would is filler only
        (see _shop_capped)."""
        o = self.options
        costs = dict(zip(SHOP_ENTRIES, self._shop_costs()))
        per = int(o.shop_trinket_points_per_check)
        buys, late = [], []   # (price, location name)
        for name in names:
            label = name.split(": ", 1)[1]
            if label.startswith("Trinket Point "):
                k = int(label.rsplit(" ", 1)[1])
                (late if k * per > SHOP_POINTS_IN_LOGIC else buys).append((costs["Trinket Point"] * per, name))
            elif label.startswith("Flaming Vessel Upgrade"):
                buys.append((costs["Flaming Vessel Upgrade"], name))
            elif label in costs:
                buys.append((costs[label], name))
        buys.sort(key=lambda b: (b[0], b[1]))
        late.sort(key=lambda b: int(b[1].rsplit(" ", 1)[1]))
        cap = SHOP_CAP * MAX_BUDGET
        need, total = {}, 0
        self._shop_capped = set()
        for price, name in buys + late:
            total += price
            need[name] = total / max(1, int(o.currency_multiplier))
            if need[name] > cap:
                need[name] = cap
                self._shop_capped.add(name)
        return need

    def create_regions(self) -> None:
        o = self.options
        create_regions(self)
        included = self._included_locations()
        shop_need = self._shop_needs([n for n, d in included.items() if d.group in ("Shop", "Shop Trinket Points")])
        for name, d in included.items():
            region_name = d.region
            if region_name == "Night Garden":
                room = _location_room(name, d)
                if name in NG_LOWER_NAMED or name in NG_LOWER_NAMED_LOCS or d.group == "Spirit Nest" or \
                        room in NG_LOWER_ROOMS:
                    region_name = "Night Garden Lower"
                elif room in NG_EAST_ROOMS:
                    region_name = "Night Garden East"
                elif room in NG_UPPER_ROOMS:
                    region_name = "Night Garden Upper"
            if region_name == "Webdrench Inn" and (name in WEBDRENCH_LOWER_NAMED or
                                                   _location_room(name, d) in WEBDRENCH_LOWER_ROOMS):
                region_name = "Webdrench Inn Lower"
            region = self.multiworld.get_region(region_name, self.player)
            loc = WellDwellerLocation(self.player, name, LOCATION_NAME_TO_ID[name], region)
            if name in self._shop_capped or d.group == "Shop Trinket Points" and \
                    int(name.rsplit(" ", 1)[1]) * self.options.shop_trinket_points_per_check > SHOP_POINTS_IN_LOGIC:
                # Trinket points are sold one after another; later ones need a lot of currency,
                # so they only ever hold filler.
                loc.progress_type = LocationProgressType.EXCLUDED
            rule = make_rule(d.rule + (("webdrench",) if region_name.startswith("Webdrench Inn") else ()),
                             self.player, TRINKETS)
            if d.group == "Forge":
                # Forge upgrades follow the map too (not only Workshop Tokens), spread over the whole game, so the early
                # game never has spheres of only forge checks.
                step = int(name.rsplit(" ", 1)[1])
                need_forge = max(EARLY_GAME * MAX_BUDGET, FORGE_SPREAD * MAX_BUDGET * step / FORGE_STEPS)
                base = rule
                rule = (lambda s, b=base, c=need_forge: currency_budget(s, self.player) >= c and (b is None or b(s)))
            if d.group == "Spirit Nest":
                # the Spirit Nest also waits for the early game to be over
                base = rule
                rule = (lambda s, b=base: currency_budget(s, self.player) >= EARLY_GAME * MAX_BUDGET and (b is None or b(s)))
            if d.group in ("Shop", "Shop Trinket Points", "Forge", "Spirit Nest"):
                # no Workshop Tokens or Spirits in the shop, forge or Spirit Nest: a check there holding what the next
                # one needs makes chains of spheres with nothing to do on the map
                loc.item_rule = lambda item: not (item.player == self.player and item.name in MENU_KEYS)
            if d.group in ("Shop", "Shop Trinket Points"):
                sp = o.shop_progression
                if sp == sp.option_none or (sp == sp.option_affordable and
                                            shop_need.get(name, 0) > SHOP_AFFORDABLE * MAX_BUDGET):
                    # expensive purchases never hold anyone's progression: nobody waits on a currency grind
                    loc.item_rule = lambda item: not item.advancement and \
                        not (item.player == self.player and item.name in MENU_KEYS)
            need = shop_need.get(name, 0)
            if need > 0:
                base = rule
                c = max(need, SHOP_START * MAX_BUDGET)
                rule = (lambda s, b=base, c=c: abilities(s, self.player) >= SHOP_EARLY_ABILITIES
                        and currency_budget(s, self.player) >= c and (b is None or b(s)))
            if o.lever_items:
                # pulling a lever needs its own item too only if its gate stands in the way; levers are
                # usually on the near side, so a lever's own location does not need its own item
                levers = [l for l in lever_items_for(name) if not (d.group == "Levers" and LEVER_ITEMS.get(d.key) == l)]
                if levers:
                    base = rule
                    rule = (lambda s, b=base, l=tuple(levers): s.has_all(l, self.player) and (b is None or b(s)))
            if _location_room(name, d) == "AN_40":
                # Not reachable from below while the wall is up. With lever items its item opens it (then go up
                # like the time trial); without them the way in is unknown, so these hold filler only.
                base = rule
                if o.lever_items:
                    rule = (lambda s, b=base: s.has(NG_AN40_LEVER, self.player) and tag_ok("climb_plus", s, self.player, TRINKETS)
                            and (b is None or b(s)))
                else:
                    rule = (lambda s, b=base: s.has("Soar", self.player) and (b is None or b(s)))
                    loc.progress_type = LocationProgressType.EXCLUDED
            if d.group == "Forge":
                # a forge check never holds a Workshop Token, so the forge cannot feed itself sphere after sphere
                loc.item_rule = lambda item: not (item.player == self.player and item.name == "Workshop Token")
            if rule:
                loc.access_rule = rule
            region.locations.append(loc)
        self._add_tent_entrances()
        self._add_goal_event()

    def _add_tent_entrances(self) -> None:
        """With tents unlocked or shuffled, teleporting (Tent Travel) to a tent reaches its area.
        A few areas need an item to move around at all once you are there (TENT_AREA_NEEDS)."""
        o, p = self.options, self.player
        if o.tent_unlocks == o.tent_unlocks.option_vanilla:
            return
        menu = self.multiworld.get_region("Menu", p)
        shuffled = o.tent_unlocks == o.tent_unlocks.option_shuffled
        for (_, room, area), item in zip(TENTS, TENT_ITEMS):
            region = TENT_ROOM_REGION.get(room) or TENT_REGION.get(room[:2])
            if not region:
                continue
            needs = (("Tent Travel", item) if shuffled else ("Tent Travel",)) + TENT_AREA_NEEDS.get(region, ())
            menu.connect(self.multiworld.get_region(region, p), f"Teleport: {item}",
                         lambda s, needs=needs: s.has_all(needs, p))

    def _add_goal_event(self) -> None:
        p, goal = self.player, self.options.goal
        if goal == goal.option_queen:
            region, rule = "Queen's Throne", lambda s: s.has("Matchstick", p)
        elif goal == goal.option_true_ending:
            # beating the Queen may also be needed for the true ending: required too (forgiving)
            region, rule = "Night Garden", lambda s: s.has("Spirit", p, 20) and s.has("Spirit Fragment", p, 5) and \
                s.can_reach_region("Queen's Throne", p) and s.has("Matchstick", p)
        else:
            region, rule = "Night Garden", lambda s: all(s.has(t, p) for t in TRINKETS)
        r = self.multiworld.get_region(region, p)
        ev = WellDwellerLocation(p, "Goal", None, r)
        ev.access_rule = rule
        ev.place_locked_item(WellDwellerItem("Victory", ItemClassification.progression, None, p))
        r.locations.append(ev)
        self.multiworld.completion_condition[p] = lambda s: s.has("Victory", p)

    def create_item(self, name: str) -> WellDwellerItem:
        d = ITEMS[name]
        classification = d.classification
        if name in TENT_ITEMS and self.options.tent_unlocks == self.options.tent_unlocks.option_shuffled \
                and TENT_REGION.get(name.rsplit("(", 1)[1][:2]):
            classification = ItemClassification.progression
        if name == "Workshop Token" and self.options.forge_checks:
            # forge checks need tokens in logic
            classification = ItemClassification.progression_skip_balancing
        return WellDwellerItem(name, classification, d.id, self.player)

    def create_items(self) -> None:
        o = self.options
        pool: list[str] = []
        for name, d in ITEMS.items():
            pool += [name] * d.count
        if o.matchstick == o.matchstick.option_start_with:
            pool.remove("Matchstick")
            self.multiworld.push_precollected(self.create_item("Matchstick"))
        elif o.matchstick == o.matchstick.option_early:
            self.multiworld.local_early_items[self.player]["Matchstick"] = 1
        if o.lever_items:
            # the AN_06 lever opens the lower Night Garden: without it early there is hardly anything to explore.
            # Without the Matchstick at the start the first sphere is only two locations, so it is given right away.
            if o.matchstick == o.matchstick.option_start_with:
                self.multiworld.local_early_items[self.player][NG_GATE_LEVER] = 1
            else:
                self.multiworld.push_precollected(self.create_item(NG_GATE_LEVER))
        if o.matchstick == o.matchstick.option_shuffled and \
                (o.tent_travel == o.tent_travel.option_shuffled or o.lever_items):
            # the first sphere is only two locations without it: keep it shuffled across the multiworld,
            # but in sphere 1
            self.multiworld.early_items[self.player]["Matchstick"] = 1
        if o.forge_checks:
            for name, copies in UPGRADE_ITEMS.items():
                pool += [name] * copies
        if o.lever_items:
            pool += [lv for lv in LEVER_ITEMS.values()
                     if not (lv == NG_GATE_LEVER and o.matchstick != o.matchstick.option_start_with)]
        if o.tent_unlocks == o.tent_unlocks.option_shuffled:
            pool += [t for t in TENT_ITEMS if t != STARTING_TENT]
            self.multiworld.push_precollected(self.create_item(STARTING_TENT))
        if o.tent_travel == o.tent_travel.option_start_with:
            pool.remove("Tent Travel")
            self.multiworld.push_precollected(self.create_item("Tent Travel"))

        # These key items stay at their own spots: the game uses the location's own flag as
        # "you have it", so they cannot be handed out elsewhere.
        for item, location in VANILLA_KEY_ITEMS.items():
            pool.remove(item)
            self.multiworld.get_location(location, self.player).place_locked_item(self.create_item(item))

        unfilled = self.multiworld.get_unfilled_locations(self.player)
        slots = len(unfilled)
        # Filler-only (excluded) locations need filler: keep that many slots free for it.
        excluded = sum(1 for loc in unfilled if loc.progress_type == LocationProgressType.EXCLUDED)
        # Optional extra copies (only as far as there is room).
        extras = (["Trinket Point"] * o.extra_trinket_points + ["Workshop Token"] * o.extra_workshop_tokens
                  + ["Oil Vial"] * o.extra_oil_vials + ["Golden Feather"] * o.extra_golden_feathers)
        room = max(0, slots - excluded - len(pool))
        if len(extras) > room:
            self.random.shuffle(extras)
            extras = extras[:room]
        pool += extras
        # Too many items (or too little room left for filler): drop the least important ones first.
        for trim in ("Hat", "Trinket Point") + (() if o.forge_checks else ("Workshop Token",)):
            while len(pool) > slots - excluded and trim in pool:
                pool.remove(trim)
        if len(pool) > slots:
            raise Exception(f"Well Dweller: {len(pool)} items for {slots} locations")
        pool += self._filler_mix(slots - len(pool))
        self.multiworld.itempool += [self.create_item(n) for n in pool]

    def _filler_mix(self, count: int) -> list[str]:
        """Split the free slots between Currency, boons and traps by the filler shares."""
        o = self.options
        boons, traps = sorted(o.boons.value), sorted(o.traps.value)
        shares = [("currency", int(o.filler_currency)), ("boons", int(o.filler_boons) if boons else 0),
                  ("traps", int(o.filler_traps) if traps else 0)]
        total = sum(v for _, v in shares)
        if total == 0:
            return [FILLER_ITEM] * count
        exact = [(k, count * v / total) for k, v in shares]
        counts = {k: int(x) for k, x in exact}
        for k, x in sorted(exact, key=lambda kx: kx[1] - int(kx[1]), reverse=True)[:count - sum(counts.values())]:
            counts[k] += 1
        out = [FILLER_ITEM] * counts["currency"]
        out += [self.random.choice(boons) for _ in range(counts["boons"])]
        out += [self.random.choice(traps) for _ in range(counts["traps"])]
        return out

    def get_filler_item_name(self) -> str:
        return FILLER_ITEM

    def fill_slot_data(self) -> dict[str, Any]:
        o = self.options
        return {
            "goal": int(o.goal), "matchstick": int(o.matchstick), "tent_travel": int(o.tent_travel),
            "lever_checks": bool(o.lever_checks), "vessel_checks": bool(o.vessel_checks),
            "time_trial_checks": bool(o.time_trial_checks), "forge_checks": bool(o.forge_checks),
            "shop_trinket_point_checks": int(o.shop_trinket_point_checks), "death_link": bool(o.death_link),
            "tent_unlocks": int(o.tent_unlocks), "skip_intro": bool(o.skip_intro), "lever_items": bool(o.lever_items),
            "shop_trinket_points_per_check": int(o.shop_trinket_points_per_check),
            "trinket_max_levels": [TRINKET_MAX_LEVEL[t] for t in TRINKET_INDEX_ORDER],
            "currency_multiplier": int(o.currency_multiplier) * 100, "currency_item_amount": int(o.currency_item_amount),
            "shop_costs": self._shop_costs(),
            "death_link_amnesty": int(o.death_link_amnesty), "death_wish": int(o.death_wish),
            # every option, so the client can rebuild the logic for the in-game map tracker
            "options": {name: (sorted(v) if isinstance(v, (set, frozenset)) else v)
                        for name in o.__dataclass_fields__ for v in [getattr(o, name).value]},
            # save key -> location id, for the client
            "location_keys": {d.key: LOCATION_NAME_TO_ID[n] for n, d in ALL_LOCATIONS.items() if d.key},
        }

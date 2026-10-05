from dataclasses import dataclass

from Options import Choice, DeathLink, DefaultOnToggle, OptionSet, PerGameCommonOptions, Range, Toggle


class Goal(Choice):
    """What you need to do to finish.
    queen: defeat The Queen.
    true_ending: return all 20 spirits and collect the 5 Spirit Fragments.
    secret_treasure: collect all 32 trinkets."""
    display_name = "Goal"
    option_queen = 0
    option_true_ending = 1
    option_secret_treasure = 2
    default = 0


class MatchstickMode(Choice):
    """How you get the Matchstick, your weapon.
    start_with: you start with it.
    early: it is shuffled, but always placed in your own early locations.
    shuffled: it can be anywhere in the multiworld."""
    display_name = "Matchstick"
    option_start_with = 0
    option_early = 1
    option_shuffled = 2
    default = 1


class TentTravel(Choice):
    """How you get Tent Travel (fast travel between tents).
    start_with: unlocked from the start (recommended: the tent shops sit on a ledge you need Climb or
    Slingshot to leave, and teleporting is the way out without them).
    shuffled: it is an item in the pool."""
    display_name = "Tent Travel"
    option_start_with = 0
    option_shuffled = 1
    default = 0


class TentUnlocks(Choice):
    """Which tents you can teleport to (with Tent Travel).
    vanilla: a tent is added when you visit it.
    all_unlocked: every tent is available from the start.
    shuffled: each tent is an item in the multiworld (the first tent in the Night Garden is given at the start).
    A shuffled tent you find yourself is unlocked too.
    Queen's Castle tents always stay vanilla, so the Golden Feather gate can't be skipped.
    With all_unlocked or shuffled, the logic counts on teleporting (Tent Travel) to the tents you have:
    a tent counts as reaching its area."""
    display_name = "Tent Unlocks"
    option_vanilla = 0
    option_all_unlocked = 1
    option_shuffled = 2
    default = 0


class SkipIntro(DefaultOnToggle):
    """Skip the opening cutscene in the Well: a new game starts in the Night Garden right away."""
    display_name = "Skip Intro"


class Levers(Toggle):
    """Hitting a gate lever for the first time is a check (103 levers). The gate still opens as usual."""
    display_name = "Lever Checks"


class LeverItems(Toggle):
    """Death's Door style levers: pulling a lever only sends its check; the gate it operates opens when
    that lever's item arrives (receiving the item first also counts the lever as pulled).
    Turns Lever Checks on. Gate positions come from the online map, so treat this as experimental."""
    display_name = "Lever Items"


class Vessels(Toggle):
    """Breaking a currency vessel for the first time is a check (124 vessels)."""
    display_name = "Vessel Checks"


class TimeTrials(Toggle):
    """Completing each of the 10 time trials is a check."""
    display_name = "Time Trial Checks"


class ForgeChecks(Toggle):
    """Each of the 26 trinket upgrades at the forge is a check."""
    display_name = "Forge Checks"


class ShopTrinketPointsPerCheck(Range):
    """Every how many Trinket Point purchases in the Looter's shop give a check.
    Purchases always keep their normal effect (you still get the Trinket Point)."""
    display_name = "Shop Trinket Points per Check"
    range_start = 1
    range_end = 10
    default = 1


class ShopTrinketPoints(Range):
    """How many Trinket Point purchase checks there are (one every "Shop Trinket Points per Check" purchases;
    the shop sells 100, so at most 100 / per check). Purchases cost currency, so only the checks
    within the first 10 purchases can hold important items; later ones only hold filler.
    Adds this many locations."""
    display_name = "Shop Trinket Point Checks"
    range_start = 0
    range_end = 100
    default = 5


class CurrencyMultiplier(Range):
    """Multiplies all currency you get: enemies, vessels and Currency items from the multiworld
    (1 = normal, 2 = double). Shop checks come into logic sooner with a higher multiplier."""
    display_name = "Currency Multiplier"
    range_start = 1
    range_end = 10
    default = 2


class ShopPrices(Choice):
    """Prices in the Looter's shop.
    vanilla: the game's prices.
    randomized: every shop entry gets its own price, between Shop Price Minimum and Shop Price Maximum
    (percent of the vanilla price). The logic uses the prices of your seed."""
    display_name = "Shop Prices"
    option_vanilla = 0
    option_randomized = 1
    default = 0


class ShopPriceMinimum(Range):
    """Shop Prices randomized: lowest price, in percent of the vanilla price."""
    display_name = "Shop Price Minimum"
    range_start = 10
    range_end = 1000
    default = 50


class ShopPriceMaximum(Range):
    """Shop Prices randomized: highest price, in percent of the vanilla price."""
    display_name = "Shop Price Maximum"
    range_start = 10
    range_end = 1000
    default = 200


class CurrencyItemAmount(Range):
    """How much currency one "Currency" item from the multiworld gives."""
    display_name = "Currency Item Amount"
    range_start = 50
    range_end = 5000
    default = 500


class ExtraTrinketPoints(Range):
    """Extra Trinket Point items added to the pool (on top of the game's own)."""
    display_name = "Extra Trinket Points"
    range_start = 0
    range_end = 50
    default = 0


class ExtraWorkshopTokens(Range):
    """Extra Workshop Token items added to the pool."""
    display_name = "Extra Workshop Tokens"
    range_start = 0
    range_end = 30
    default = 0


class ExtraOilVials(Range):
    """Extra Oil Vial items added to the pool (the game holds at most 12 Oil Vials)."""
    display_name = "Extra Oil Vials"
    range_start = 0
    range_end = 9
    default = 0


class ExtraGoldenFeathers(Range):
    """Extra Golden Feathers added to the pool (the Queen's Castle still needs 7)."""
    display_name = "Extra Golden Feathers"
    range_start = 0
    range_end = 10
    default = 0


class FillerCurrency(Range):
    """Share of the remaining filler that is Currency. The three filler shares are weights:
    they don't have to add up to 100. All 0 = only Currency."""
    display_name = "Filler: Currency"
    range_start = 0
    range_end = 100
    default = 60


class FillerBoons(Range):
    """Share of the remaining filler that is boons (see Boons)."""
    display_name = "Filler: Boons"
    range_start = 0
    range_end = 100
    default = 25


class FillerTraps(Range):
    """Share of the remaining filler that is traps (see Traps)."""
    display_name = "Filler: Traps"
    range_start = 0
    range_end = 100
    default = 15


class Boons(OptionSet):
    """Which boons can be filler.
    Big Currency: 5x the Currency Item Amount. Full Heal: health to max. Vial Refill: all Oil Vials refilled."""
    display_name = "Boons"
    valid_keys = {"Big Currency", "Full Heal", "Vial Refill"}
    default = frozenset(valid_keys)


class Traps(OptionSet):
    """Which traps can be filler.
    Thief: lose a quarter of your currency. Bruise: lose a third of your current health (never lethal).
    Spill: your Oil Vials are emptied."""
    display_name = "Traps"
    valid_keys = {"Thief", "Bruise", "Spill"}
    default = frozenset(valid_keys)


class DeathLinkAmnesty(Range):
    """Death Link: how many times you can die before one death is sent to the others (0 = every death)."""
    display_name = "Death Link Amnesty"
    range_start = 0
    range_end = 20
    default = 0


class DeathWish(Range):
    """Death Link: how many deaths from others you must receive before one of them kills you
    (1 = every one, 2 = every second one, ...)."""
    display_name = "Death Wish"
    range_start = 1
    range_end = 20
    default = 1


@dataclass
class WellDwellerOptions(PerGameCommonOptions):
    goal: Goal
    matchstick: MatchstickMode
    tent_travel: TentTravel
    tent_unlocks: TentUnlocks
    skip_intro: SkipIntro
    lever_checks: Levers
    lever_items: LeverItems
    vessel_checks: Vessels
    time_trial_checks: TimeTrials
    forge_checks: ForgeChecks
    shop_trinket_points_per_check: ShopTrinketPointsPerCheck
    shop_trinket_point_checks: ShopTrinketPoints
    currency_multiplier: CurrencyMultiplier
    shop_prices: ShopPrices
    shop_price_minimum: ShopPriceMinimum
    shop_price_maximum: ShopPriceMaximum
    currency_item_amount: CurrencyItemAmount
    extra_trinket_points: ExtraTrinketPoints
    extra_workshop_tokens: ExtraWorkshopTokens
    extra_oil_vials: ExtraOilVials
    extra_golden_feathers: ExtraGoldenFeathers
    filler_currency: FillerCurrency
    filler_boons: FillerBoons
    filler_traps: FillerTraps
    boons: Boons
    traps: Traps
    death_link: DeathLink
    death_link_amnesty: DeathLinkAmnesty
    death_wish: DeathWish

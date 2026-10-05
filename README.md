# Well Dweller – Archipelago

[Archipelago](https://archipelago.gg) multiworld support for **Well Dweller**: an APWorld (logic, options and the
Well Dweller Client) and a game mod for Aurie/YYToolkit.

> **Public test build (alpha).** Expect bugs and logic gaps. Please test with the Logic Test world and report in
> the Discord - see "Testing with Logic Test" in [docs/setup_en.md](docs/setup_en.md).

## Contents
- Repository root: the APWorld package (`well_dweller`). Releases ship it as `well_dweller.apworld`.
- `docs/setup_en.md`: setup guide, client commands and in-game features.
- `mod/`: source of the game mod (`WellDwellerAP.dll`). See `mod/README.md` for build steps.

## Quick start
1. Install Aurie/YYToolkit for Well Dweller and copy `WellDwellerAP.dll` to `<Well Dweller>\mods\aurie\`.
2. Install `well_dweller.apworld` (double-click it, or copy it to Archipelago's `custom_worlds`).
3. Generate with a Well Dweller YAML, start **Well Dweller Client** from the Archipelago Launcher, connect,
   then start a new game in an empty save slot.

Release files: `well_dweller.apworld`, `WellDwellerAP.dll`, `Well Dweller.yaml` (template) and `Logic Test.yaml`.

See [docs/setup_en.md](docs/setup_en.md) for details.

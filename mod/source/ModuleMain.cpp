// Well Dweller Archipelago mod (Aurie + YYToolkit v5).
//
// Talks to the Archipelago client through text files in <game folder>\archipelago\:
//   items.txt   written by the client: "slot <seed> <slot>", "opt <name> <value>", "trinket <item id> <index>",
//               then one "<index> <item id>" line per received item
//   checks.txt  appended by the mod:   "key <persistent key>" and "grant <variable> <room>" lines
//   state.txt   rewritten by the mod every second: watched variables, room, applied item count
//   mod.log     diagnostics
//
// Item handling:
//  * Abilities and key items are enforced: the game variable always matches what the multiworld sent.
//    If the game raises one by itself (a vanilla pickup), a "grant" line is written and the value is reset.
//  * Consumables (currency, tokens, trinket points, oil vials) are applied once, in order. The number
//    applied is stored in the game's persistent variables ("ap_applied"), so it is saved and loaded
//    together with the rest of the save file. Vanilla increases of trinket points, workshop tokens and
//    oil vials are reverted (they are location checks now).
//  * A save is bound to one slot ("ap_slot" persistent variable). A save without it is only claimed
//    when it is a fresh game (percent < 1) or the client asks for it; other saves are left alone and
//    report nothing, so an old 100% save cannot send checks or lose items.

#include <YYToolkit/YYTK_Shared.hpp>
#include <fstream>
#include <sstream>
#include <map>
#include <set>
#include <vector>
#include <string>
#include <cstdio>
#include <ctime>
#include <cmath>
#include <cstring>
#include <cctype>

using namespace Aurie;
using namespace YYTK;

static constexpr const char* MOD_VERSION = "0.1.0";

static YYTKInterface* g_Yytk = nullptr;
static fs::path g_Dir;
static std::ofstream g_Log;

// ---------------------------------------------------------------- logging / formatting

static std::string Timestamp()
{
	char buf[32];
	std::time_t t = std::time(nullptr);
	std::tm tm_local{};
	localtime_s(&tm_local, &t);
	std::strftime(buf, sizeof(buf), "%H:%M:%S", &tm_local);
	return buf;
}

static void Log(const std::string& Message)
{
	if (g_Log.is_open())
	{
		g_Log << "[" << Timestamp() << "] " << Message << "\n";
		g_Log.flush();
	}
	DbgPrintEx(LOG_SEVERITY_INFO, "[WD-AP] %s", Message.c_str());
}

static std::string Num(double V)
{
	char buf[64];
	std::snprintf(buf, sizeof(buf), "%.10g", V);
	return buf;
}

static std::string Describe(const RValue& Value)
{
	try
	{
		if (Value.IsUndefined()) return "undefined";
		if (Value.IsString()) return "\"" + Value.ToString() + "\"";
		if (Value.IsArray())
		{
			RValue copy = Value;
			size_t n = 0;
			g_Yytk->GetArraySize(copy, n);
			std::string out = "[";
			for (size_t i = 0; i < n && i < 64; i++)
			{
				RValue* e = nullptr;
				if (i) out += ",";
				if (AurieSuccess(g_Yytk->GetArrayEntry(copy, i, e)) && e && e->IsNumberConvertible())
					out += Num(e->ToDouble());
				else
					out += "?";
			}
			return out + "]";
		}
		if (Value.IsStruct()) return "<" + Value.GetKindName() + ">";
		if (Value.IsNumberConvertible()) return Num(Value.ToDouble());
		return "<" + Value.GetKindName() + ">";
	}
	catch (...)
	{
		return "<unreadable>";
	}
}

// ---------------------------------------------------------------- game access helpers

static CInstance* Global()
{
	CInstance* g = nullptr;
	g_Yytk->GetGlobalInstance(&g);
	return g;
}

static RValue* GlobalRef(const char* Name)
{
	CInstance* g = Global();
	RValue* member = nullptr;
	if (!g || !AurieSuccess(g_Yytk->GetInstanceMember(g, Name, member)))
		return nullptr;
	return member;
}

static bool GetNumber(const char* Name, double& Out)
{
	RValue* v = GlobalRef(Name);
	if (!v || !v->IsNumberConvertible())
		return false;
	Out = v->ToDouble();
	return true;
}

static void SetNumber(const char* Name, double Value)
{
	RValue* v = GlobalRef(Name);
	if (v)
		*v = RValue(Value);
}

static std::string CurrentRoomName()
{
	try
	{
		RValue room;
		if (!AurieSuccess(g_Yytk->GetBuiltin("room", nullptr, NULL_INDEX, room)))
			return "?";
		RValue name = g_Yytk->CallBuiltin("room_get_name", { room });
		return name.IsString() ? name.ToString() : "?";
	}
	catch (...)
	{
		return "?";
	}
}

static bool InGameplayRoom(const std::string& Room)
{
	if (Room.size() < 3) return false;
	if (Room.rfind("rm_", 0) == 0 || Room == "InitRoom" || Room == "r_load" || Room == "AB_02_boot") return false;
	bool area = Room[0] == 'A' && isupper(static_cast<unsigned char>(Room[1])) && Room[2] == '_';
	if (!(area || Room.rfind("r_", 0) == 0)) return false;
	RValue* name = GlobalRef("area_name");
	return name && name->IsString() && !name->ToString().empty();
}

// persistent_vars ds_map
static bool PersistentMap(RValue& Map)
{
	RValue* m = GlobalRef("persistent_vars");
	if (!m || m->IsUndefined())
		return false;
	Map = *m;
	return g_Yytk->CallBuiltin("ds_exists", { Map, RValue(1.0) }).ToBoolean();
}

static std::vector<std::string> PersistentKeys()
{
	std::vector<std::string> out;
	RValue map;
	if (!PersistentMap(map))
		return out;
	RValue keys = g_Yytk->CallBuiltin("ds_map_keys_to_array", { map });
	size_t n = 0;
	if (!keys.IsArray() || !AurieSuccess(g_Yytk->GetArraySize(keys, n)))
		return out;
	for (size_t i = 0; i < n; i++)
	{
		RValue* k = nullptr;
		if (AurieSuccess(g_Yytk->GetArrayEntry(keys, i, k)) && k && k->IsString())
			out.push_back(k->ToString());
	}
	return out;
}

static bool PvarExists(const std::string& Key)
{
	RValue map;
	if (!PersistentMap(map))
		return false;
	return g_Yytk->CallBuiltin("ds_map_exists", { map, RValue(std::string_view(Key)) }).ToBoolean();
}

static double PvarNumber(const std::string& Key, double Default)
{
	RValue map;
	if (!PersistentMap(map))
		return Default;
	RValue v = g_Yytk->CallBuiltin("ds_map_find_value", { map, RValue(std::string_view(Key)) });
	if (v.IsUndefined()) return Default;
	if (v.IsNumberConvertible()) return v.ToDouble();
	if (v.IsString()) { try { return std::stod(v.ToString()); } catch (...) { return Default; } }
	return Default;
}

static std::string PvarString(const std::string& Key)
{
	RValue map;
	if (!PersistentMap(map))
		return "";
	RValue v = g_Yytk->CallBuiltin("ds_map_find_value", { map, RValue(std::string_view(Key)) });
	if (v.IsString()) return v.ToString();
	if (v.IsNumberConvertible()) return Num(v.ToDouble());
	return "";
}

static void PvarSet(const std::string& Key, const RValue& Value)
{
	RValue map;
	if (PersistentMap(map))
		g_Yytk->CallBuiltin("ds_map_set", { map, RValue(std::string_view(Key)), Value });
}

// Add a named flag the way the game does (Persistent_Var_Add stores the string "1").
static void PvarAddFlag(const std::string& Key)
{
	RValue result;
	AurieStatus st = AURIE_EXTERNAL_ERROR;
	try { st = g_Yytk->CallGameScriptEx(result, "gml_Script_Persistent_Var_Add", Global(), Global(), { RValue(std::string_view(Key)) }); }
	catch (...) {}
	if (!AurieSuccess(st) || !PvarExists(Key))
		PvarSet(Key, RValue(std::string_view("1")));
}

static void PvarDelete(const std::string& Key)
{
	RValue map;
	if (PersistentMap(map))
		g_Yytk->CallBuiltin("ds_map_delete", { map, RValue(std::string_view(Key)) });
}

// ---------------------------------------------------------------- files

static std::string CurrentSlot(); // defined below

// Every line is tagged with the slot it belongs to, so a client connected to another seed ignores it.
static void AppendCheck(const std::string& Line)
{
	std::ofstream f(g_Dir / "checks.txt", std::ios::app);
	f << "[" << CurrentSlot() << "] " << Line << "\n";
}

struct ReceivedItems
{
	std::string Slot;
	std::vector<int> Ids;                  // by index
	std::map<std::string, double> Opts;    // "opt <name> <value>"
	std::map<int, int> TrinketIndex;       // item id -> upgrade_list index
	std::map<int, int> MaxLevel;           // upgrade_list index -> highest forge level
};

static ReceivedItems g_Items;
static std::string CurrentSlot() { return g_Items.Slot; }
static fs::file_time_type g_ItemsStamp{};

static void ReadItemsFile()
{
	std::error_code ec;
	fs::path p = g_Dir / "items.txt";
	auto stamp = fs::last_write_time(p, ec);
	if (ec || stamp == g_ItemsStamp)
		return;
	g_ItemsStamp = stamp;
	std::ifstream f(p);
	ReceivedItems next;
	std::string line;
	while (std::getline(f, line))
	{
		if (!line.empty() && line.back() == '\r') line.pop_back();
		if (line.rfind("slot ", 0) == 0) { next.Slot = line.substr(5); continue; }
		std::istringstream ss(line);
		if (line.rfind("opt ", 0) == 0)
		{
			std::string tag, name; double v = 0;
			if (ss >> tag >> name >> v) next.Opts[name] = v;
			continue;
		}
		if (line.rfind("maxlevel ", 0) == 0)
		{
			std::string tag; int idx = -1, lvl = 1;
			if (ss >> tag >> idx >> lvl && idx >= 0) next.MaxLevel[idx] = lvl;
			continue;
		}
		if (line.rfind("trinket ", 0) == 0)
		{
			std::string tag; int id = 0, idx = -1;
			if (ss >> tag >> id >> idx && idx >= 0) next.TrinketIndex[id] = idx;
			continue;
		}
		int index = -1, id = 0;
		if (ss >> index >> id && index >= 0)
		{
			if (static_cast<size_t>(index) >= next.Ids.size()) next.Ids.resize(index + 1, 0);
			next.Ids[index] = id;
		}
	}
	if (next.Ids.size() != g_Items.Ids.size() || next.Slot != g_Items.Slot)
		Log("items.txt: " + std::to_string(next.Ids.size()) + " items for slot " + next.Slot);
	g_Items = std::move(next);
}

// ---------------------------------------------------------------- item tables (ids match the apworld)

static double Opt(const char* Name, double Default)
{
	auto it = g_Items.Opts.find(Name);
	return it == g_Items.Opts.end() ? Default : it->second;
}

static int Count(int Id)
{
	int n = 0;
	for (int i : g_Items.Ids) if (i == Id) n++;
	return n;
}

struct Enforced { const char* Var; int ItemId; int MinCount; }; // var = 1 when count(item) >= MinCount, else 0
static const Enforced FLAGS[] = {
	{ "has_match", 1, 1 },
	{ "up_sling", 2, 1 },
	{ "up_climb", 3, 1 },
	{ "up_unlimited_stamina", 3, 2 },
	{ "up_wind_ride", 4, 1 },
	{ "up_hover", 5, 1 },
	{ "up_wall_sling", 6, 1 },
	{ "up_fly", 7, 1 },
	{ "up_boat", 8, 1 },
};
struct Counted { const char* Var; int ItemId; };   // var = count(item)
static const Counted COUNTS[] = {
	{ "elevator_parts", 21 },
	{ "fish_gate", 22 },
	{ "golden_feathers", 23 },
	{ "spirits_found", 28 },
};
struct PvarFlag { const char* Key; int ItemId; };  // persistent key present only with the item
static const PvarFlag PVAR_FLAGS[] = {
	{ "torpedo", 9 },
	{ "tent_travel", 10 },
};
// consumables: applied once per received copy
static void ApplyConsumable(int Id)
{
	double v = 0;
	switch (Id)
	{
	case 40: if (GetNumber("upgrade_tokens", v)) SetNumber("upgrade_tokens", v + 1); break;
	case 41:
		if (GetNumber("upgrade_points", v)) SetNumber("upgrade_points", v + 1);
		if (GetNumber("upgrade_points_current", v)) SetNumber("upgrade_points_current", v + 1);
		break;
	case 42: break; // oil vials are enforced through collected_potions (EnforceItems)
	case 43: if (GetNumber("hit_bar_max", v)) SetNumber("hit_bar_max", v + 8); Log("Flaming Vessel Upgrade: +8"); break;
	case 60: if (GetNumber("currency", v)) SetNumber("currency", v + std::round(Opt("currency_item", 500) * Opt("currency_multiplier", 100) / 100.0)); break;
	// boons
	case 70: if (GetNumber("currency", v)) SetNumber("currency", v + std::round(5 * Opt("currency_item", 500) * Opt("currency_multiplier", 100) / 100.0)); Log("boon: Big Currency"); break;
	case 71: if (GetNumber("player_max_health", v)) SetNumber("player_health", v); Log("boon: Full Heal"); break;
	case 72: if (GetNumber("health_vials_max", v)) SetNumber("health_vials", v); Log("boon: Vial Refill"); break;
	// traps
	case 80: if (GetNumber("currency", v)) SetNumber("currency", std::floor(v * 0.75)); Log("trap: Thief"); break;
	case 81:
		if (GetNumber("player_health", v) && v > 1) SetNumber("player_health", std::max(1.0, v - std::ceil(v / 3)));
		Log("trap: Bruise"); break;
	case 82: SetNumber("health_vials", 0); Log("trap: Spill"); break;
	default: break; // not handled yet (logged by the client)
	}
}

// ---------------------------------------------------------------- main loop

static std::set<std::string> g_ReportedKeys;
static std::string g_LastRoom;
static bool g_WasInGame = false;
static ULONGLONG g_LastTick = 0, g_LastState = 0;
static bool g_F5 = false;
static std::string g_SaveStatus = "no save loaded";
static ULONGLONG g_InGameSince = 0;

// Tent NPCs available from the start: Looter (shop), frog (forge), mouse (map markers).
// Ilda (mouse) also needs her Bog meetings (first_mouse / second_mouse / second_mouse_two) - confirmed in game.
// After a skipped tutorial the game plays its "wake up at the nest" scene, which expects the ability to
// be owned. The ability is lent for that scene (from the skip until a few seconds after arriving back
// at the nest) and then taken back without counting as a vanilla grant.
static std::string g_LentVar, g_LentRoom;
static ULONGLONG g_LentUntil = 0;   // 0 = not back at the nest yet
static bool IsLent(const char* Var, ULONGLONG Now)
{
	return !g_LentVar.empty() && g_LentVar == Var && (g_LentUntil == 0 || Now < g_LentUntil);
}

// Trinkets sold by the Looter (upgrade_list indexes): Skull Keychain, Weathered Coin, Silver Ring,
// Rusted Thimble, Bottle Cap, Glass Eye.
static const int SHOP_TRINKETS[] = { 0, 12, 16, 18, 20, 21 };
static bool IsShopTrinket(int i) { for (int s : SHOP_TRINKETS) if (s == i) return true; return false; }

// o_inside_tent_control's Create event (disassembled) shows each tent NPC when its trigger flag exists:
// Ilda second_mouse, Looter cabin_lights, Willow feather_drain (handled separately: it is a location key).
static const char* SHOP_FLAGS[] = { "looter_show_tent", "frog_show_tent", "mouse_show_tent",
	"first_mouse", "second_mouse", "second_mouse_two", "cabin_lights" };

// Willow's trigger is feather_drain, which the game sets when her friends are rescued in AL_01 (a check).
// The mod keeps its own copy of the flag everywhere except around AL_01, so the rescue still happens
// there; while "ap_fd_masked" is set the flag is never reported. The real rescue clears the mask.
static const char* FD_KEY = "feather_drain";
static const char* FD_ZONE[] = { "AL_01", "AL_02", "AP_30" };
static bool g_FdRemovedInZone = false;

static void ManageWillowFlag(const std::string& Room)
{
	if (Opt("open_shops", 1) < 1) return;
	if (!PvarExists("ap_fd_masked"))
	{
		if (PvarExists(FD_KEY) || PvarExists("ap_fd_done")) return; // real rescue already done
		PvarSet("ap_fd_masked", RValue(1.0));
		Log("Willow: managing feather_drain until her friends are rescued");
	}
	bool inZone = false;
	for (const char* z : FD_ZONE) if (Room == z) inZone = true;
	bool exists = PvarExists(FD_KEY);
	if (inZone)
	{
		if (!g_FdRemovedInZone) { if (exists) PvarDelete(FD_KEY); g_FdRemovedInZone = true; Log("Willow: flag removed near AL_01"); }
		else if (exists)
		{
			// set by the game itself: the friends were rescued
			PvarDelete("ap_fd_masked");
			PvarSet("ap_fd_done", RValue(1.0));
			Log("Willow: friends rescued in " + Room);
		}
	}
	else
	{
		g_FdRemovedInZone = false;
		if (!exists) PvarAddFlag(FD_KEY);
	}
}

static void UnlockShops()
{
	if (Opt("open_shops", 1) < 1) return;
	RValue map;
	if (!PersistentMap(map)) return;
	for (const char* k : SHOP_FLAGS)
		if (!g_Yytk->CallBuiltin("ds_map_find_value", { map, RValue(std::string_view(k)) }).IsString())
		{
			PvarDelete(k); // stored as a number by mistake; the game stores the string "1"
			PvarAddFlag(k);
			Log(std::string("unlocked tent NPC: ") + k);
		}
}

#include "MapFull.inc"

// Reveal the whole map once per save (no spoiler concerns for AP players): copy the completed map
// into global.map_system[? "map_array"][x][y], keeping anything the player already explored.
static void RevealMap()
{
	if (Opt("reveal_map", 1) < 1 || PvarExists("ap_map_revealed2")) return;
	RValue* sys = GlobalRef("map_system");
	if (!sys || sys->IsUndefined()) return;
	RValue cols = g_Yytk->CallBuiltin("ds_map_find_value", { *sys, RValue(std::string_view("map_array")) });
	size_t w = 0;
	if (!cols.IsArray() || !AurieSuccess(g_Yytk->GetArraySize(cols, w)) || w == 0) return;
	int changed = 0;
	for (size_t x = 0; x < w && x < static_cast<size_t>(MAP_W); x++)
	{
		RValue* col = nullptr;
		size_t h = 0;
		if (!AurieSuccess(g_Yytk->GetArrayEntry(cols, x, col)) || !col || !col->IsArray()) continue;
		if (!AurieSuccess(g_Yytk->GetArraySize(*col, h))) continue;
		for (size_t y = 0; y < h && y < static_cast<size_t>(MAP_H); y++)
		{
			double want = MAP_FULL[y * MAP_W + x] - '0';
			RValue* cell = nullptr;
			if (want <= 0 || !AurieSuccess(g_Yytk->GetArrayEntry(*col, y, cell)) || !cell) continue;
			double cur = cell->IsNumberConvertible() ? cell->ToDouble() : 0;
			if (want > cur) { *cell = RValue(want); changed++; }
		}
	}
	// The map is also kept as a string (map_system[? "map"], saved as map_full); merge that too.
	RValue str = g_Yytk->CallBuiltin("ds_map_find_value", { *sys, RValue(std::string_view("map")) });
	if (str.IsString())
	{
		std::string s = str.ToString();
		if (s.size() < static_cast<size_t>(MAP_W * MAP_H)) s.resize(MAP_W * MAP_H, '0');
		int strChanged = 0;
		for (size_t i = 0; i < static_cast<size_t>(MAP_W * MAP_H); i++)
			if (MAP_FULL[i] > s[i]) { s[i] = MAP_FULL[i]; strChanged++; }
		g_Yytk->CallBuiltin("ds_map_set", { *sys, RValue(std::string_view("map")), RValue(std::string_view(s)) });
		Log("map string: " + std::to_string(strChanged) + " cells");
	}
	else
		Log("map string not found (" + str.GetKindName() + ")");
	RValue result;
	g_Yytk->CallGameScriptEx(result, "gml_Script_refresh_map", Global(), Global(), {});
	PvarSet("ap_map_revealed2", RValue(1.0));
	Log("revealed the map (" + std::to_string(changed) + " cells, map " + std::to_string(w) + " wide)");
}

#include "Tents.inc"

// Tent unlocks (opt tents): 0 vanilla, 1 all unlocked, 2 shuffled (tent items 200+i). Queen's Castle
// tents are not in TENTS and always behave as in the game.
static RValue GlobalValue(const char* Name)
{
	RValue* v = GlobalRef(Name);
	return v ? *v : RValue();
}

static bool TentListed(const RValue& List, const char* Key)
{
	RValue i = g_Yytk->CallBuiltin("ds_list_find_index", { List, RValue(std::string_view(Key)) });
	return i.IsNumberConvertible() && i.ToDouble() >= 0;
}

// Shuffled tents: a tent is also unlocked for good once the player finds it (enters it, or the game adds it
// while the player is in its room). Remembered as "ap_tent_found_<key>".
static void ManageTents(const std::string& Room, const std::string& PrevRoom)
{
	int mode = static_cast<int>(Opt("tents", 0));
	if (mode == 0) return;
	RValue list = GlobalValue("teleporters"), map = GlobalValue("teleporters_map"), marks = GlobalValue("map_marks");
	if (list.IsUndefined() || map.IsUndefined()) return;
	if (!g_Yytk->CallBuiltin("ds_exists", { list, RValue(2.0) }).ToBoolean()) return; // 2 = ds_type_list
	bool haveMarks = !marks.IsUndefined() && g_Yytk->CallBuiltin("ds_exists", { marks, RValue(1.0) }).ToBoolean();
	int added = 0, removed = 0;
	for (size_t i = 0; i < sizeof(TENTS) / sizeof(TENTS[0]); i++)
	{
		const Tent& t = TENTS[i];
		bool have = TentListed(list, t.Key);
		std::string foundKey = std::string("ap_tent_found_") + t.Key;
		if (mode == 2 && !PvarExists(foundKey)
			&& ((Room == "r_inside_tent" && PrevRoom == t.Room) || (Room == t.Room && have)))
		{
			PvarAddFlag(foundKey);
			Log(std::string("tent found: ") + t.Room);
		}
		bool want = mode == 1 || Count(200 + static_cast<int>(i)) > 0 || PvarExists(foundKey);
		bool marked = haveMarks && g_Yytk->CallBuiltin("ds_map_exists", { marks, RValue(std::string_view(t.MarkKey)) }).ToBoolean();
		if (want)
		{
			if (!have)
			{
				g_Yytk->CallBuiltin("ds_list_add", { list, RValue(std::string_view(t.Key)) });
				RValue entry = g_Yytk->CallBuiltin("json_parse", { RValue(std::string_view(t.Json)) });
				g_Yytk->CallBuiltin("ds_map_set", { map, RValue(std::string_view(t.Key)), entry });
				added++;
			}
			if (haveMarks && !marked)
			{
				// the tent icon on the map (also what the teleport menu shows)
				RValue mark = g_Yytk->CallBuiltin("json_parse", { RValue(std::string_view(t.MarkJson)) });
				g_Yytk->CallBuiltin("ds_map_set", { marks, RValue(std::string_view(t.MarkKey)), mark });
				added++;
			}
		}
		else
		{
			if (have)
			{
				RValue idx = g_Yytk->CallBuiltin("ds_list_find_index", { list, RValue(std::string_view(t.Key)) });
				g_Yytk->CallBuiltin("ds_list_delete", { list, idx });
				g_Yytk->CallBuiltin("ds_map_delete", { map, RValue(std::string_view(t.Key)) });
				removed++;
			}
			if (marked) { g_Yytk->CallBuiltin("ds_map_delete", { marks, RValue(std::string_view(t.MarkKey)) }); removed++; }
		}
	}
	if (added || removed)
	{
		RValue result;
		g_Yytk->CallGameScriptEx(result, "gml_Script_refresh_map", Global(), Global(), {});
		Log("tents: +" + std::to_string(added) + " -" + std::to_string(removed) + " (mode " + std::to_string(mode) + ", marks " + (haveMarks ? "yes" : "no") + ")");
	}
}

// Skip the opening in the Well: right after a fresh save is claimed in r_Well, mark the intro as seen
// and go straight to the Night Garden (AN_01, the room above the Well).
#include "Hud.inc"

static bool SkipIntro(const std::string& Room)
{
	if (Opt("skip_intro", 1) < 1 || PvarExists("ap_intro_done")) return false;
	PvarSet("ap_intro_done", RValue(1.0));
	if (Room != "r_Well" || PvarExists("left_well")) return false;
	for (const char* k : { "Show_Well", "left_well" })
		if (!PvarExists(k)) PvarAddFlag(k);
	RValue target = g_Yytk->CallBuiltin("asset_get_index", { RValue(std::string_view("AN_01")) });
	if (target.IsUndefined()) { Log("skip intro: room AN_01 not found"); return false; }
	g_Yytk->CallBuiltin("room_goto", { target });
	Log("skip intro: r_Well -> AN_01");
	return true;
}

#include "Levers.inc"

// Lever items (opt lever_items): a lever's own save key is also what keeps its gate open.
// - item received: set the key (gate open). The mod marks it with "ap_lv_<key>" so ReportKeys does not send the
//   lever's own check for it; that check is sent the first time the player is in the lever's room.
// - key set by a pull without the item: the pull was reported as a check by ReportKeys; remove the key
//   again and restart the room so the gate is closed. The player is put back where they stood.
static bool InstanceXY(const char* Object, RValue& Inst, double& X, double& Y, std::string& Why);
static void ClearGateLocks();
static std::string g_RestoreRoom;
static double g_RestoreX = 0, g_RestoreY = 0;
static ULONGLONG g_RestoreAt = 0;
static int g_RestoreTries = 0;

static const LeverItem* LeverByKey(const std::string& Key)
{
	for (const LeverItem& l : LEVERS) if (Key == l.Key) return &l;
	return nullptr;
}

static void ManageLevers(const std::string& Room, ULONGLONG Now)
{
	if (Opt("lever_items", 0) < 1) return;
	bool restart = false, opened = false;
	for (const LeverItem& l : LEVERS)
	{
		bool owned = Count(l.ItemId) > 0;
		bool on = PvarExists(l.Key);
		if (owned && !on)
		{
			PvarAddFlag(std::string("ap_lv_") + l.Key);   // before the key, so it is never reported as a pull
			PvarAddFlag(l.Key);
			Log(std::string("lever item: opened ") + l.Key);
			opened = true;
		}
		else if (!owned && on)
		{
			PvarDelete(l.Key);
			Log(std::string("lever pulled without its item: closed ") + l.Key);
			if (Room == l.Room) restart = true;
		}
	}
	if (opened) ClearGateLocks();
	if (restart)
	{
		RValue player; double px = 0, py = 0; std::string why;
		if (InstanceXY("oPlayer", player, px, py, why))
		{
			g_RestoreRoom = Room; g_RestoreX = px; g_RestoreY = py; g_RestoreAt = Now + 300; g_RestoreTries = 0;
		}
		g_Yytk->CallBuiltin("room_restart", {});
	}
}

// The map shows a lock icon (a global.map_marks entry with a lock sprite) on a gate the player has seen closed.
// Pulling the lever removes it in the game; a gate opened by its lever item keeps it, so remove lock marks that sit
// on a gate whose lever key is set. Runs once per load, on room changes and whenever a lever item opens a gate.
static bool g_LockLogDone = false;
static std::string MarkSpriteName(const RValue& Mark)
{
	for (const char* field : { "sprite", "_sprite_zoom", "_sprite" })
	{
		RValue v = g_Yytk->CallBuiltin("variable_struct_get", { Mark, RValue(std::string_view(field)) });
		if (v.IsString()) return std::string(v.ToString());
		if (v.IsNumberConvertible() && !v.IsUndefined())
		{
			RValue n = g_Yytk->CallBuiltin("sprite_get_name", { v });
			if (n.IsString()) return std::string(n.ToString());
		}
	}
	return "";
}

static double MarkNumber(const RValue& Mark, const char* Field)
{
	RValue v = g_Yytk->CallBuiltin("variable_struct_get", { Mark, RValue(std::string_view(Field)) });
	return v.IsNumberConvertible() && !v.IsUndefined() ? v.ToDouble() : -1000.0;
}

static void ClearGateLocks()
{
	if (Opt("lever_items", 0) < 1) return;
	RValue marks = GlobalValue("map_marks");
	if (marks.IsUndefined() || !g_Yytk->CallBuiltin("ds_exists", { marks, RValue(1.0) }).ToBoolean()) return;
	RValue keys = g_Yytk->CallBuiltin("ds_map_keys_to_array", { marks });
	size_t n = 0;
	if (!keys.IsArray() || !AurieSuccess(g_Yytk->GetArraySize(keys, n))) return;
	int removed = 0;
	bool logAll = !g_LockLogDone;
	g_LockLogDone = true;
	for (size_t i = 0; i < n; i++)
	{
		RValue* k = nullptr;
		if (!AurieSuccess(g_Yytk->GetArrayEntry(keys, i, k)) || !k) continue;
		RValue mark = g_Yytk->CallBuiltin("ds_map_find_value", { marks, *k });
		if (!mark.IsStruct()) continue;
		std::string spr = MarkSpriteName(mark);
		if (spr.find("lock") == std::string::npos) continue;
		RValue roomV = g_Yytk->CallBuiltin("variable_struct_get", { mark, RValue(std::string_view("_room")) });
		std::string room = roomV.IsString() ? std::string(roomV.ToString()) : "";
		double x = MarkNumber(mark, "_xpos"), y = MarkNumber(mark, "_ypos");
		std::string keyText = k->IsString() ? std::string(k->ToString()) : Num(k->ToDouble());
		if (logAll) Log("map lock mark " + keyText + ": " + spr + " room " + room + " at " + Num(x) + "," + Num(y));
		for (const LeverGate& g : LEVER_GATES)
		{
			double d = std::hypot(x - g.X, y - g.Y);
			if (!((room == g.Room && d < 3.0) || d < 1.0)) continue;
			if (!PvarExists(g.Key)) continue;
			g_Yytk->CallBuiltin("ds_map_delete", { marks, *k });
			Log("map lock removed at " + keyText + " (gate of " + g.Key + ")");
			removed++;
			break;
		}
	}
	if (removed)
	{
		RValue result;
		g_Yytk->CallGameScriptEx(result, "gml_Script_refresh_map", Global(), Global(), {});
	}
}

// After a lever room restart: move the player back to where they pulled the lever.
static void RestoreAfterRestart(const std::string& Room, ULONGLONG Now)
{
	if (g_RestoreRoom.empty() || Now < g_RestoreAt) return;
	if (Room != g_RestoreRoom || g_RestoreTries >= 6) { g_RestoreRoom.clear(); return; }
	g_RestoreTries++;
	RValue player; double px = 0, py = 0; std::string why;
	if (!InstanceXY("oPlayer", player, px, py, why)) return;
	if (std::abs(px - g_RestoreX) > 8 || std::abs(py - g_RestoreY) > 8)
	{
		g_Yytk->CallBuiltin("variable_instance_set", { player, RValue(std::string_view("x")), RValue(g_RestoreX) });
		g_Yytk->CallBuiltin("variable_instance_set", { player, RValue(std::string_view("y")), RValue(g_RestoreY) });
		Log("lever room restart: player put back at " + Num(g_RestoreX) + "," + Num(g_RestoreY));
		g_RestoreTries = 4;   // one more check afterwards
	}
}

static bool IsPvarFlag(const std::string& Key)
{
	for (const PvarFlag& f : PVAR_FLAGS) if (Key == f.Key) return true;
	for (const char* k : SHOP_FLAGS) if (Key == k) return true;
	return false;
}

// Decide whether the loaded save belongs to the connected slot.
static bool SaveIsOurs()
{
	if (g_Items.Slot.empty()) { g_SaveStatus = "client not connected"; return false; }
	std::string owner = PvarString("ap_slot");
	if (owner == g_Items.Slot) { g_SaveStatus = "ok"; return true; }
	if (!owner.empty()) { g_SaveStatus = "save belongs to another slot (" + owner + ")"; return false; }
	// Give the game a few seconds after loading so the save's own values are in place.
	if (GetTickCount64() - g_InGameSince < 3000) { g_SaveStatus = "checking save"; return false; }
	double percent = 0;
	GetNumber("percent", percent);
	size_t keys = PersistentKeys().size();
	if ((percent >= 1 || keys >= 60) && Opt("claim", 0) < 1)
	{
		g_SaveStatus = "not an Archipelago save (start a new game, or use /claim in the client)";
		return false;
	}
	// Claim it: remember which trinkets the save already had.
	std::string bits;
	if (RValue* arr = GlobalRef("upgrade_list_binary"))
	{
		size_t n = 0;
		if (arr->IsArray() && AurieSuccess(g_Yytk->GetArraySize(*arr, n)))
			for (size_t i = 0; i < n; i++)
			{
				RValue* e = nullptr;
				bool on = AurieSuccess(g_Yytk->GetArrayEntry(*arr, i, e)) && e && e->IsNumberConvertible() && e->ToDouble() > 0;
				bits += on ? '1' : '0';
			}
	}
	PvarSet("ap_slot", RValue(std::string_view(g_Items.Slot)));
	PvarSet("ap_base_trinkets", RValue(std::string_view(bits)));
	Log("claimed this save for slot " + g_Items.Slot + " (percent " + Num(percent) + ", " + std::to_string(keys) + " keys, trinkets " + bits + ")");
	g_SaveStatus = "ok";
	return true;
}

static void MarkShopTrinketBought(int Idx, const char* How)
{
	std::string key = "ap_shop_trinket_" + std::to_string(Idx);
	if (PvarExists(key)) return;
	PvarSet(key, RValue(1.0));
	AppendCheck("shop trinket " + std::to_string(Idx));
	Log("shop trinket " + std::to_string(Idx) + " bought (check only, " + How + ")");
}

// The Looter's shop shows a trinket as sold when upgrade_list_binary says it is owned. While the shop window
// is open (o_looter_popupshop.mode == 1) the 6 shop trinkets are shown as owned only when they were bought there,
// so received-but-unbought ones are for sale and bought ones stay sold. A trinket that turns owned while the
// window is open was just bought: that is the check. When the window closes, the real state is put back
// (levels and equipped slots).
struct ShopSaved { double Level = 0, Active = -1; };
static bool g_ShopWindow = false;
static std::map<int, ShopSaved> g_ShopSaved;

// shop.txt (from the client): "s\t<sel_ii>\t<name>\t<description>" - what a shop entry gives the multiworld.
static std::map<int, std::pair<std::string, std::string>> g_ShopText;
static std::string g_ForgeText;   // what the next forge upgrade (check) gives the multiworld
static fs::file_time_type g_ShopTextStamp{};
static void ReadShopText()
{
	fs::path p = g_Dir / "shop.txt";
	std::error_code ec;
	auto stamp = fs::last_write_time(p, ec);
	if (ec || stamp == g_ShopTextStamp) return;
	g_ShopTextStamp = stamp;
	std::ifstream f(p);
	if (!f) return;
	g_ShopText.clear();
	g_ForgeText.clear();
	std::string line;
	while (std::getline(f, line))
	{
		if (!line.empty() && line.back() == '\r') line.pop_back();
		std::vector<std::string> parts;
		size_t start = 0;
		while (true)
		{
			size_t t = line.find('\t', start);
			parts.push_back(line.substr(start, t == std::string::npos ? std::string::npos : t - start));
			if (t == std::string::npos) break;
			start = t + 1;
		}
		if (parts.size() >= 4 && parts[0] == "s") g_ShopText[std::atoi(parts[1].c_str())] = { parts[2], parts[3] };
		if (parts.size() >= 4 && parts[0] == "f") g_ForgeText = parts[2] + ". " + parts[3];
	}
}

static RValue ShopInstance()
{
	static RValue obj;
	if (obj.IsUndefined()) obj = g_Yytk->CallBuiltin("asset_get_index", { RValue(std::string_view("o_looter_popupshop")) });
	return g_Yytk->CallBuiltin("instance_find", { obj, RValue(0.0) });
}

// Shows what the selected shop entry gives the multiworld (name and description in the shop window).
static void ShopShowItem(const RValue& Inst)
{
	// The selected entry: trinkets by sel_ii; the other entries (6 Trinket Point, 7 Flaming Vessel, 8 Oil Vial)
	// by purchase_array[sel], because sel_ii is only kept up to date for trinkets.
	RValue ii = g_Yytk->CallBuiltin("variable_instance_get", { Inst, RValue(std::string_view("sel_ii")) });
	RValue sel = g_Yytk->CallBuiltin("variable_instance_get", { Inst, RValue(std::string_view("sel")) });
	RValue items = g_Yytk->CallBuiltin("variable_instance_get", { Inst, RValue(std::string_view("purchase_array")) });
	int selIi = ii.IsNumberConvertible() ? static_cast<int>(ii.ToDouble()) : -1;
	int selIdx = sel.IsNumberConvertible() ? static_cast<int>(sel.ToDouble()) : -1;
	int entry = -1;
	size_t n = 0;
	if (selIdx >= 0 && items.IsArray() && AurieSuccess(g_Yytk->GetArraySize(items, n)) && static_cast<size_t>(selIdx) < n)
	{
		RValue* e = nullptr;
		if (AurieSuccess(g_Yytk->GetArrayEntry(items, static_cast<size_t>(selIdx), e)) && e && e->IsNumberConvertible())
			entry = static_cast<int>(e->ToDouble());
	}
	int key = (entry >= 6 && entry <= 9) ? entry : selIi;
	static int lastSel = -2, lastIi = -2;
	if (selIdx != lastSel || selIi != lastIi)
	{
		lastSel = selIdx; lastIi = selIi;
		RValue nm = g_Yytk->CallBuiltin("variable_instance_get", { Inst, RValue(std::string_view("sel_name")) });
		Log("shop selection: sel " + std::to_string(selIdx) + " -> entry " + std::to_string(entry) + ", sel_ii " +
			std::to_string(selIi) + ", name '" + (nm.IsString() ? nm.ToString() : std::string("?")) + "'");
	}
	auto it = g_ShopText.find(key);
	if (it == g_ShopText.end()) return;
	g_Yytk->CallBuiltin("variable_instance_set", { Inst, RValue(std::string_view("sel_name")), RValue(std::string_view(it->second.first)) });
	g_Yytk->CallBuiltin("variable_instance_set", { Inst, RValue(std::string_view("sel_des")), RValue(std::string_view(it->second.second)) });
}

// Forge window (o_upgrade_trinkets): the "next level" text shows what the next forge check gives.
static void ForgeShowItem()
{
	if (g_ForgeText.empty()) return;
	static RValue obj;
	if (obj.IsUndefined()) obj = g_Yytk->CallBuiltin("asset_get_index", { RValue(std::string_view("o_upgrade_trinkets")) });
	RValue inst = g_Yytk->CallBuiltin("instance_find", { obj, RValue(0.0) });
	if (inst.IsUndefined() || (inst.IsNumberConvertible() && inst.ToDouble() < 0)) return;
	RValue mode = g_Yytk->CallBuiltin("variable_instance_get", { inst, RValue(std::string_view("mode")) });
	if (!mode.IsNumberConvertible() || mode.ToDouble() < 1) return;
	g_Yytk->CallBuiltin("variable_instance_set", { inst, RValue(std::string_view("sel_upgrade_desc")), RValue(std::string_view(g_ForgeText)) });
}

// Shop prices (opt shopcost0..8, from the apworld's shop_prices option): written into the shop's cost_array
// (one price per shop entry, in shop order: 6 trinkets, Trinket Point, Flaming Vessel, Oil Vial).
static void ApplyShopPrices(const RValue& Inst)
{
	if (Opt("shopcost0", -1) < 0) return;
	RValue costs = g_Yytk->CallBuiltin("variable_instance_get", { Inst, RValue(std::string_view("cost_array")) });
	size_t n = 0;
	if (!costs.IsArray() || !AurieSuccess(g_Yytk->GetArraySize(costs, n))) return;
	static const char* NAMES[] = { "shopcost0", "shopcost1", "shopcost2", "shopcost3", "shopcost4", "shopcost5",
		"shopcost6", "shopcost7", "shopcost8" };
	bool changed = false;
	for (size_t i = 0; i < n && i < 9; i++)
	{
		double want = Opt(NAMES[i], -1);
		if (want < 0) continue;
		RValue* e = nullptr;
		if (!AurieSuccess(g_Yytk->GetArrayEntry(costs, i, e)) || !e) continue;
		if (!e->IsNumberConvertible() || e->ToDouble() != want) { *e = RValue(want); changed = true; }
	}
	if (changed)
	{
		// the price shown for the selected entry
		RValue sel = g_Yytk->CallBuiltin("variable_instance_get", { Inst, RValue(std::string_view("sel")) });
		if (sel.IsNumberConvertible())
		{
			int i = static_cast<int>(sel.ToDouble());
			if (i >= 0 && i < 9) g_Yytk->CallBuiltin("variable_instance_set", { Inst, RValue(std::string_view("sel_cost")), RValue(Opt(NAMES[i], 0)) });
		}
		Log("shop prices applied");
	}
}

static ULONGLONG g_ShopLastOpen = 0;
static bool ShopWindowOpen()
{
	RValue inst = ShopInstance();
	if (inst.IsUndefined() || (inst.IsNumberConvertible() && inst.ToDouble() < 0)) return false;
	ApplyShopPrices(inst);
	RValue mode = g_Yytk->CallBuiltin("variable_instance_get", { inst, RValue(std::string_view("mode")) });
	ULONGLONG now = GetTickCount64();
	if (mode.IsNumberConvertible() && mode.ToDouble() >= 1)
	{
		g_ShopLastOpen = now;
		ShopShowItem(inst);
		return true;
	}
	// a purchase briefly switches the window to mode 0; stay "open" for a moment so the purchase is seen
	return g_ShopWindow && now - g_ShopLastOpen < 2500;
}


static void ManageShopWindow(const std::string& Room)
{
	ReadShopText();
	if (Room == "r_inside_tent") ForgeShowItem();
	bool open = Room == "r_inside_tent" && ShopWindowOpen();
	if (!open && !g_ShopWindow) return;
	RValue* owned = GlobalRef("upgrade_list_binary");
	RValue* active = GlobalRef("upgrade_list_active");
	if (!owned || !owned->IsArray()) return;
	auto entry = [](RValue* Arr, int I) -> RValue*
	{
		RValue* e = nullptr;
		if (!Arr || !Arr->IsArray() || !AurieSuccess(g_Yytk->GetArrayEntry(*Arr, static_cast<size_t>(I), e))) return nullptr;
		return e;
	};
	if (open && !g_ShopWindow)
	{
		g_ShopWindow = true;
		g_ShopSaved.clear();
		for (int t : SHOP_TRINKETS)
		{
			RValue* e = entry(owned, t); RValue* a = entry(active, t);
			ShopSaved sv;
			if (e && e->IsNumberConvertible()) sv.Level = e->ToDouble();
			if (a && a->IsNumberConvertible()) sv.Active = a->ToDouble();
			g_ShopSaved[t] = sv;
			if (e) *e = RValue(PvarExists("ap_shop_trinket_" + std::to_string(t)) ? 1.0 : 0.0);
		}
		Log("shop window opened: shop trinkets show as sold only when bought");
		return;
	}
	if (open)
	{
		for (int t : SHOP_TRINKETS)
		{
			RValue* e = entry(owned, t);
			if (!e) continue;
			double cur = e->IsNumberConvertible() ? e->ToDouble() : 0;
			bool bought = PvarExists("ap_shop_trinket_" + std::to_string(t));
			if (!bought && cur > 0) MarkShopTrinketBought(t, "shop window");
			else if (bought && cur <= 0) *e = RValue(1.0);
		}
		return;
	}
	// window closed: put the real state back (EnforceItems corrects levels of received trinkets next tick)
	g_ShopWindow = false;
	for (auto& [t, sv] : g_ShopSaved)
	{
		RValue* e = entry(owned, t); RValue* a = entry(active, t);
		if (e) *e = RValue(sv.Level);
		if (a && sv.Active >= 0 && a->IsNumberConvertible() && a->ToDouble() < 0) *a = RValue(sv.Active);
	}
	g_ShopSaved.clear();
	Log("shop window closed: trinkets restored");
}

static int CountOf(const char* Object);
static void EnforceItems(const std::string& Room)
{
	ULONGLONG nowTick = GetTickCount64();
	if (!g_LentVar.empty() && g_LentUntil == 0 && Room == g_LentRoom) g_LentUntil = nowTick + 8000;
	if (!g_LentVar.empty() && g_LentUntil != 0 && nowTick >= g_LentUntil)
	{
		Log("returning lent " + g_LentVar);
		double want = 0;
		for (const Enforced& e : FLAGS) if (g_LentVar == e.Var) want = Count(e.ItemId) >= e.MinCount ? 1.0 : 0.0;
		SetNumber(g_LentVar.c_str(), want);
		g_LentVar.clear(); g_LentRoom.clear(); g_LentUntil = 0;
	}
	for (const Enforced& e : FLAGS)
	{
		double cur = 0;
		if (IsLent(e.Var, nowTick)) continue;
		if (!GetNumber(e.Var, cur)) continue;
		double want = Count(e.ItemId) >= e.MinCount ? 1.0 : 0.0;
		if (cur > want)
		{
			AppendCheck(std::string("grant ") + e.Var + " " + Room);
			Log(std::string("vanilla grant of ") + e.Var + " in " + Room + " -> reset");
		}
		if (cur != want) SetNumber(e.Var, want);
	}
	for (const Counted& c : COUNTS)
	{
		double cur = 0;
		if (!GetNumber(c.Var, cur)) continue;
		double want = Count(c.ItemId);
		if (cur > want)
		{
			AppendCheck(std::string("grant ") + c.Var + " " + Room + " " + Num(cur));
			Log(std::string("vanilla increase of ") + c.Var + " in " + Room + " -> reset");
		}
		if (cur != want) SetNumber(c.Var, want);
	}
	// Oil vials: the game derives the vial count from global.collected_potions (12 flags, one per
	// vial in the world). Received Oil Vials use the last slots; vanilla pickups are removed.
	if (RValue* pots = GlobalRef("collected_potions"))
	{
		size_t n = 0;
		int have = Count(42);
		if (pots->IsArray() && AurieSuccess(g_Yytk->GetArraySize(*pots, n)))
			for (size_t i = 0; i < n; i++)
			{
				RValue* e = nullptr;
				if (!AurieSuccess(g_Yytk->GetArrayEntry(*pots, i, e)) || !e) continue;
				double want = static_cast<int>(n - 1 - i) < have ? 1.0 : 0.0;
				double cur = e->IsNumberConvertible() ? e->ToDouble() : 0.0;
				if (cur > want)
				{
					AppendCheck("grant collected_potions " + Room + " " + std::to_string(i));
					Log("vanilla oil vial " + std::to_string(i) + " in " + Room + " -> removed");
					// the vial count itself was already reverted when it went up (TRACKED)
				}
				else if (cur < want)
				{
					double m = 0;
					if (GetNumber("health_vials_max", m)) SetNumber("health_vials_max", m + 1);
					if (GetNumber("health_vials", m)) SetNumber("health_vials", m + 1);
				}
				if (cur != want) *e = RValue(want);
			}
	}
	// Looter parts: array of 4 flags
	if (RValue* arr = GlobalRef("looter_parts"))
	{
		int have = Count(25);
		size_t n = 0;
		if (arr->IsArray() && AurieSuccess(g_Yytk->GetArraySize(*arr, n)))
			for (size_t i = 0; i < n; i++)
			{
				RValue* e = nullptr;
				if (!AurieSuccess(g_Yytk->GetArrayEntry(*arr, i, e)) || !e) continue;
				double want = static_cast<int>(i) < have ? 1.0 : 0.0;
				double cur = e->IsNumberConvertible() ? e->ToDouble() : 0.0;
				if (cur > want) AppendCheck("grant looter_parts " + Room + " " + std::to_string(i));
				if (cur != want) *e = RValue(want);
			}
	}
	for (const PvarFlag& f : PVAR_FLAGS)
	{
		bool want = Count(f.ItemId) > 0, cur = PvarExists(f.Key);
		if (cur && !want) { AppendCheck(std::string("grant ") + f.Key + " " + Room); PvarDelete(f.Key); }
		if (!cur && want) PvarAddFlag(f.Key);
	}
	// Trinkets: owned = owned when the save was claimed + received trinkets with a known index.
	// Looter's shop trinkets are check-only: buying one sends its check and gives nothing (see ManageShopWindow,
	// which keeps every unbought trinket in stock while the shop window is open, received ones included).
	RValue* owned = GlobalRef("upgrade_list_binary");
	RValue* active = GlobalRef("upgrade_list_active");
	size_t n = 0;
	if (owned && owned->IsArray() && AurieSuccess(g_Yytk->GetArraySize(*owned, n)))
	{
		std::string base = PvarString("ap_base_trinkets");
		std::vector<bool> received(n, false);
		for (size_t i = 0; i < n && i < base.size(); i++) received[i] = base[i] == '1';
		for (int id : g_Items.Ids)
		{
			auto it = g_Items.TrinketIndex.find(id);
			if (it != g_Items.TrinketIndex.end() && it->second >= 0 && static_cast<size_t>(it->second) < n)
				received[it->second] = true;
		}
		bool inTent = Room == "r_inside_tent";
		bool forgeItems = Opt("forge_items", 0) >= 1;
		for (size_t i = 0; i < n; i++)
		{
			RValue* e = nullptr;
			if (!AurieSuccess(g_Yytk->GetArrayEntry(*owned, i, e)) || !e) continue;
			double level = e->IsNumberConvertible() ? e->ToDouble() : 0;
			RValue* a = nullptr;
			bool haveActive = active && active->IsArray() && AurieSuccess(g_Yytk->GetArrayEntry(*active, i, a)) && a;
			bool equipped = haveActive && a->IsNumberConvertible() && a->ToDouble() >= 0;
			int idx = static_cast<int>(i);
			bool real = received[i];
			if (g_ShopWindow && IsShopTrinket(idx)) continue;   // ManageShopWindow owns these while the shop is open
			if (!real)
			{
				if (level > 0)
				{
					if (inTent && IsShopTrinket(idx))
						MarkShopTrinketBought(idx, "owned");
					else
					{
						AppendCheck("grant trinket " + Room + " " + std::to_string(i));
						Log("vanilla trinket " + std::to_string(i) + " in " + Room + " -> removed");
					}
					*e = RValue(0.0);
				}
				if (equipped)
				{
					*a = RValue(-1.0);
					Log("trinket " + std::to_string(i) + " not received -> unequipped");
				}
				continue;
			}
			if (!forgeItems)
			{
				if (level <= 0) *e = RValue(1.0);
				continue;
			}
			auto ml = g_Items.MaxLevel.find(idx);
			int maxLevel = ml == g_Items.MaxLevel.end() ? 3 : ml->second;
			double want = 1 + std::min(Count(500 + idx), maxLevel - 1);
			if (level > want && level > 0)
			{
				int steps = static_cast<int>(level - want);
				int count = static_cast<int>(PvarNumber("ap_forge_count", 0)) + steps;
				PvarSet("ap_forge_count", RValue(static_cast<double>(count)));
				AppendCheck("forge " + std::to_string(count));
				Log("forge purchase on trinket " + std::to_string(i) + " -> check " + std::to_string(count) + ", level back to " + Num(want));
			}
			if (level != want) *e = RValue(want);
		}
	}
}

// Resources the multiworld hands out. Vanilla increases are reverted; our own are applied on top.
struct Tracked { const char* Var; const char* Current; };
static const Tracked TRACKED[] = {
	{ "upgrade_points", "upgrade_points_current" },
	{ "upgrade_tokens", nullptr },
	{ "health_vials_max", "health_vials" },
	{ "hit_bar_max", nullptr },          // flaming vessel capacity (+8 per Flaming Vessel Upgrade)
};
static std::map<std::string, double> g_Last;
static double g_LastBoughtSlots = -1;

static void RememberTracked()
{
	for (const Tracked& t : TRACKED)
	{
		double v = 0;
		if (GetNumber(t.Var, v)) g_Last[t.Var] = v;
	}
	GetNumber("bought_slots", g_LastBoughtSlots);
}

static void RevertVanillaResources(const std::string& Room)
{
	double bought = 0;
	GetNumber("bought_slots", bought);
	// Trinket points bought in the shop: purchases that count toward the milestone checks lose their effect
	// (the Trinket Points come from the multiworld); purchases beyond the last milestone keep it.
	bool shopPurchase = bought > g_LastBoughtSlots && bought > Opt("shop_per", 1) * Opt("shop_points", 0);
	for (const Tracked& t : TRACKED)
	{
		double cur = 0;
		auto last = g_Last.find(t.Var);
		if (!GetNumber(t.Var, cur) || last == g_Last.end() || cur <= last->second) continue;
		double delta = cur - last->second;
		if (shopPurchase && std::string(t.Var) == "upgrade_points") continue;
		// Flaming vessel capacity: only the shop's upgrades are taken back (the shop counts them in
		// bought_potions, so they stay sold); anything else is left alone.
		if (std::string(t.Var) == "hit_bar_max" && Room != "r_inside_tent") continue;
		// The Looter's Oil Vial: the purchase is the check and keeps its vial (reverting it made the
		// shop sell it again and again).
		if (std::string(t.Var) == "health_vials_max" && Room == "r_inside_tent")
		{
			AppendCheck("shop oilvial");
			Log("shop Oil Vial bought");
			continue;
		}
		SetNumber(t.Var, last->second);
		if (t.Current)
		{
			double c = 0;
			if (GetNumber(t.Current, c)) SetNumber(t.Current, c - delta < 0 ? 0 : c - delta);
		}
		AppendCheck(std::string("grant ") + t.Var + " " + Room + " " + Num(delta));
		Log(std::string("vanilla +") + Num(delta) + " " + t.Var + " in " + Room + " -> reverted");
	}
}

// Currency: every gain is scaled by the multiplier - the game's own gains here, AP currency items when applied.
// F10 (test helper) is not scaled and not logged.
// currency_log.txt: the game's own gains at 1x (before the multiplier), per room - used to estimate how much
// currency each area gives, for the shop logic. Line: "<seed slot>\t<room>\t<amount>".
static double g_LastCurrency = -1;
static void ScaleCurrency(const std::string& Room)
{
	double cur = 0;
	if (!GetNumber("currency", cur)) return;
	double pct = Opt("currency_multiplier", 100);
	if (g_LastCurrency >= 0 && cur > g_LastCurrency)
	{
		double delta = cur - g_LastCurrency;
		{
			std::ofstream f(g_Dir / "currency_log.txt", std::ios::app);
			f << CurrentSlot() << "\t" << Room << "\t" << Num(delta) << "\n";
		}
		if (pct != 100)
		{
			double extra = std::round(delta * (pct - 100) / 100.0);
			if (cur + extra < 0) extra = -cur;
			SetNumber("currency", cur + extra);
		}
	}
}
static void RememberCurrency() { GetNumber("currency", g_LastCurrency); }

// Test helper: F10 adds 10000 currency (not scaled, not logged).
static bool g_F10 = false;
static void DebugCurrencyHotkey()
{
	bool f10 = (GetAsyncKeyState(VK_F10) & 0x8000) != 0;
	if (f10 && !g_F10)
	{
		double v = 0;
		if (GetNumber("currency", v))
		{
			SetNumber("currency", v + 10000);
			if (g_LastCurrency >= 0) g_LastCurrency += 10000;
			Log("F10: +10000 currency");
		}
	}
	g_F10 = f10;
}

// Death Link: report deaths (health dropping to 0) and kill on request ("opt kill N", N counts up).
static double g_LastHealth = -1;
static double g_KillsSeen = -1;
static void DeathLink()
{
	double h = 0;
	if (GetNumber("player_health", h))
	{
		if (g_LastHealth > 0 && h <= 0) { AppendCheck("death"); Log("death"); }
		g_LastHealth = h;
	}
	double kills = Opt("kill", 0);
	if (g_KillsSeen < 0 || kills < g_KillsSeen) g_KillsSeen = kills; // mod start / client restarted
	if (kills > g_KillsSeen)
	{
		g_KillsSeen = kills;
		if (h > 0) { SetNumber("player_health", 0); g_LastHealth = 0; Log("death link: killed"); }
	}
}

static void ApplyConsumables()
{
	int applied = static_cast<int>(PvarNumber("ap_applied", 0));
	int total = static_cast<int>(g_Items.Ids.size());
	if (applied >= total) return;
	for (int i = applied; i < total; i++)
		ApplyConsumable(g_Items.Ids[i]);
	PvarSet("ap_applied", RValue(static_cast<double>(total)));
	Log("applied items " + std::to_string(applied) + ".." + std::to_string(total - 1));
}

static void ReportKeys(const std::string& Room)
{
	bool fdMasked = PvarExists("ap_fd_masked");
	for (const std::string& k : PersistentKeys())
	{
		if (k == FD_KEY && fdMasked) continue;
		// A lever opened by its received item: its own check waits until the player visits the lever's room.
		if (k.rfind("ap_", 0) != 0 && PvarExists("ap_lv_" + k))
		{
			const LeverItem* l = LeverByKey(k);
			if (l && Room != l->Room) continue;
			PvarDelete("ap_lv_" + k);
			Log("lever " + k + ": visited its room -> check");
		}
		if (!IsPvarFlag(k) && k.rfind("ap_", 0) != 0 && g_ReportedKeys.insert(k).second)
		{
			AppendCheck("key " + k);
			if (k.rfind("challengeAX_", 0) == 0)
			{
				std::string from = PvarString("ap_trial_" + k.substr(9, 5));   // "AX_nn"
				AppendCheck("trial " + (from.empty() ? std::string("?") : from) + " " + k.substr(9, 5));
			}
		}
	}
}

static const char* WATCH[] = {
	"area_name", "currency", "golden_feathers", "elevator_parts", "fish_gate", "spirits_found",
	"spirits_collected_reward", "bought_slots", "bought_potions", "upgrade_points", "upgrade_points_current",
	"upgrade_tokens", "health_vials_max", "health_vials", "collected_potions", "hit_bar_max", "fly_time", "percent", "boss_keys",
	"looter_parts", "family", "story_pages", "upgrade_list", "upgrade_list_binary", "upgrade_list_active", "difficulty", "savefilenum",
	"player_health", "player_max_health",
};

static void WriteState(const std::string& Room, bool InGame)
{
	std::ofstream f(g_Dir / "state.txt", std::ios::trunc);
	f << "mod " << MOD_VERSION << "\n";
	f << "time " << Timestamp() << "\n";
	f << "room " << Room << "\n";
	f << "ingame " << (InGame ? 1 : 0) << "\n";
	f << "slot " << g_Items.Slot << "\n";
	f << "received " << g_Items.Ids.size() << "\n";
	f << "save " << g_SaveStatus << "\n";
	f << "applied " << (InGame ? Num(PvarNumber("ap_applied", 0)) : std::string("-")) << "\n";
	for (const char* w : WATCH)
	{
		RValue* v = GlobalRef(w);
		f << "var " << w << " " << (v ? Describe(*v) : std::string("missing")) << "\n";
	}
}

// F5: dump the game's trinket/ability info scripts (to map trinket indexes to names).
static void DumpInfoScripts()
{
	std::ofstream f(g_Dir / "info_dump.txt", std::ios::trunc);
	for (const char* script : { "gml_Script_scr_upgrades_info", "gml_Script_scr_upgrade_info", "gml_Script_scr_ability_info" })
	{
		for (int i = 0; i < 40; i++)
		{
			RValue result;
			AurieStatus st = AURIE_SUCCESS;
			try { st = g_Yytk->CallGameScriptEx(result, script, Global(), Global(), { RValue(static_cast<double>(i)) }); }
			catch (...) { st = AURIE_EXTERNAL_ERROR; }
			f << script << "(" << i << ") status=" << AurieStatusToString(st) << " -> " << Describe(result) << "\n";
			if (AurieSuccess(st) && result.IsStruct())
			{
				g_Yytk->EnumInstanceMembers(result, [&f](IN const char* Name, RValue* V) -> bool
				{
					if (Name && V) f << "    ." << Name << " = " << Describe(*V) << "\n";
					return false;
				});
			}
		}
	}
	Log("wrote info_dump.txt");
}

// Ability tutorials (AZ_ rooms): the egg already counted as a check, and the ability may not be owned,
// so the player could get stuck. Move the player onto the room's exit (o_back_to_nest) right away.
static bool IsTutorialRoom(const std::string& Room)
{
	if (Room.rfind("AZ_", 0) != 0) return false;
	return Room != "AZ_98" && Room != "AZ_99" && Room.find("template") == std::string::npos;
}

static bool InstanceXY(const char* Object, RValue& Inst, double& X, double& Y, std::string& Why)
{
	RValue obj = g_Yytk->CallBuiltin("asset_get_index", { RValue(std::string_view(Object)) });
	// GameMaker 2024+ returns an asset reference here, not a plain number.
	if (obj.IsUndefined() || (obj.IsNumberConvertible() && obj.ToDouble() < 0 && !obj.IsString()))
	{
		Why = std::string(Object) + ": no such object (" + obj.GetKindName() + ")"; return false;
	}
	RValue count = g_Yytk->CallBuiltin("instance_number", { obj });
	if (!count.IsNumberConvertible() || count.ToDouble() < 1) { Why = std::string(Object) + ": no instance in room"; return false; }
	Inst = g_Yytk->CallBuiltin("instance_find", { obj, RValue(0.0) });
	RValue x = g_Yytk->CallBuiltin("variable_instance_get", { Inst, RValue(std::string_view("x")) });
	RValue y = g_Yytk->CallBuiltin("variable_instance_get", { Inst, RValue(std::string_view("y")) });
	if (!x.IsNumberConvertible() || !y.IsNumberConvertible())
	{
		Why = std::string(Object) + ": x/y unreadable (" + Inst.GetKindName() + ", " + x.GetKindName() + ")";
		return false;
	}
	X = x.ToDouble(); Y = y.ToDouble();
	return true;
}

// Egg rooms -> the flag the game sets when that ability's tutorial is finished (a location key).
struct EggRoom { const char* Room; const char* WakeKey; const char* AbilityVar; };
static const EggRoom EGG_ROOMS[] = {
	{ "AH_08", "wake_sling", "up_sling" }, { "AB_29", "wake_climb", "up_climb" }, { "AP_12", "wake_wind", "up_wind_ride" },
	{ "AC_33", "wake_hover", "up_hover" }, { "AU_27", "wake_wsling", "up_wall_sling" }, { "AQ_44", "wake_fly", "up_fly" },
};


static const EggRoom* EggRoomFor(const std::string& Room)
{
	for (const EggRoom& e : EGG_ROOMS) if (Room == e.Room) return &e;
	return nullptr;
}

static int DestroyAll(const char* Object)
{
	RValue obj = g_Yytk->CallBuiltin("asset_get_index", { RValue(std::string_view(Object)) });
	if (obj.IsUndefined()) return 0;
	int killed = 0;
	for (int guard = 0; guard < 16; guard++)
	{
		RValue count = g_Yytk->CallBuiltin("instance_number", { obj });
		if (!count.IsNumberConvertible() || count.ToDouble() < 1) break;
		RValue inst = g_Yytk->CallBuiltin("instance_find", { obj, RValue(0.0) });
		g_Yytk->CallBuiltin("instance_destroy", { inst });
		killed++;
	}
	return killed;
}

static int CountOf(const char* Object)
{
	RValue obj = g_Yytk->CallBuiltin("asset_get_index", { RValue(std::string_view(Object)) });
	if (obj.IsUndefined()) return 0;
	RValue count = g_Yytk->CallBuiltin("instance_number", { obj });
	return count.IsNumberConvertible() ? static_cast<int>(count.ToDouble()) : 0;
}

// Egg rooms. The game only removes an egg once its ability is owned, so an egg whose ability the
// multiworld has not sent yet would send the player into its tutorial again and again.
// - egg already taken (wake flag set): remove the egg so it can't be picked up again
// - egg missing while not taken (the game hid it because the ability is already owned): count it as taken
// Called on every object event (not rate limited) so the egg is gone before the player can touch it.
static std::string g_EggRoomSeen;
static ULONGLONG g_EggRoomSince = 0;
static void GuardEgg(const std::string& Room, ULONGLONG Now)
{
	const EggRoom* egg = EggRoomFor(Room);
	if (!egg) { g_EggRoomSeen.clear(); return; }
	if (Room != g_EggRoomSeen) { g_EggRoomSeen = Room; g_EggRoomSince = Now; }
	if (!g_LentVar.empty() && g_LentRoom == Room) return; // the game's own wake-up scene is running
	if (PvarExists(egg->WakeKey))
	{
		if (Now - g_EggRoomSince > 1500) return; // only right after entering, never mid-scene
		int k = DestroyAll("o_ability") + DestroyAll("o_abil_col");
		if (k) Log(std::string("egg in ") + Room + " already taken -> removed (" + std::to_string(k) + ")");
	}
	else if (Now - g_EggRoomSince > 3000 && CountOf("o_ability") == 0 && CountOf("oPlayer") > 0)
	{
		PvarAddFlag(egg->WakeKey);
		Log(std::string("egg in ") + Room + " not there (ability already owned?) -> counted as taken");
	}
}

static ULONGLONG g_TutorialSince = 0;
static int g_TutorialMoves = 0;
static std::string g_TutorialWhy;

// Called every tick while in a tutorial room. PrevRoom is where the player came from (the egg room).
static void SkipTutorial(const std::string& Room, const std::string& PrevRoom, bool JustEntered, ULONGLONG Now)
{
	if (JustEntered)
	{
		g_TutorialSince = Now; g_TutorialMoves = 0; g_TutorialWhy.clear();
		Log("tutorial " + Room + " entered from " + PrevRoom);
		// Entering the tutorial means the egg was taken: mark it like the game does at the end of the tutorial.
		for (const EggRoom& e : EGG_ROOMS)
			if (PrevRoom == e.Room && !PvarExists(e.WakeKey)) { PvarAddFlag(e.WakeKey); Log(std::string("egg taken: ") + e.WakeKey); }
	}
	if (Now - g_TutorialSince < 1500 || Opt("skip_tutorials", 1) < 1) return;
	RValue exitInst, player;
	double ex = 0, ey = 0, px = 0, py = 0;
	std::string why;
	if (!InstanceXY("o_back_to_nest", exitInst, ex, ey, why) || !InstanceXY("oPlayer", player, px, py, why))
	{
		if (why != g_TutorialWhy) { Log("tutorial " + Room + ": cannot skip yet: " + why); g_TutorialWhy = why; }
		return;
	}
	if (g_TutorialMoves == 0)
	{
		Log("tutorial " + Room + ": moving player from " + Num(px) + "," + Num(py) + " to the exit at " + Num(ex) + "," + Num(ey));
		if (const EggRoom* egg = EggRoomFor(PrevRoom))
		{
			double cur = 0;
			if (GetNumber(egg->AbilityVar, cur) && cur < 1)
			{
				g_LentVar = egg->AbilityVar; g_LentRoom = egg->Room; g_LentUntil = 0;
				SetNumber(egg->AbilityVar, 1.0);
				Log(std::string("lending ") + egg->AbilityVar + " for the wake-up scene");
			}
		}
	}
	if (g_TutorialMoves++ % 8 == 0 || std::abs(px - ex) > 64 || std::abs(py - ey) > 64)
	{
		g_Yytk->CallBuiltin("variable_instance_set", { player, RValue(std::string_view("x")), RValue(ex) });
		g_Yytk->CallBuiltin("variable_instance_set", { player, RValue(std::string_view("y")), RValue(ey - 16) });
	}
	if (g_TutorialMoves == 40) Log("tutorial " + Room + ": still here after 10 s, the exit did not trigger");
}

// Test helper: <game>\archipelago\set_flags.txt, one flag per line ("-flag" removes it).
// Applied to the loaded Archipelago save whenever the file changes.
static fs::file_time_type g_FlagsStamp{};
static void ApplyFlagsFile()
{
	std::error_code ec;
	fs::path p = g_Dir / "set_flags.txt";
	auto stamp = fs::last_write_time(p, ec);
	if (ec || stamp == g_FlagsStamp) return;
	g_FlagsStamp = stamp;
	std::ifstream f(p);
	std::string line;
	while (std::getline(f, line))
	{
		while (!line.empty() && (line.back() == '\r' || line.back() == ' ')) line.pop_back();
		if (line.empty() || line[0] == '#') continue;
		if (line[0] == '-') { PvarDelete(line.substr(1)); Log("set_flags: removed " + line.substr(1)); }
		else { PvarAddFlag(line); Log("set_flags: added " + line + " = " + PvarString(line)); }
	}
}

static void Tick()
{
	ULONGLONG now = GetTickCount64();

	bool f5 = (GetAsyncKeyState(VK_F5) & 0x8000) != 0;
	if (f5 && !g_F5) DumpInfoScripts();
	g_F5 = f5;

	if (now - g_LastTick < 250) return;
	g_LastTick = now;

	ReadItemsFile();
	std::string room = CurrentRoomName();
	bool ingame = InGameplayRoom(room);
	bool roomChanged = room != g_LastRoom;
	static std::string prevRoom;
	if (roomChanged)
	{
		Log("room " + g_LastRoom + " -> " + room);
		prevRoom = g_LastRoom;
		g_LastRoom = room;
	}
	if (IsTutorialRoom(room) && ingame && SaveIsOurs())
		SkipTutorial(room, prevRoom, roomChanged, now);
	if (ingame && SaveIsOurs())
		GuardEgg(room, now);
	bool justEntered = ingame && !g_WasInGame;
	if (justEntered)
	{
		Log("entered gameplay (save loaded)");
		g_InGameSince = now;
		g_ReportedKeys.clear(); // report everything once per load; the client ignores duplicates
		g_OldMarksCleaned = false;
		g_LockLogDone = false;
	}
	g_WasInGame = ingame;
	if (!ingame) g_SaveStatus = "no save loaded";

	if (ingame && SaveIsOurs())
	{
		if (roomChanged && room.rfind("AX_", 0) == 0 && room.size() >= 5 && prevRoom.rfind("AX_", 0) != 0)
		{
			PvarSet("ap_trial_" + room.substr(0, 5), RValue(std::string_view(prevRoom)));
			Log("time trial " + room + " entered from " + prevRoom);
		}
		ReportKeys(room);
		RestoreAfterRestart(room, now);
		if (justEntered && PvarNumber("ap_forge_count", 0) > 0)
			AppendCheck("forge " + Num(PvarNumber("ap_forge_count", 0)));
		if (justEntered || g_Last.empty()) RememberTracked();
		else RevertVanillaResources(room);
		if (justEntered || g_LastCurrency < 0) RememberCurrency(); else ScaleCurrency(room);
		DeathLink();
		EnforceItems(room);
		UnlockShops();
		ManageWillowFlag(room);
		RevealMap();
		ManageTents(room, prevRoom);
		ManageLevers(room, now);
		if (justEntered || roomChanged) ClearGateLocks();
		SyncMarks(now);
		SkipIntro(room);
		if (justEntered) g_FlagsStamp = {};
		ApplyFlagsFile();
		ApplyConsumables();
		RememberTracked();
		RememberCurrency();
	}
	else
	{
		g_Last.clear();
		g_LastCurrency = -1;
		g_LastHealth = -1;
	}
	ReadHudFile();
	g_HudOn = ingame && SaveIsOurs();
	if (now - g_LastState >= 1000)
	{
		g_LastState = now;
		WriteState(room, ingame);
	}
}

static bool g_InCallback = false;
static std::string g_ShotPending;
static void TakePendingShot()
{
	if (g_ShotPending.empty()) return;
	g_Yytk->CallBuiltin("screen_save", { RValue(std::string_view(g_ShotPending)) });
	Log("F7: screenshot " + g_ShotPending);
	g_ShotPending.clear();
}

// F3 inside a tent: put the player back at the tent's exit (the shop ledges need Climb or Slingshot).
static bool g_F3 = false;
static void TentExitHotkey(const std::string& Room)
{
	bool f3 = (GetAsyncKeyState(VK_F3) & 0x8000) != 0;
	bool pressed = f3 && !g_F3;
	g_F3 = f3;
	if (!pressed || Room != "r_inside_tent") return;
	RValue exitInst, player;
	double ex = 0, ey = 0, px = 0, py = 0;
	std::string why;
	if (!InstanceXY("o_tent_exit", exitInst, ex, ey, why) || !InstanceXY("oPlayer", player, px, py, why))
	{
		Log("F3: cannot find the tent exit: " + why);
		return;
	}
	g_Yytk->CallBuiltin("variable_instance_set", { player, RValue(std::string_view("x")), RValue(ex) });
	g_Yytk->CallBuiltin("variable_instance_set", { player, RValue(std::string_view("y")), RValue(ey - 16) });
	Log("F3: moved player to the tent exit at " + Num(ex) + "," + Num(ey));
}

// F7: dump the variables of the shop / trinket menu objects (to find what marks a menu as open).
static bool g_F7 = false;
static int g_F7Count = 0;
static void DumpMenusHotkey()
{
	bool f7 = (GetAsyncKeyState(VK_F7) & 0x8000) != 0;
	bool pressed = f7 && !g_F7;
	g_F7 = f7;
	if (!pressed) return;
	g_F7Count++;
	std::ofstream f(g_Dir / ("f7_dump_" + std::to_string(g_F7Count) + ".txt"), std::ios::trunc);
	f << "room " << g_LastRoom << "\n";
	for (const char* name : { "o_looter_popupshop", "o_looter_shop1", "o_looter_shop", "o_upgrade_trinkets", "o_ui_trinket",
		"o_trinket_ug_glow", "o_inside_tent_control", "o_Equip", "o_Map_Draw", "o_menu_control", "o_looternpc" })
	{
		RValue obj = g_Yytk->CallBuiltin("asset_get_index", { RValue(std::string_view(name)) });
		RValue count = g_Yytk->CallBuiltin("instance_number", { obj });
		int c = count.IsNumberConvertible() ? static_cast<int>(count.ToDouble()) : 0;
		f << "== " << name << " x" << c << "\n";
		for (int k = 0; k < c && k < 4; k++)
		{
			RValue inst = g_Yytk->CallBuiltin("instance_find", { obj, RValue(static_cast<double>(k)) });
			f << " [" << k << "]\n";
			RValue names = g_Yytk->CallBuiltin("variable_instance_get_names", { inst });
			size_t nn = 0;
			if (names.IsArray() && AurieSuccess(g_Yytk->GetArraySize(names, nn)))
				for (size_t j = 0; j < nn; j++)
				{
					RValue* nm = nullptr;
					if (!AurieSuccess(g_Yytk->GetArrayEntry(names, j, nm)) || !nm) continue;
					RValue v = g_Yytk->CallBuiltin("variable_instance_get", { inst, *nm });
					f << "    " << nm->ToString() << " = " << Describe(v) << "\n";
				}
			for (const char* bi : { "x", "y", "visible", "depth", "image_alpha", "sprite_index" })
			{
				RValue v = g_Yytk->CallBuiltin("variable_instance_get", { inst, RValue(std::string_view(bi)) });
				f << "    (" << bi << ") = " << Describe(v) << "\n";
			}
		}
	}
	for (const char* g : { "paused", "pause", "pause_menu", "popup", "popup2", "in_menu", "open_shop", "openshop", "v_new_shop" })
	{
		RValue* v = GlobalRef(g);
		f << "global " << g << " = " << (v ? Describe(*v) : std::string("missing")) << "\n";
	}
	// global variables that look map / menu / shop related
	RValue gnames = g_Yytk->CallBuiltin("variable_instance_get_names", { RValue(-5.0) });
	size_t gn = 0;
	if (gnames.IsArray() && AurieSuccess(g_Yytk->GetArraySize(gnames, gn)))
		for (size_t j = 0; j < gn; j++)
		{
			RValue* nm = nullptr;
			if (!AurieSuccess(g_Yytk->GetArrayEntry(gnames, j, nm)) || !nm) continue;
			std::string name = nm->ToString();
			std::string low = name;
			for (char& ch : low) ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
			if (low.find("map") == std::string::npos && low.find("zoom") == std::string::npos && low.find("menu") == std::string::npos &&
				low.find("shop") == std::string::npos && low.find("pause") == std::string::npos && low.find("cam") == std::string::npos &&
				low.find("gui") == std::string::npos && low.find("trinket") == std::string::npos && low.find("equip") == std::string::npos)
				continue;
			RValue* v = GlobalRef(name.c_str());
			f << "global* " << name << " = " << (v ? Describe(*v) : std::string("?")) << "\n";
		}
	f << "gui " << Describe(g_Yytk->CallBuiltin("display_get_gui_width", {})) << " x " << Describe(g_Yytk->CallBuiltin("display_get_gui_height", {})) << "\n";
	RValue cam = g_Yytk->CallBuiltin("view_get_camera", { RValue(0.0) });
	f << "camera0 x " << Describe(g_Yytk->CallBuiltin("camera_get_view_x", { cam })) << " y " << Describe(g_Yytk->CallBuiltin("camera_get_view_y", { cam }))
	  << " w " << Describe(g_Yytk->CallBuiltin("camera_get_view_width", { cam })) << " h " << Describe(g_Yytk->CallBuiltin("camera_get_view_height", { cam })) << "\n";
	// map draw lists (what the map draws, maybe with screen positions)
	{
		RValue mobj = g_Yytk->CallBuiltin("asset_get_index", { RValue(std::string_view("o_Map_Draw")) });
		RValue minst = g_Yytk->CallBuiltin("instance_find", { mobj, RValue(0.0) });
		for (const char* lname : { "draw_list", "draw_list_animated" })
		{
			if (minst.IsUndefined() || (minst.IsNumberConvertible() && minst.ToDouble() < 0)) break;
			RValue list = g_Yytk->CallBuiltin("variable_instance_get", { minst, RValue(std::string_view(lname)) });
			if (!g_Yytk->CallBuiltin("ds_exists", { list, RValue(2.0) }).ToBoolean()) { f << lname << " not a list\n"; continue; }
			int size = static_cast<int>(Builtin("ds_list_size", { list }));
			f << lname << " size " << size << "\n";
			for (int k = 0; k < size && k < 12; k++)
			{
				RValue v = g_Yytk->CallBuiltin("ds_list_find_value", { list, RValue(static_cast<double>(k)) });
				f << "  [" << k << "] " << Describe(v) << "\n";
				if (v.IsStruct())
				{
					RValue names = g_Yytk->CallBuiltin("variable_struct_get_names", { v });
					size_t nn = 0;
					if (names.IsArray() && AurieSuccess(g_Yytk->GetArraySize(names, nn)))
						for (size_t j = 0; j < nn; j++)
						{
							RValue* nm = nullptr;
							if (!AurieSuccess(g_Yytk->GetArrayEntry(names, j, nm)) || !nm) continue;
							f << "      " << nm->ToString() << " = " << Describe(g_Yytk->CallBuiltin("variable_struct_get", { v, *nm })) << "\n";
						}
				}
			}
		}
	}
	g_ShotPending = (g_Dir / ("f7_shot_" + std::to_string(g_F7Count) + ".png")).string();   // saved in the next draw event
	Log("F7: wrote f7_dump_" + std::to_string(g_F7Count) + ".txt");
}

static void ObjectCallback(FWCodeEvent& Context)
{
	// HUD: drawn right after the game controller's Draw GUI End event.
	CCode* code = std::get<2>(Context.Arguments());
	if (code && !g_InCallback)
	{
		const char* name = code->GetName();
		if (name && std::strcmp(name, "gml_Object_o_Game_Control_Draw_75") == 0)
		{
			Context.Call();
			g_InCallback = true;
			try { DrawHud(); DrawToast(); TakePendingShot(); } catch (...) {}
			g_InCallback = false;
			return;
		}
		if (name && std::strcmp(name, "gml_Object_o_Map_Draw_Draw_64") == 0)
		{
			Context.Call();
			g_InCallback = true;
			try { DrawMapTracker(); DrawToast(); TakePendingShot(); } catch (...) {}
			g_InCallback = false;
			return;
		}
	}
	if (g_InCallback) return;
	g_InCallback = true;
	try
	{
		if (g_WasInGame) { TentExitHotkey(g_LastRoom); DebugCurrencyHotkey(); DumpMenusHotkey(); MapFilterHotkey(); }
		if (g_WasInGame && (g_LastRoom == "r_inside_tent" || g_ShopWindow)) ManageShopWindow(g_LastRoom);
		// cheap per-event work: egg rooms need the egg removed before the player touches it
		if (!g_LastRoom.empty() && EggRoomFor(g_LastRoom) && g_WasInGame)
		{
			std::string room = CurrentRoomName();
			if (EggRoomFor(room) && SaveIsOurs()) GuardEgg(room, GetTickCount64());
		}
		Tick();
	}
	catch (...) {}
	g_InCallback = false;
}

EXPORTED AurieStatus ModuleInitialize(IN AurieModule* Module, IN const fs::path& ModulePath)
{
	(void)ModulePath;
	g_Yytk = GetInterface();
	if (!g_Yytk)
	{
		DbgPrintEx(LOG_SEVERITY_ERROR, "[WD-AP] YYToolkit interface not found");
		return AURIE_MODULE_DEPENDENCY_NOT_RESOLVED;
	}
	wchar_t exe[MAX_PATH] = {};
	GetModuleFileNameW(nullptr, exe, MAX_PATH);
	g_Dir = fs::path(exe).parent_path() / "archipelago";
	std::error_code ec;
	fs::create_directories(g_Dir, ec);
	g_Log.open(g_Dir / "mod.log", std::ios::out | std::ios::trunc);
	Log(std::string("Well Dweller Archipelago mod ") + MOD_VERSION + " loaded");
	AurieStatus st = g_Yytk->CreateCallback(Module, EVENT_OBJECT_CALL, reinterpret_cast<PVOID>(ObjectCallback), 0);
	Log(std::string("object callback: ") + AurieStatusToString(st));
	return AURIE_SUCCESS;
}

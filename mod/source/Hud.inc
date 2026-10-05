// In-game HUD (bottom left: last item messages + checks counter) and map tracker markers.
// Both are fed by the client: hud.txt and marks.txt in <game>\archipelago\.
//
// hud.txt   "checks\t<found>\t<total>"
//           "msg\t<sprite|ap>\t<frame>\t<RRGGBB>\t<text>[\t<RRGGBB>\t<text>...]"   (oldest first, up to 5)
// marks.txt "mode\t0"   (starting filter: off)
//           "m\t<map x>\t<map y>\t<sprite>\t<frame>\t<state>"   state 0 all checked, 1 in logic, 2 out of logic
// F6 with the map open cycles the filter (saved per save as ap_map_filter).

struct HudSeg { double Color; std::string Text; };
struct HudMsg { std::string Sprite; int Frame = 0; std::vector<HudSeg> Segs; };
static struct
{
	int Found = -1, Total = 0;
	std::vector<HudMsg> Msgs;
	fs::file_time_type Stamp{};
} g_Hud;
static bool g_HudOn = false;           // set by Tick: in gameplay with our save loaded
static ULONGLONG g_ToastUntil = 0;     // short message (map filter changes)
static std::string g_Toast;
static std::map<std::string, RValue> g_SpriteCache;
static RValue g_ApLogo;
static bool g_ApLogoTried = false;

static std::vector<std::string> SplitTabs(const std::string& Line)
{
	std::vector<std::string> out;
	size_t start = 0;
	while (true)
	{
		size_t t = Line.find('\t', start);
		out.push_back(Line.substr(start, t == std::string::npos ? std::string::npos : t - start));
		if (t == std::string::npos) break;
		start = t + 1;
	}
	return out;
}

static double HexColor(const std::string& Hex)
{
	unsigned v = 0xFFFFFF;
	try { v = static_cast<unsigned>(std::stoul(Hex, nullptr, 16)); } catch (...) {}
	unsigned r = (v >> 16) & 255, g = (v >> 8) & 255, b = v & 255;
	return static_cast<double>(r | (g << 8) | (b << 16));   // GameMaker colours are BGR
}

static void ReadHudFile()
{
	fs::path p = g_Dir / "hud.txt";
	std::error_code ec;
	auto stamp = fs::last_write_time(p, ec);
	if (ec || stamp == g_Hud.Stamp) return;
	g_Hud.Stamp = stamp;
	std::ifstream f(p);
	if (!f) return;
	g_Hud.Msgs.clear();
	std::string line;
	while (std::getline(f, line))
	{
		if (!line.empty() && line.back() == '\r') line.pop_back();
		auto parts = SplitTabs(line);
		if (parts[0] == "checks" && parts.size() >= 3)
		{
			g_Hud.Found = std::atoi(parts[1].c_str());
			g_Hud.Total = std::atoi(parts[2].c_str());
		}
		else if (parts[0] == "msg" && parts.size() >= 5)
		{
			HudMsg m;
			m.Sprite = parts[1];
			m.Frame = std::atoi(parts[2].c_str());
			for (size_t i = 3; i + 1 < parts.size(); i += 2) m.Segs.push_back({ HexColor(parts[i]), parts[i + 1] });
			g_Hud.Msgs.push_back(m);
		}
	}
}

static RValue HudSprite(const std::string& Name)
{
	if (Name == "ap")
	{
		if (!g_ApLogoTried)
		{
			g_ApLogoTried = true;
			fs::path logo = g_Dir / "ap_logo.png";
			std::error_code ec;
			if (fs::exists(logo, ec))
				g_ApLogo = g_Yytk->CallBuiltin("sprite_add", { RValue(std::string_view(logo.string())), RValue(1.0),
					RValue(false), RValue(false), RValue(0.0), RValue(0.0) });
		}
		if (!g_ApLogo.IsUndefined()) return g_ApLogo;
		return HudSprite("s_item_marker");
	}
	auto it = g_SpriteCache.find(Name);
	if (it != g_SpriteCache.end()) return it->second;
	RValue s = g_Yytk->CallBuiltin("asset_get_index", { RValue(std::string_view(Name)) });
	g_SpriteCache[Name] = s;
	return s;
}

static double Builtin(const char* Name, std::vector<RValue> Args = {})
{
	RValue v = g_Yytk->CallBuiltin(Name, Args);
	return v.IsNumberConvertible() ? v.ToDouble() : 0;
}

// Draws one icon fitted into a Size x Size box with its top-left corner at X,Y.
static void DrawIcon(const HudMsg& M, double X, double Y, double Size)
{
	RValue spr = HudSprite(M.Sprite);
	if (spr.IsUndefined()) return;
	double w = Builtin("sprite_get_width", { spr }), h = Builtin("sprite_get_height", { spr });
	if (w <= 0 || h <= 0) return;
	double ox = Builtin("sprite_get_xoffset", { spr }), oy = Builtin("sprite_get_yoffset", { spr });
	double sc = Size / (w > h ? w : h);
	double bx = X + (Size - w * sc) / 2, by = Y + (Size - h * sc) / 2;
	g_Yytk->CallBuiltin("draw_sprite_ext", { spr, RValue(static_cast<double>(M.Frame)), RValue(bx + ox * sc), RValue(by + oy * sc),
		RValue(sc), RValue(sc), RValue(0.0), RValue(16777215.0), RValue(1.0) });
}

// Short centred message near the top of the screen (map filter changes).
static void DrawToast()
{
	if (g_Toast.empty() || GetTickCount64() > g_ToastUntil) return;
	double gw = Builtin("display_get_gui_width"), gh = Builtin("display_get_gui_height");
	if (gw <= 0 || gh <= 0) return;
	RValue oldFont = g_Yytk->CallBuiltin("draw_get_font", {});
	double oldH = Builtin("draw_get_halign"), oldV = Builtin("draw_get_valign");
	double oldColor = Builtin("draw_get_colour"), oldAlpha = Builtin("draw_get_alpha");
	RValue font = HudSprite("fnt_default");
	if (!font.IsUndefined()) g_Yytk->CallBuiltin("draw_set_font", { font });
	g_Yytk->CallBuiltin("draw_set_halign", { RValue(1.0) });
	g_Yytk->CallBuiltin("draw_set_valign", { RValue(0.0) });
	double ui = gh / 1080.0, scale = 0.7 * ui;
	RValue text{ std::string_view(g_Toast) };
	double w = Builtin("string_width", { text }) * scale, h = Builtin("string_height", { text }) * scale;
	double cx = gw / 2, y = 120 * ui, pad = 10 * ui;
	g_Yytk->CallBuiltin("draw_set_alpha", { RValue(0.6) });
	g_Yytk->CallBuiltin("draw_set_colour", { RValue(0.0) });
	g_Yytk->CallBuiltin("draw_rectangle", { RValue(cx - w / 2 - pad), RValue(y - pad), RValue(cx + w / 2 + pad), RValue(y + h + pad), RValue(false) });
	g_Yytk->CallBuiltin("draw_set_alpha", { RValue(1.0) });
	RValue c(HexColor("F2D16B"));
	g_Yytk->CallBuiltin("draw_text_transformed_colour", { RValue(cx), RValue(y), text, RValue(scale), RValue(scale), RValue(0.0), c, c, c, c, RValue(1.0) });
	if (!oldFont.IsUndefined()) g_Yytk->CallBuiltin("draw_set_font", { oldFont });
	g_Yytk->CallBuiltin("draw_set_halign", { RValue(oldH) });
	g_Yytk->CallBuiltin("draw_set_valign", { RValue(oldV) });
	g_Yytk->CallBuiltin("draw_set_colour", { RValue(oldColor) });
	g_Yytk->CallBuiltin("draw_set_alpha", { RValue(oldAlpha) });
}

// Called right after o_Game_Control's Draw GUI End event.
static void DrawHud()
{
	if (!g_HudOn || g_Hud.Found < 0) return;
	double gw = Builtin("display_get_gui_width"), gh = Builtin("display_get_gui_height");
	if (gw <= 0 || gh <= 0) return;
	RValue oldFont = g_Yytk->CallBuiltin("draw_get_font", {});
	double oldColor = Builtin("draw_get_colour"), oldAlpha = Builtin("draw_get_alpha");
	double oldH = Builtin("draw_get_halign"), oldV = Builtin("draw_get_valign");

	RValue font = HudSprite("fnt_default");
	if (!font.IsUndefined()) g_Yytk->CallBuiltin("draw_set_font", { font });
	g_Yytk->CallBuiltin("draw_set_halign", { RValue(0.0) });
	g_Yytk->CallBuiltin("draw_set_valign", { RValue(0.0) });

	double ui = gh / 1080.0;
	double scale = 0.62 * ui;
	double lineH = Builtin("string_height", { RValue(std::string_view("Ag")) }) * scale * 1.1;
	if (lineH <= 0) lineH = 24 * ui;
	double icon = lineH, gap = 8 * ui, pad = 10 * ui, margin = 18 * ui;

	std::string counter = "Checks: " + std::to_string(g_Hud.Found) + " / " + std::to_string(g_Hud.Total);
	double width = Builtin("string_width", { RValue(std::string_view(counter)) }) * scale;
	for (const HudMsg& m : g_Hud.Msgs)
	{
		double w = icon + gap;
		for (const HudSeg& s : m.Segs) w += Builtin("string_width", { RValue(std::string_view(s.Text)) }) * scale;
		if (w > width) width = w;
	}
	double lines = static_cast<double>(g_Hud.Msgs.size() + 1);
	double x0 = margin, y1 = gh - margin;
	double y0 = y1 - lines * lineH - 2 * pad;
	double x1 = x0 + width + 2 * pad;

	g_Yytk->CallBuiltin("draw_set_alpha", { RValue(0.5) });
	g_Yytk->CallBuiltin("draw_set_colour", { RValue(0.0) });
	g_Yytk->CallBuiltin("draw_rectangle", { RValue(x0), RValue(y0), RValue(x1), RValue(y1), RValue(false) });
	g_Yytk->CallBuiltin("draw_set_alpha", { RValue(1.0) });

	double y = y0 + pad;
	for (const HudMsg& m : g_Hud.Msgs)
	{
		double x = x0 + pad;
		DrawIcon(m, x, y, icon);
		x += icon + gap;
		for (const HudSeg& s : m.Segs)
		{
			RValue text(std::string_view(s.Text));
			RValue c(s.Color);
			g_Yytk->CallBuiltin("draw_text_transformed_colour", { RValue(x), RValue(y), text, RValue(scale), RValue(scale), RValue(0.0),
				c, c, c, c, RValue(1.0) });
			x += Builtin("string_width", { text }) * scale;
		}
		y += lineH;
	}
	RValue gold(HexColor("F2D16B"));
	g_Yytk->CallBuiltin("draw_text_transformed_colour", { RValue(x0 + pad), RValue(y), RValue(std::string_view(counter)),
		RValue(scale), RValue(scale), RValue(0.0), gold, gold, gold, gold, RValue(1.0) });

	if (!oldFont.IsUndefined()) g_Yytk->CallBuiltin("draw_set_font", { oldFont });
	g_Yytk->CallBuiltin("draw_set_colour", { RValue(oldColor) });
	g_Yytk->CallBuiltin("draw_set_alpha", { RValue(oldAlpha) });
	g_Yytk->CallBuiltin("draw_set_halign", { RValue(oldH) });
	g_Yytk->CallBuiltin("draw_set_valign", { RValue(oldV) });
}

// ---------------------------------------------------------------- map tracker
// The mod draws the tracker markers itself, on top of the game's map (after o_Map_Draw's Draw GUI event).
// Map cell (cx, cy) -> GUI position, measured from screenshots (2560x1440 GUI):
//   x = xpos_start + xpos + 150.5 - 50 * zoom + 24 * zoom * cx
//   y = ypos_start + ypos + 173.7 - 57.3 * zoom + 16 * zoom * cy
// Old builds put markers into global.map_marks ("_ap" field); those are removed once per load.

struct MapPoint { double X = 0, Y = 0; std::string Sprite; int Frame = 0; int State = 1; std::string Names; };
static fs::file_time_type g_MarksStamp{};
static std::vector<MapPoint> g_Points;
static int g_MarksMode = 0;   // the tracker starts off; F6 switches it
static ULONGLONG g_LastMarkSync = 0;
static bool g_MarksDirty = true;
static bool g_OldMarksCleaned = false;

static int MapFilter()
{
	double f = PvarNumber("ap_map_filter", -1);
	return f < 0 ? g_MarksMode : static_cast<int>(f);
}

static bool MarkShown(int State, int Filter)
{
	if (Filter >= 3) return true;
	if (Filter == 2) return State != 0;
	if (Filter == 1) return State == 1;
	return false;
}

// F6 while the map is open: all items -> all uncollected -> in logic only -> off -> all items ...
static bool g_F6 = false;
static void MapFilterHotkey()
{
	bool f6 = (GetAsyncKeyState(VK_F6) & 0x8000) != 0;
	bool pressed = f6 && !g_F6;
	g_F6 = f6;
	if (!pressed || !g_HudOn) return;
	int next = MapFilter() - 1;
	if (next < 0) next = 3;
	PvarSet("ap_map_filter", RValue(static_cast<double>(next)));
	static const char* NAMES[] = { "off", "in logic only", "all uncollected", "all items" };
	g_Toast = std::string("Map tracker: ") + NAMES[next] + "  (F6)";
	g_ToastUntil = GetTickCount64() + 3000;
	Log(g_Toast);
}

static void ReadMarksFile()
{
	fs::path p = g_Dir / "marks.txt";
	std::error_code ec;
	auto stamp = fs::last_write_time(p, ec);
	if (ec || stamp == g_MarksStamp) return;
	g_MarksStamp = stamp;
	std::ifstream f(p);
	if (!f) return;
	g_Points.clear();
	std::string line;
	while (std::getline(f, line))
	{
		if (!line.empty() && line.back() == '\r') line.pop_back();
		auto parts = SplitTabs(line);
		if (parts[0] == "mode" && parts.size() >= 2) g_MarksMode = std::atoi(parts[1].c_str());
		else if (parts[0] == "m" && parts.size() >= 5)
		{
			MapPoint m;
			m.X = std::atof(parts[1].c_str());
			m.Y = std::atof(parts[2].c_str());
			m.Sprite = parts[3];
			m.Frame = std::atoi(parts[4].c_str());
			m.State = parts.size() >= 6 ? std::atoi(parts[5].c_str()) : 1;
			if (parts.size() >= 7) m.Names = parts[6];
			g_Points.push_back(m);
		}
	}
}

// Called from Tick: read marks.txt; once per load remove markers that older builds put into global.map_marks.
static void SyncMarks(ULONGLONG Now)
{
	ReadMarksFile();
	if (g_OldMarksCleaned) return;
	RValue marks = GlobalValue("map_marks");
	if (marks.IsUndefined() || !g_Yytk->CallBuiltin("ds_exists", { marks, RValue(1.0) }).ToBoolean()) return;
	g_OldMarksCleaned = true;
	int removed = 0;
	RValue keys = g_Yytk->CallBuiltin("ds_map_keys_to_array", { marks });
	size_t n = 0;
	if (keys.IsArray() && AurieSuccess(g_Yytk->GetArraySize(keys, n)))
		for (size_t i = 0; i < n; i++)
		{
			RValue* k = nullptr;
			if (!AurieSuccess(g_Yytk->GetArrayEntry(keys, i, k)) || !k || !k->IsString()) continue;
			RValue mark = g_Yytk->CallBuiltin("ds_map_find_value", { marks, *k });
			if (!mark.IsStruct()) continue;
			RValue ap = g_Yytk->CallBuiltin("variable_struct_get", { mark, RValue(std::string_view("_ap")) });
			if (!ap.IsString()) continue;
			g_Yytk->CallBuiltin("ds_map_delete", { marks, *k });
			removed++;
		}
	if (removed)
	{
		RValue result;
		g_Yytk->CallGameScriptEx(result, "gml_Script_refresh_map", Global(), Global(), {});
		Log("map tracker: removed " + std::to_string(removed) + " old map markers");
	}
}

struct SpriteInfo { RValue Spr; double W = 0, H = 0, Ox = 0, Oy = 0; bool Ok = false; };
static std::map<std::string, SpriteInfo> g_SpriteInfo;
static const SpriteInfo& SpriteInfoFor(const std::string& Name)
{
	auto it = g_SpriteInfo.find(Name);
	if (it != g_SpriteInfo.end()) return it->second;
	SpriteInfo si;
	si.Spr = HudSprite(Name);
	if (!si.Spr.IsUndefined() && !(si.Spr.IsNumberConvertible() && si.Spr.ToDouble() < 0))
	{
		si.W = Builtin("sprite_get_width", { si.Spr }); si.H = Builtin("sprite_get_height", { si.Spr });
		si.Ox = Builtin("sprite_get_xoffset", { si.Spr }); si.Oy = Builtin("sprite_get_yoffset", { si.Spr });
		si.Ok = si.W > 0 && si.H > 0;
	}
	return g_SpriteInfo[Name] = si;
}

static double InstNum(const RValue& Inst, const char* Name, double Default = 0)
{
	RValue v = g_Yytk->CallBuiltin("variable_instance_get", { Inst, RValue(std::string_view(Name)) });
	return v.IsNumberConvertible() ? v.ToDouble() : Default;
}

// Draws the markers over the open map, plus the name of the marker under the map cursor.
static void DrawMapTracker()
{
	if (!g_HudOn || g_Points.empty()) return;
	int filter = MapFilter();
	if (filter <= 0) return;
	static RValue obj;
	if (obj.IsUndefined()) obj = g_Yytk->CallBuiltin("asset_get_index", { RValue(std::string_view("o_Map_Draw")) });
	RValue inst = g_Yytk->CallBuiltin("instance_find", { obj, RValue(0.0) });
	if (inst.IsUndefined() || (inst.IsNumberConvertible() && inst.ToDouble() < 0)) return;
	double alphaMap = InstNum(inst, "map_alpha", 1) * InstNum(inst, "alpha_var", 1);
	if (alphaMap <= 0.05) return;
	double z = InstNum(inst, "zoom", 1);
	double gw = Builtin("display_get_gui_width"), gh = Builtin("display_get_gui_height");
	if (gw <= 0 || gh <= 0 || z <= 0) return;
	double k = gw / 2560.0;   // the measurements were made with a 2560 wide GUI
	double baseX = InstNum(inst, "xpos_start") + InstNum(inst, "xpos") + (150.5 - 50 * z) * k;
	double baseY = InstNum(inst, "ypos_start") + InstNum(inst, "ypos") + (173.7 - 57.3 * z) * k;
	double cellW = 24 * z * k, cellH = 16 * z * k;
	double size = 13 * z * k;
	if (size < 22 * k) size = 22 * k;
	if (size > 80 * k) size = 80 * k;
	double top = gh * 0.075, bottom = gh * 0.93;
	double cx = gw / 2, cy = gh / 2;   // the map cursor sits in the middle of the screen
	double oldAlpha = Builtin("draw_get_alpha");
	const MapPoint* hover = nullptr;
	double hoverD = size * 0.6;
	for (const MapPoint& m : g_Points)
	{
		if (!MarkShown(m.State, filter)) continue;
		double x = baseX + cellW * m.X, y = baseY + cellH * m.Y;
		if (x < -size || x > gw + size || y < top || y > bottom) continue;
		const SpriteInfo& si = SpriteInfoFor(m.Sprite);
		if (!si.Ok) continue;
		double sc = size / (si.W > si.H ? si.W : si.H);
		double alpha = m.State == 1 ? 1.0 : (m.State == 2 ? 0.45 : 0.3);
		double col = m.State == 1 ? 16777215.0 : 8421504.0;   // white / grey tint
		g_Yytk->CallBuiltin("draw_sprite_ext", { si.Spr, RValue(static_cast<double>(m.Frame)),
			RValue(x - si.W * sc / 2 + si.Ox * sc), RValue(y - si.H * sc / 2 + si.Oy * sc),
			RValue(sc), RValue(sc), RValue(0.0), RValue(col), RValue(alpha * alphaMap) });
		double d = std::hypot(x - cx, y - cy);
		if (d < hoverD) { hoverD = d; hover = &m; }
	}
	g_Yytk->CallBuiltin("draw_set_alpha", { RValue(oldAlpha) });
	if (!hover || hover->Names.empty()) return;
	// label under the cursor
	RValue oldFont = g_Yytk->CallBuiltin("draw_get_font", {});
	double oldH = Builtin("draw_get_halign"), oldV = Builtin("draw_get_valign"), oldColor = Builtin("draw_get_colour");
	RValue font = HudSprite("fnt_default");
	if (!font.IsUndefined()) g_Yytk->CallBuiltin("draw_set_font", { font });
	g_Yytk->CallBuiltin("draw_set_halign", { RValue(1.0) });
	g_Yytk->CallBuiltin("draw_set_valign", { RValue(0.0) });
	double ui = gh / 1080.0, scale = 0.55 * ui;
	std::string label = hover->Names;
	std::string status = hover->State == 1 ? "in logic" : (hover->State == 2 ? "not in logic yet" : "checked");
	RValue t1{ std::string_view(label) };
	RValue t2{ std::string_view(status) };
	double w = std::max(Builtin("string_width", { t1 }), Builtin("string_width", { t2 })) * scale;
	double lh = Builtin("string_height", { t1 }) * scale;
	double y0 = cy + size * 0.7, pad = 8 * ui;
	g_Yytk->CallBuiltin("draw_set_alpha", { RValue(0.75) });
	g_Yytk->CallBuiltin("draw_set_colour", { RValue(0.0) });
	g_Yytk->CallBuiltin("draw_rectangle", { RValue(cx - w / 2 - pad), RValue(y0 - pad), RValue(cx + w / 2 + pad), RValue(y0 + 2 * lh + pad), RValue(false) });
	g_Yytk->CallBuiltin("draw_set_alpha", { RValue(1.0) });
	RValue white(16777215.0);
	RValue sc2(hover->State == 1 ? HexColor("7CFC8A") : (hover->State == 2 ? HexColor("FA8072") : HexColor("BBBBBB")));
	g_Yytk->CallBuiltin("draw_text_transformed_colour", { RValue(cx), RValue(y0), t1, RValue(scale), RValue(scale), RValue(0.0), white, white, white, white, RValue(1.0) });
	g_Yytk->CallBuiltin("draw_text_transformed_colour", { RValue(cx), RValue(y0 + lh), t2, RValue(scale), RValue(scale), RValue(0.0), sc2, sc2, sc2, sc2, RValue(1.0) });
	if (!oldFont.IsUndefined()) g_Yytk->CallBuiltin("draw_set_font", { oldFont });
	g_Yytk->CallBuiltin("draw_set_halign", { RValue(oldH) });
	g_Yytk->CallBuiltin("draw_set_valign", { RValue(oldV) });
	g_Yytk->CallBuiltin("draw_set_colour", { RValue(oldColor) });
	g_Yytk->CallBuiltin("draw_set_alpha", { RValue(oldAlpha) });
}

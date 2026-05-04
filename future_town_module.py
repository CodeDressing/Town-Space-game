"""
future_town_module.py — Future Town (Tkinter)
Compatible with game_main.py patterns that instantiate: TownView(parent, state, app)

WHAT'S NEW IN THIS PATCH
- CAPITAL NPCs: Receptionist + 2 Guards in the Capital interior. Walk up and press E for small talk & tips.
- ROLE PERKS (applied + shown in HUD):
    Penguin — Hustle: 10% shop discount
    Joker   — Getaway: +8% move speed
    Batman  — Deterrent: faster heat cool-down

FEATURES
- Enterable Town Capital (press E near the building).
- Capital interior movement (WASD/Arrows) + Data Console (press E near console) + new NPCs.
- Quests require traveling to matching buildings: Courier→Logistics Hub, Survey→Power Substation, Patrol→Skyway Watch Post.
- HUD, Day/Night (N), Audio (O), Mini-map (M), Performance mode, Fast Travel, Trade Shop, Quest Log.
- Popups/windows always front-most via _raise_window(); message boxes parented to their owner window.
- Quest state persists in state.quests (list of dicts). Settings persist in state.settings.

PATCH KEYS (searchable sections)
[PATCHKEY: CONFIG_V1]
[PATCHKEY: UTIL_SFX_V1]
[PATCHKEY: WINDOW_UTILS_V1]
[PATCHKEY: APP_API_HELPERS_V1]
[PATCHKEY: WORLD_CONSTANTS_V1]
[PATCHKEY: WORLD_BUILDINGS_V1]
[PATCHKEY: ROLE_PERKS_V1]
[PATCHKEY: VIEW_INIT_V1]
[PATCHKEY: INPUT_V1]
[PATCHKEY: GAME_LOOP_V1]
[PATCHKEY: WORLD_HELPERS_V1]
[PATCHKEY: DRAW_OVERWORLD_V1]
[PATCHKEY: HUD_OVERLAY_V1]
[PATCHKEY: HEAT_AND_WORLD_TICK_V1]
[PATCHKEY: CAPITAL_ENTER_V1]
[PATCHKEY: CAPITAL_INTERIOR_MOVEMENT_V1]
[PATCHKEY: CAPITAL_NPCS_V1]
[PATCHKEY: CAPITAL_HUD_V1]
[PATCHKEY: CAPITAL_TRADE_V1]
[PATCHKEY: CAPITAL_QUESTS_V1]
[PATCHKEY: SETTINGS_HELPERS_V1]
[PATCHKEY: SETTINGS_PANEL_V1]
[PATCHKEY: FAST_TRAVEL_V1]
[PATCHKEY: ALIAS_V1]
"""

# ===========================
# [PATCHKEY: CONFIG_V1]
# ===========================
import tkinter as tk
from tkinter import ttk, messagebox
import time, math, random, platform

# Window
W, H = 960, 540
FPS = 60

# Defaults (can be overridden by persisted state.settings)
AUDIO_ENABLED = True
DAY_NIGHT_ENABLED = True
PATROL_VISUALS_ENABLED = True

# Day/Night speed (bigger = faster)
DAY_NIGHT_SPEED = 0.05

# World Layers (parallax)
SKYLINE_F = 0.30
TOWERS_F  = 0.60
NEAR_F    = 1.00

# Capital placement in world-space
CAPITAL_WORLD_X = 320
CAPITAL_W, CAPITAL_H = 160, 200

# Fast travel destinations (pseudo world x)
FAST_TRAVEL_DESTS = {
    "Home District": -240,
    "Industrial":     760,
    "Town Capital":   CAPITAL_WORLD_X,
}

# Quest offers mapped to destination buildings + rewards
QUEST_OFFERS = [
    {"title": "Courier: Deliver nano-parts to Sector 7",        "target": "logistics",  "reward": 120},
    {"title": "Survey: Scan power conduits along the East Ridge","target": "substation","reward": 140},
    {"title": "Patrol: Assist City Watch on the Skyway",        "target": "watch",      "reward": 160},
]


# ===========================
# [PATCHKEY: UTIL_SFX_V1]
# ===========================
def _play_sfx_beep(widget: tk.Widget, tone: str = "ok"):
    """
    Minimal cross-platform SFX (no screen shake/flash).
    tone: "ok" | "warn" | "info"
    Uses global AUDIO_ENABLED (kept in sync with state.settings).
    """
    if not AUDIO_ENABLED:
        return
    try:
        if platform.system() == "Windows":
            import winsound
            freq = 750 if tone == "ok" else 580 if tone == "warn" else 660
            winsound.Beep(freq, 90)
        else:
            widget.bell()
    except Exception:
        pass


# ===========================
# [PATCHKEY: WINDOW_UTILS_V1]
# ===========================
def _raise_window(win: tk.Toplevel):
    """Ensure Toplevel is front-most and focused (prevents 'behind other tabs')."""
    try:
        win.lift()
        win.attributes("-topmost", True)
        win.focus_force()
        win.after(50, lambda: (win.lift(), win.focus_force(), win.attributes("-topmost", True)))
    except Exception:
        pass


# ===========================
# [PATCHKEY: APP_API_HELPERS_V1]
# ===========================
def _safe_get(d, key, default=None):
    try:
        return d.get(key, default)
    except Exception:
        return default

def _ensure_role(state) -> str:
    inv = getattr(state, "inventory", None)
    if inv is None:
        setattr(state, "inventory", {})
        inv = state.inventory
    if "role" not in inv:
        inv["role"] = "penguin"
    return inv["role"]

def _ensure_heat(state) -> int:
    if not hasattr(state, "heat"):
        state.heat = 0
    return int(state.heat)

def _ensure_quests(state):
    """Ensure quests stored as list[dict]. Convert strings to dicts if needed."""
    if not hasattr(state, "quests") or state.quests is None:
        state.quests = []
    new_list = []
    for q in state.quests:
        if isinstance(q, str):
            new_list.append({"title": q, "target": None, "status": "active", "reward": 0})
        elif isinstance(q, dict):
            q.setdefault("status", "active")
            q.setdefault("target", None)
            q.setdefault("reward", 0)
            new_list.append(q)
    state.quests = new_list
    return state.quests


# ===========================
# [PATCHKEY: WORLD_CONSTANTS_V1]
# ===========================
COLORS = {
    "text": "#e7ecff",
    "sky_base": (30, 30, 70),
}
def _clamp01(x): return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


# ===========================
# [PATCHKEY: WORLD_BUILDINGS_V1]
# ===========================
BUILDINGS = {
    "capital":    {"name": "Town Capital",      "world_x": CAPITAL_WORLD_X, "w": CAPITAL_W, "h": CAPITAL_H},
    "logistics":  {"name": "Logistics Hub",     "world_x": -240,            "w": 120,       "h": 150},
    "substation": {"name": "Power Substation",  "world_x": 760,             "w": 140,       "h": 160},
    "watch":      {"name": "Skyway Watch Post", "world_x": 560,             "w": 130,       "h": 140},
}


# ===========================
# [PATCHKEY: ROLE_PERKS_V1]
# ===========================
ROLE_PERKS = {
    "penguin": {"name": "Hustle",   "desc": "10% shop discount",    "speed_mul": 1.00, "shop_disc": 0.10, "heat_bonus": 0.00},
    "joker":   {"name": "Getaway",  "desc": "+8% move speed",       "speed_mul": 1.08, "shop_disc": 0.00, "heat_bonus": 0.00},
    "batman":  {"name": "Deterrent","desc": "Faster heat cool-down","speed_mul": 1.02, "shop_disc": 0.00, "heat_bonus": 0.15},
}
def _perk_for_role(role: str):
    return ROLE_PERKS.get(role, ROLE_PERKS["penguin"])


# ===========================
# [PATCHKEY: VIEW_INIT_V1]
# ===========================
class FutureTownView(ttk.Frame):
    def __init__(self, parent, state, app):
        super().__init__(parent)
        self.state = state
        self.app = app

        self.canvas = tk.Canvas(
            self, width=W, height=H, bg="#0f1016",
            highlightthickness=1, highlightbackground="#2a2f3a"
        )
        self.canvas.pack(pady=10)

        # Input
        self.keys = set()
        self.canvas.bind("<KeyPress>", self._on_keydown)
        self.canvas.bind("<KeyRelease>", self._on_keyup)
        self.canvas.focus_set()

        # Player + Camera
        self.px, self.py = W // 2, H - 120
        self.scroll_x = 0.0

        # Systems
        _ensure_role(self.state)
        _ensure_heat(self.state)
        _ensure_quests(self.state)
        self.police_active = False
        self._dn_phase = 0.0

        # Settings bootstrapping (persisted)
        self._ensure_settings()
        self._apply_settings()  # sync globals + local flags

        # Capital interior state
        self._cap_win = None
        self._cap_canvas = None
        self._cap_keys = set()
        self._cap_px = 0
        self._cap_py = 0
        self._cap_npcs = []  # populated on enter

        # Start loops
        self._last = time.time()
        self._tick()
        self.after(700, self._world_tick)

    # ===========================
    # [PATCHKEY: INPUT_V1]
    # ===========================
    def _on_keydown(self, e):
        k = e.keysym.lower()
        self.keys.add(k)
        if k == "e":
            self._handle_interact()
        elif k == "o":
            self._toggle_audio()
        elif k == "n":
            self._toggle_day_night()
        elif k == "m":
            self._toggle_minimap()
        elif k == "escape":
            pass

    def _on_keyup(self, e):
        self.keys.discard(e.keysym.lower())

    def _handle_interact(self):
        """Overworld interaction on E: enter Capital, or complete quests at target buildings."""
        if self._player_near_building("capital"):
            self._enter_capital()
            return
        for bid in ("logistics", "substation", "watch"):
            if self._player_near_building(bid):
                if self._try_complete_quests_at(bid):
                    _play_sfx_beep(self, "ok")
                else:
                    self._notice("No active quest here. Check the Quests Board at the Capital.",
                                 "Info", parent=self.winfo_toplevel())
                return

    # ===========================
    # [PATCHKEY: GAME_LOOP_V1]
    # ===========================
    def _tick(self):
        now = time.time()
        dt = max(0.001, min(0.05, now - self._last))
        self._last = now

        vx = (-1 if ("a" in self.keys or "left"  in self.keys) else 0) + \
             ( 1 if ("d" in self.keys or "right" in self.keys) else 0)
        vy = (-1 if ("w" in self.keys or "up"    in self.keys) else 0) + \
             ( 1 if ("s" in self.keys or "down"  in self.keys) else 0)

        # Apply role perk to speed
        role = _ensure_role(self.state)
        speed_base = 240
        speed = speed_base * _perk_for_role(role)["speed_mul"]

        self.px = max(18, min(W-18, self.px + vx*speed*dt))
        self.py = max(18, min(H-18, self.py + vy*speed*dt))
        self.scroll_x += vx * dt * 120

        if DAY_NIGHT_ENABLED:
            self._dn_phase = (self._dn_phase + dt * DAY_NIGHT_SPEED) % 1.0

        self._draw_overworld()
        self.after(int(1000 / FPS), self._tick)

    # ===========================
    # [PATCHKEY: WORLD_HELPERS_V1]
    # ===========================
    def _world_to_screen(self, world_x: float, factor: float, width: float) -> float:
        span = W + width + 2 * 200
        x = (world_x - self.scroll_x * factor)
        x = (x + span) % span
        return x - 200

    def _building_screen_rect(self, bid: str):
        b = BUILDINGS[bid]
        cx = self._world_to_screen(b["world_x"], NEAR_F, b["w"])
        left   = cx - b["w"] // 2
        right  = cx + b["w"] // 2
        top    = H - 140 - b["h"]
        bottom = H - 140
        return (left, top, right, bottom)

    def _player_near_building(self, bid: str, pad: int = 28) -> bool:
        lx, ty, rx, by = self._building_screen_rect(bid)
        px = min(max(self.px, lx - pad), rx + pad)
        py = min(max(self.py, ty - pad), by + pad)
        return (abs(self.px - px) + abs(self.py - py)) <= 48

    def _active_quests_for_target(self, target_id: str):
        _ensure_quests(self.state)
        return [q for q in self.state.quests if q.get("status") == "active" and q.get("target") == target_id]

    def _try_complete_quests_at(self, target_id: str) -> bool:
        qs = self._active_quests_for_target(target_id)
        if not qs:
            return False
        q = qs[0]
        q["status"] = "done"
        reward = int(q.get("reward", 0))
        self.state.money = getattr(self.state, "money", 0) + reward
        self._notice(f"Completed: {q['title']}\nReward: ${reward}", "Quest Complete",
                     parent=self.winfo_toplevel())
        try:
            self.app.update_stats()
        except Exception:
            pass
        return True

    # ===========================
    # [PATCHKEY: DRAW_OVERWORLD_V1]
    # ===========================
    def _draw_overworld(self):
        c = self.canvas
        c.delete("all")

        # PERF: gradient every 3px (or 6px in perf mode)
        step = 6 if getattr(self, "_perf_mode", False) else 3
        for i in range(0, H, step):
            r, g, b = COLORS["sky_base"]
            dn = 0.5 + 0.5 * math.cos(2*math.pi*((i / H) + self._dn_phase)) if DAY_NIGHT_ENABLED else 1.0
            r2 = int(_clamp01((r/255.0) * (0.6 + 0.4 * dn)) * 255)
            g2 = int(_clamp01((g/255.0) * (0.6 + 0.4 * dn)) * 255)
            b2 = int(_clamp01((b/255.0) * (0.7 + 0.3 * dn)) * 255)
            c.create_rectangle(0, i, W, min(H, i+step), fill=f"#{r2:02x}{g2:02x}{b2:02x}", outline="")

        # Far skyline (parallax)
        for i in range(12):
            bx = int((i * 220) % (W + 260)) - 130
            bx = int(bx - (self.scroll_x * SKYLINE_F) % (W + 260))
            c.create_rectangle(bx, H - 360, bx + 180, H, fill="#47507a", outline="")

        # Mid towers (parallax)
        for i in range(10):
            bx = int((i * 260) % (W + 280)) - 140
            bx = int(bx - (self.scroll_x * TOWERS_F) % (W + 280))
            c.create_rectangle(bx, H - 260, bx + 160, H, fill="#5aa0bd", outline="")
            c.create_rectangle(bx + 20, H - 240, bx + 140, H - 120, fill="#89c9e6", outline="")

        # Near platforms (parallax)
        for i in range(8):
            bx = int((i * 300) % (W + 340)) - 170
            bx = int(bx - (self.scroll_x * NEAR_F) % (W + 340))
            c.create_rectangle(bx, H - 140, bx + 220, H - 100, fill="#2a2a3c", outline="")

        # Road
        road_top = H // 2 + 40
        c.create_polygon(W * 0.35, road_top, W * 0.65, road_top, W * 0.9, H, W * 0.1, H,
                         fill="#34363e", outline="")
        for i in range(6):
            t = i / 6
            y = road_top + (H - road_top) * t + 20
            x1 = W * 0.35 + (W * 0.1) * t
            x2 = W * 0.65 - (W * 0.1) * t
            c.create_line(x1, y, x2, y, fill="#d8d8d8")

        # Buildings
        for bid in ("capital", "logistics", "substation", "watch"):
            lx, ty, rx, by = self._building_screen_rect(bid)
            name = BUILDINGS[bid]["name"]
            fill, outline = ("#394b6b", "#8fb7ff") if bid == "capital" else ("#3b3f56", "#8aa2cc")
            c.create_rectangle(lx - 20, by, rx + 20, by + 14, fill="#22262f", outline="#13161b")
            c.create_rectangle(lx, ty, rx, by, fill=fill, outline=outline)
            c.create_rectangle((lx + rx) / 2 - 16, by - 40, (lx + rx) / 2 + 16, by, fill="#1a2233", outline="#99d1ff")
            c.create_text((lx + rx) / 2, ty - 12, text=name.upper(), fill="#cfe8ff",
                          font=("Segoe UI", 10, "bold"))

        # Player (role colors)
        role = _ensure_role(self.state)
        p_fill, p_outline = ("#ffffff", "#0d0d0d") if role == "penguin" else \
                            ("#7e2cb7", "#ffffff") if role == "joker" else \
                            ("#f6c645", "#000000")
        c.create_rectangle(self.px - 18, self.py - 18, self.px + 18, self.py + 18,
                           fill=p_fill, outline=p_outline)
        c.create_rectangle(self.px - 24, self.py - 24, self.px + 24, self.py + 24, outline="#00ffff")

        # Interaction hints
        if self._player_near_building("capital"):
            lx, ty, rx, by = self._building_screen_rect("capital")
            c.create_text((lx + rx) / 2, by + 34, text="Press E to Enter", fill="#b0ffea",
                          font=("Segoe UI", 10, "bold"))
        for bid in ("logistics", "substation", "watch"):
            if self._player_near_building(bid) and self._active_quests_for_target(bid):
                lx, ty, rx, by = self._building_screen_rect(bid)
                c.create_text((lx + rx) / 2, by + 34, text="Press E to Complete Quest", fill="#b0ffea",
                              font=("Segoe UI", 10, "bold"))

        # Top HUD
        c.create_text(10, 10, anchor="nw", fill=COLORS["text"],
                      text=self._top_hud_text(), font=("Segoe UI", 12, "bold"))

        # Patrol visual if heat > 0
        if PATROL_VISUALS_ENABLED and _ensure_heat(self.state) > 0:
            hx = W - 160; hy = 10
            c.create_rectangle(hx, hy, hx+150, hy+26, fill="#321a1a", outline="#883333")
            c.create_text(hx+8, hy+13, anchor="w", text=f"HEAT: {self.state.heat}",
                          fill="#ff9999", font=("Segoe UI", 10, "bold"))

        # Mini-map (top-right)
        if self._minimap_on:
            mmx, mmy, mmw, mmh = W - 170, 44, 160, 100
            c.create_rectangle(mmx, mmy, mmx+mmw, mmy+mmh, fill="#12151d", outline="#3a4a6a")
            wx_center = self.scroll_x
            half_span = 800
            def wx_to_mm(wx):
                t = (wx - (wx_center - half_span)) / (2*half_span)
                t = max(0.0, min(1.0, t))
                return mmx + 6 + t*(mmw - 12)
            c.create_line(mmx+6, mmy+mmh-18, mmx+mmw-6, mmy+mmh-18, fill="#2b3344")
            markers = [("C", BUILDINGS["capital"]["world_x"], "#9dd4ff"),
                       ("L", BUILDINGS["logistics"]["world_x"], "#cfe8ff"),
                       ("S", BUILDINGS["substation"]["world_x"], "#cfe8ff"),
                       ("W", BUILDINGS["watch"]["world_x"], "#cfe8ff")]
            for label, wx, col in markers:
                x = wx_to_mm(wx)
                c.create_rectangle(x-3, mmy+12, x+3, mmy+mmh-22, outline="#6f8fb7")
                c.create_text(x, mmy+8, text=label, fill=col, font=("Segoe UI", 8, "bold"))
            px = wx_to_mm(wx_center)
            c.create_oval(px-3, mmy+mmh-24-3, px+3, mmy+mmh-24+3, fill="#fffbcc", outline="#000")

    # ===========================
    # [PATCHKEY: HUD_OVERLAY_V1]
    # ===========================
    def _top_hud_text(self) -> str:
        parts = ["Future Town"]
        level = getattr(self.state, "level", None)
        money = getattr(self.state, "money", None)
        energy = getattr(self.state, "energy", None)
        role = _ensure_role(self.state)
        perk = _perk_for_role(role)

        if level is not None:  parts.append(f"Lvl {level}")
        if money is not None:  parts.append(f"${money}")
        if energy is not None: parts.append(f"ENG {energy}")
        parts.append(f"Role {role.capitalize()} • Perk {perk['name']}")

        try:
            if hasattr(self.app, "_game_clock_secs"):
                mins = int(self.app._game_clock_secs // 60) % (24 * 60)
                hh, mm = divmod(mins, 60)
                parts.append(f"{hh:02d}:{mm:02d}")
        except Exception:
            pass

        parts.append("WASD/Arrows: Move • E: Interact • O/N/M: Audio/DayNight/Mini-map")
        return "  |  ".join(parts)

    # ===========================
    # [PATCHKEY: HEAT_AND_WORLD_TICK_V1]
    # ===========================
    def _world_tick(self):
        # Role-based heat decay bonus
        role = _ensure_role(self.state)
        base_chance = 0.35
        bonus = _perk_for_role(role)["heat_bonus"]  # Batman +0.15 => 0.50 total
        decay_chance = min(0.80, base_chance + bonus)

        h = _ensure_heat(self.state)
        if h > 0 and random.random() < decay_chance:
            self.state.heat = max(0, h - 1)
            if self.state.heat == 0:
                self.police_active = False
                try:
                    self._notice("GCPD patrol stands down. Heat is clear.", "GCPD",
                                 parent=self.winfo_toplevel())
                except Exception:
                    pass
        self._draw_overworld()
        self.after(700, self._world_tick)

    def _notice(self, text: str, title: str = "Notice", parent=None):
        """Show an info box, parented so it stays above the right window."""
        try:
            if parent is None:
                parent = self.winfo_toplevel()
            messagebox.showinfo(title, text, parent=parent)
            _play_sfx_beep(self, "info")
            try:
                _raise_window(parent)
            except Exception:
                pass
        except Exception:
            pass

    # ===========================
    # [PATCHKEY: CAPITAL_ENTER_V1]
    # ===========================
    def _enter_capital(self):
        _play_sfx_beep(self, "ok")

        w = tk.Toplevel(self)
        self._cap_win = w
        w.title("Town Capital")
        w.geometry("860x560+120+80")
        try: w.transient(self.winfo_toplevel())
        except Exception: pass
        w.grab_set()
        _raise_window(w)

        # Header + HUD
        header = ttk.Frame(w, padding=(10, 8)); header.pack(fill="x")
        ttk.Label(header, text="Town Capital", font=("Segoe UI", 14, "bold")).pack(side="left")
        self._cap_hud_var = tk.StringVar(value=self._capital_hud_text())
        ttk.Label(header, textvariable=self._cap_hud_var, foreground="#1f4a8a").pack(side="right")

        # Interior canvas
        Cw, Ch = 820, 440
        self._cap_canvas = tk.Canvas(w, width=Cw, height=Ch, bg="#12151d", highlightthickness=0)
        self._cap_canvas.pack(padx=16, pady=10)

        # Start position inside Capital
        self._cap_px, self._cap_py = 110, Ch - 120

        # Buttons
        buttons = ttk.Frame(w, padding=(12, 4)); buttons.pack(fill="x")
        ttk.Button(buttons, text="Trade (T)",      command=lambda: self._cap_trade_popup(w)).pack(side="left")
        ttk.Button(buttons, text="Quests (Q)",     command=lambda: self._cap_quests_popup(w)).pack(side="left")
        ttk.Button(buttons, text="Fast Travel (F)",command=lambda: self._cap_fast_travel(w)).pack(side="left")
        ttk.Button(buttons, text="Settings (S)",   command=lambda: self._open_settings(w)).pack(side="left")
        ttk.Button(buttons, text="Leave (Esc)",    command=w.destroy).pack(side="right")

        # Keybinds for interior
        self._cap_keys = set()
        def on_cap_keydown(e):
            k = e.keysym.lower()
            self._cap_keys.add(k)
            if k == "escape":
                w.destroy()
            elif k == "t":
                self._cap_trade_popup(w)
            elif k == "q":
                self._cap_quests_popup(w)
            elif k == "f":
                self._cap_fast_travel(w)
            elif k == "s":
                self._open_settings(w)
            elif k == "e":
                self._cap_interact()
        def on_cap_keyup(e):
            self._cap_keys.discard(e.keysym.lower())
        w.bind("<KeyPress>", on_cap_keydown)
        w.bind("<KeyRelease>", on_cap_keyup)
        w.bind("<FocusIn>", lambda e: _raise_window(w))
        _raise_window(w)

        # Populate NPCs
        self._init_capital_npcs()

        # Begin interior loop
        self._cap_tick()

        # Keep HUD updated
        def hud_tick():
            if not w.winfo_exists():
                return
            self._cap_hud_var.set(self._capital_hud_text())
            w.after(400, hud_tick)
        hud_tick()

    # ===========================
    # [PATCHKEY: CAPITAL_INTERIOR_MOVEMENT_V1]
    # ===========================
    def _is_near_console(self):
        if not self._cap_canvas:
            return False
        Cw = int(self._cap_canvas["width"]); Ch = int(self._cap_canvas["height"])
        cx1, cy1, cx2, cy2 = 180, Ch - 190, 360, Ch - 130
        px, py = self._cap_px, self._cap_py
        cx, cy = (cx1 + cx2) / 2, (cy1 + cy2) / 2
        return abs(px - cx) + abs(py - cy) < 110

    def _cap_interact(self):
        # Console has priority
        if self._is_near_console():
            self._open_data_console()
            return
        # NPCs next
        npc = self._nearest_capital_npc(max_dist=48)
        if npc is not None:
            self._talk_to_npc(npc)
        else:
            self._notice("Move closer to the console or an NPC to interact (E).", "Capital", parent=self._cap_win)

    def _open_data_console(self):
        menu = tk.Toplevel(self._cap_win)
        menu.title("Data Console")
        menu.geometry("300x220+180+140")
        try: menu.transient(self._cap_win)
        except Exception: pass
        menu.grab_set()
        _raise_window(menu)
        ttk.Label(menu, text="DATA CONSOLE", font=("Segoe UI", 12, "bold")).pack(pady=(10,6))
        ttk.Button(menu, text="Quests Board",
                   command=lambda:(menu.destroy(), self._cap_quests_popup(self._cap_win))).pack(fill="x", padx=16, pady=6)
        ttk.Button(menu, text="Trade Terminal",
                   command=lambda:(menu.destroy(), self._cap_trade_popup(self._cap_win))).pack(fill="x", padx=16, pady=6)
        ttk.Button(menu, text="Fast Travel",
                   command=lambda:(menu.destroy(), self._cap_fast_travel(self._cap_win))).pack(fill="x", padx=16, pady=6)
        ttk.Button(menu, text="Close", command=menu.destroy).pack(pady=(8,6))
        menu.bind("<FocusIn>", lambda e: _raise_window(menu))
        _raise_window(menu)

    def _cap_tick(self):
        w = self._cap_win
        if not (w and w.winfo_exists()):
            return
        c = self._cap_canvas
        Cw = int(c["width"]); Ch = int(c["height"])

        vx = (-1 if ("a" in self._cap_keys or "left"  in self._cap_keys) else 0) + \
             ( 1 if ("d" in self._cap_keys or "right" in self._cap_keys) else 0)
        vy = (-1 if ("w" in self._cap_keys or "up"    in self._cap_keys) else 0) + \
             ( 1 if ("s" in self._cap_keys or "down"  in self._cap_keys) else 0)

        # Interior move speed also gets role bonus (smaller base)
        role = _ensure_role(self.state)
        speed_base = 200
        speed = speed_base * _perk_for_role(role)["speed_mul"]

        self._cap_px = max(24, min(Cw-24, self._cap_px + vx * speed / FPS))
        self._cap_py = max(40, min(Ch-24, self._cap_py + vy * speed / FPS))

        # Draw interior
        c.delete("all")
        for i in range(0, Ch, 3):
            val = int(18 + 40 * (i / Ch))
            c.create_rectangle(0, i, Cw, min(Ch, i+3), fill=f"#{val:02x}{val:02x}{(val+14):02x}", outline="")
        c.create_rectangle(0, Ch - 96, Cw, Ch, fill="#1f2430", outline="#2f3a4a")
        c.create_oval(120, Ch - 140, 420, Ch - 60, fill="#1a2030", outline="#2a3250")
        c.create_rectangle(180, Ch - 190, 360, Ch - 130, fill="#1c2a3a", outline="#6cc3ff")
        c.create_text(270, Ch - 210, text="DATA CONSOLE", fill="#9ad7ff",
                      font=("Segoe UI", 10, "bold"))
        for ix in (520, 660, 800):
            c.create_rectangle(ix - 32, Ch - 260, ix + 32, Ch - 100, fill="#24324a", outline="#6ea2d4")
            c.create_rectangle(ix - 22, Ch - 240, ix + 22, Ch - 120, fill="#3b78a6", outline="")

        # NPCs
        self._draw_capital_npcs(c)

        # Player marker
        c.create_oval(self._cap_px - 10, self._cap_py - 10, self._cap_px + 10, self._cap_py + 10,
                      fill="#b4f2ff", outline="#0b3b4a")
        c.create_text(self._cap_px, self._cap_py - 16, text="You", fill="#dff9ff",
                      font=("Segoe UI", 9, "bold"))

        # Console hint when close
        if self._is_near_console():
            c.create_text(270, Ch - 120, text="Press E to use Data Console", fill="#b0ffea",
                          font=("Segoe UI", 10, "bold"))

        w.after(int(1000 / FPS), self._cap_tick)

    # ===========================
    # [PATCHKEY: CAPITAL_NPCS_V1]
    # ===========================
    def _init_capital_npcs(self):
        """Create receptionist + two guards placed in the Capital interior."""
        c = self._cap_canvas
        if not c:
            return
        Cw = int(c["width"]); Ch = int(c["height"])
        self._cap_npcs = [
            {
                "id": "reception",
                "name": "Receptionist",
                "x": 90, "y": Ch - 130,
                "color": "#ffd077",
                "lines": [
                    "Welcome to the Town Capital!",
                    "Tip: Accept a contract, then travel to its building to complete.",
                    "Use the Data Console for Quests, Travel, and Settings.",
                    "Performance trouble? Settings → Performance mode helps.",
                ],
            },
            {
                "id": "guard1",
                "name": "City Guard",
                "x": 520, "y": Ch - 120,
                "color": "#a3d7ff",
                "lines": [
                    "Stay sharp out there.",
                    "If your Heat rises, keep moving until it cools off.",
                    "Mini-map (M) helps you orient around town.",
                    "Fast travel can get you out of a bind.",
                ],
            },
            {
                "id": "guard2",
                "name": "City Guard",
                "x": 660, "y": Ch - 120,
                "color": "#a3d7ff",
                "lines": [
                    "Report anything suspicious.",
                    "The Watch Post handles Patrol contracts.",
                    "Power Substation is east; Logistics is west.",
                    "Keep your energy up; buy snacks at Trade.",
                ],
            },
        ]

    def _draw_capital_npcs(self, canvas: tk.Canvas):
        """Render NPC circles + nameplates; show prompt when near."""
        if not self._cap_npcs:
            return
        for npc in self._cap_npcs:
            x, y = npc["x"], npc["y"]
            canvas.create_oval(x-10, y-10, x+10, y+10, fill=npc["color"], outline="#0b3b4a")
            canvas.create_text(x, y-16, text=npc["name"], fill="#eaf7ff", font=("Segoe UI", 9, "bold"))
            if abs(self._cap_px - x) + abs(self._cap_py - y) < 54:
                canvas.create_text(x, y+18, text="Press E to talk", fill="#b0ffea", font=("Segoe UI", 9, "bold"))

    def _nearest_capital_npc(self, max_dist=48):
        """Return NPC dict if within range, else None."""
        best = None
        best_d = max_dist
        for npc in self._cap_npcs:
            d = abs(self._cap_px - npc["x"]) + abs(self._cap_py - npc["y"])
            if d <= best_d:
                best = npc
                best_d = d
        return best

    def _talk_to_npc(self, npc):
        """Show small-talk/tip line from the given NPC."""
        top = tk.Toplevel(self._cap_win)
        top.title(npc["name"])
        top.geometry("360x160+240+180")
        try: top.transient(self._cap_win)
        except Exception: pass
        top.grab_set()
        _raise_window(top)

        msg = random.choice(npc["lines"]) if npc.get("lines") else "Hello."
        ttk.Label(top, text=npc["name"], font=("Segoe UI", 12, "bold")).pack(pady=(10, 6))
        ttk.Label(top, text=msg, wraplength=320).pack(padx=12)
        ttk.Button(top, text="Close", command=top.destroy).pack(pady=10)

        top.bind("<FocusIn>", lambda e: _raise_window(top))
        _raise_window(top)

    # ===========================
    # [PATCHKEY: CAPITAL_HUD_V1]
    # ===========================
    def _capital_hud_text(self) -> str:
        parts = []
        lvl = getattr(self.state, "level", None)
        money = getattr(self.state, "money", None)
        energy = getattr(self.state, "energy", None)
        role = _ensure_role(self.state)
        perk = _perk_for_role(role)
        if lvl is not None:    parts.append(f"Level {lvl}")
        if role:               parts.append(f"Role: {role.capitalize()}  •  Perk: {perk['name']}")
        if money is not None:  parts.append(f"Credits: ${money}")
        if energy is not None: parts.append(f"Energy: {energy}")
        try:
            if hasattr(self.app, "_game_clock_secs"):
                mins = int(self.app._game_clock_secs // 60) % (24 * 60)
                hh, mm = divmod(mins, 60)
                parts.append(f"{hh:02d}:{mm:02d}")
        except Exception:
            pass
        return "  •  ".join(parts) if parts else "Welcome, Citizen."

    # ===========================
    # [PATCHKEY: CAPITAL_TRADE_V1]
    # ===========================
    def _cap_trade_popup(self, parent):
        _play_sfx_beep(self, "ok")
        top = tk.Toplevel(parent)
        top.title("Trade Terminal")
        top.geometry("380x300+240+140")
        try: top.transient(parent)
        except Exception: pass
        top.grab_set()
        _raise_window(top)

        ttk.Label(top, text="Exchange Center", font=("Segoe UI", 11, "bold")).pack(pady=(10, 6))

        items = [
            ("Coffee", 10, "Boost a little energy."),
            ("Snack",  15, "Refill some energy."),
            ("Toolkit", 60, "Minor repairs & odds."),
        ]

        balance = getattr(self.state, "money", 0)
        role = _ensure_role(self.state)
        perk = _perk_for_role(role)
        disc = perk.get("shop_disc", 0.0)

        # Price line shows discount if any
        price_hint = f" (Penguin discount {int(disc*100)}%)" if disc > 0 else ""
        ttk.Label(top, text=f"Prices shown below{price_hint}").pack()

        bal_var = tk.StringVar(value=f"Your Credits: ${balance}")
        ttk.Label(top, textvariable=bal_var).pack()

        lst = tk.Listbox(top, height=6); lst.pack(fill="both", expand=True, padx=10, pady=6)
        for name, price, desc in items:
            adj = int(round(price * (1.0 - disc)))
            if adj != price:
                lst.insert("end", f"{name:10s}  ${adj:>3}  (was ${price}) — {desc}")
            else:
                lst.insert("end", f"{name:10s}  ${price:>3}  — {desc}")

        def buy():
            sel = lst.curselection()
            if not sel:
                messagebox.showinfo("Trade", "Select an item first.", parent=top); return
            idx = sel[0]
            name, price, _ = items[idx]
            final_price = int(round(price * (1.0 - disc)))
            bal = getattr(self.state, "money", 0)
            if bal < final_price:
                _play_sfx_beep(self, "warn")
                messagebox.showinfo("Trade", "Not enough credits.", parent=top); return
            self.state.money = bal - final_price
            inv = getattr(self.state, "inventory", {})
            inv[name.lower()] = inv.get(name.lower(), 0) + 1
            _play_sfx_beep(self, "ok")
            messagebox.showinfo("Trade", f"Purchased {name} for ${final_price}.", parent=top)
            bal_var.set(f"Your Credits: ${self.state.money}")
            try: self.app.update_stats()
            except Exception: pass
            _raise_window(top)

        btns = ttk.Frame(top, padding=8); btns.pack(fill="x")
        ttk.Button(btns, text="Buy", command=buy).pack(side="left")
        ttk.Button(btns, text="Close", command=top.destroy).pack(side="right")
        top.bind("<FocusIn>", lambda e: _raise_window(top))
        _raise_window(top)

    # ===========================
    # [PATCHKEY: CAPITAL_QUESTS_V1]
    # ===========================
    def _cap_quests_popup(self, parent):
        _play_sfx_beep(self, "ok")
        top = tk.Toplevel(parent)
        top.title("Quests Board")
        top.geometry("520x360+290+160")
        try: top.transient(parent)
        except Exception: pass
        top.grab_set()
        _raise_window(top)

        ttk.Label(top, text="Available Contracts", font=("Segoe UI", 11, "bold")).pack(pady=(10, 8))

        _ensure_quests(self.state)

        offer_lb = tk.Listbox(top, height=6)
        offer_lb.pack(fill="x", padx=10)
        for off in QUEST_OFFERS:
            dst = BUILDINGS[off["target"]]["name"]
            offer_lb.insert("end", f"{off['title']}  →  {dst}  (${off['reward']})")

        ttk.Label(top, text="Your Quests:", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
        log_lb = tk.Listbox(top, height=7)
        log_lb.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        def refresh_log():
            log_lb.delete(0, "end")
            for q in self.state.quests:
                dst = BUILDINGS.get(q.get("target") or "capital", {}).get("name", "?")
                status = q.get("status", "active")
                tag = "[✓]" if status == "done" else "[Active]"
                reward = q.get("reward", 0)
                log_lb.insert("end", f"{tag} {q['title']}  →  {dst}  (${reward})")
        refresh_log()

        def accept():
            sel = offer_lb.curselection()
            if not sel:
                messagebox.showinfo("Quests", "Select a contract first.", parent=top); return
            off = QUEST_OFFERS[sel[0]]
            for q in self.state.quests:
                if q["title"] == off["title"] and q.get("status") == "active":
                    messagebox.showinfo("Quests", "Already accepted.", parent=top); _raise_window(top); return
            self.state.quests.append({"title": off["title"], "target": off["target"],
                                      "status": "active", "reward": off["reward"]})
            _play_sfx_beep(self, "ok")
            messagebox.showinfo("Quests", f"Accepted: {off['title']}\nDestination: {BUILDINGS[off['target']]['name']}",
                                parent=top)
            refresh_log()
            _raise_window(top)

        def complete_here():
            messagebox.showinfo("Quests",
                                "Travel to the quest destination in town and press E near the building to complete.",
                                parent=top)
            _raise_window(top)

        btns = ttk.Frame(top, padding=8); btns.pack(fill="x")
        ttk.Button(btns, text="Accept",   command=accept).pack(side="left")
        ttk.Button(btns, text="Complete (at destination)", command=complete_here).pack(side="left", padx=8)
        ttk.Button(btns, text="Close",    command=top.destroy).pack(side="right")
        top.bind("<FocusIn>", lambda e: _raise_window(top))
        _raise_window(top)

    # ===========================
    # [PATCHKEY: SETTINGS_HELPERS_V1]
    # ===========================
    def _ensure_settings(self):
        if not hasattr(self.state, "settings"):
            self.state.settings = {}
        s = self.state.settings
        s.setdefault("audio_on", AUDIO_ENABLED)
        s.setdefault("day_night_on", DAY_NIGHT_ENABLED)
        s.setdefault("minimap_on", False)
        s.setdefault("perf_mode", False)
        self._minimap_on = bool(s["minimap_on"])
        self._perf_mode  = bool(s["perf_mode"])

    def _apply_settings(self):
        global AUDIO_ENABLED, DAY_NIGHT_ENABLED
        s = self.state.settings
        AUDIO_ENABLED = bool(s.get("audio_on", True))
        DAY_NIGHT_ENABLED = bool(s.get("day_night_on", True))
        self._minimap_on = bool(s.get("minimap_on", False))
        self._perf_mode  = bool(s.get("perf_mode", False))

    def _toggle_audio(self):
        self.state.settings["audio_on"] = not bool(self.state.settings.get("audio_on", True))
        self._apply_settings()
        if AUDIO_ENABLED:
            _play_sfx_beep(self, "ok")
            self._notice("Audio enabled.", "Settings", parent=self.winfo_toplevel())
        else:
            self._notice("Audio disabled.", "Settings", parent=self.winfo_toplevel())

    def _toggle_day_night(self):
        self.state.settings["day_night_on"] = not bool(self.state.settings.get("day_night_on", True))
        self._apply_settings()
        _play_sfx_beep(self, "ok")
        self._draw_overworld()

    def _toggle_minimap(self):
        self.state.settings["minimap_on"] = not bool(self.state.settings.get("minimap_on", False))
        self._apply_settings()
        _play_sfx_beep(self, "ok")
        self._draw_overworld()

    # ===========================
    # [PATCHKEY: SETTINGS_PANEL_V1]
    # ===========================
    def _open_settings(self, parent):
        _play_sfx_beep(self, "ok")
        top = tk.Toplevel(parent)
        top.title("Settings")
        top.geometry("360x240+320+180")
        try: top.transient(parent)
        except Exception: pass
        top.grab_set()
        _raise_window(top)

        ttk.Label(top, text="Gameplay & UI", font=("Segoe UI", 11, "bold")).pack(pady=(10, 6))

        audio_var = tk.BooleanVar(value=bool(self.state.settings.get("audio_on", True)))
        night_var = tk.BooleanVar(value=bool(self.state.settings.get("day_night_on", True)))
        mini_var  = tk.BooleanVar(value=bool(self.state.settings.get("minimap_on", False)))
        perf_var  = tk.BooleanVar(value=bool(self.state.settings.get("perf_mode", False)))

        frm = ttk.Frame(top, padding=8); frm.pack(fill="both", expand=True)
        ttk.Checkbutton(frm, text="Audio (O)", variable=audio_var).grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Checkbutton(frm, text="Day/Night (N)", variable=night_var).grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ttk.Checkbutton(frm, text="Mini-map (M)", variable=mini_var).grid(row=2, column=0, sticky="w", padx=6, pady=4)
        ttk.Checkbutton(frm, text="Performance mode (lighter visuals)", variable=perf_var)\
            .grid(row=3, column=0, sticky="w", padx=6, pady=4)

        def save():
            self.state.settings["audio_on"]   = bool(audio_var.get())
            self.state.settings["day_night_on"] = bool(night_var.get())
            self.state.settings["minimap_on"] = bool(mini_var.get())
            self.state.settings["perf_mode"]  = bool(perf_var.get())
            self._apply_settings()
            _play_sfx_beep(self, "ok")
            self._draw_overworld()
            top.destroy()

        btns = ttk.Frame(top, padding=8); btns.pack(fill="x")
        ttk.Button(btns, text="Save", command=save).pack(side="left")
        ttk.Button(btns, text="Close", command=top.destroy).pack(side="right")
        top.bind("<FocusIn>", lambda e: _raise_window(top))
        _raise_window(top)

    # ===========================
    # [PATCHKEY: FAST_TRAVEL_V1]
    # ===========================
    def _cap_fast_travel(self, parent):
        _play_sfx_beep(self, "ok")
        top = tk.Toplevel(parent)
        top.title("Fast Travel")
        top.geometry("320x200+320+180")
        try: top.transient(parent)
        except Exception: pass
        top.grab_set()
        _raise_window(top)

        ttk.Label(top, text="Choose Destination", font=("Segoe UI", 11, "bold")).pack(pady=(10, 6))
        dest = tk.StringVar(value="Town Capital")
        for name in FAST_TRAVEL_DESTS.keys():
            ttk.Radiobutton(top, text=name, value=name, variable=dest).pack(anchor="w", padx=12)

        def go():
            name = dest.get()
            wx = FAST_TRAVEL_DESTS[name]
            self.px = W // 2
            self.scroll_x = wx
            _play_sfx_beep(self, "ok")
            self._notice(f"Arrived at {name}.", "Travel", parent=top)
            top.destroy()

        btns = ttk.Frame(top, padding=8); btns.pack(fill="x", pady=(8, 6))
        ttk.Button(btns, text="Travel", command=go).pack(side="left")
        ttk.Button(btns, text="Cancel", command=top.destroy).pack(side="right")
        top.bind("<FocusIn>", lambda e: _raise_window(top))
        _raise_window(top)


# ===========================
# [PATCHKEY: ALIAS_V1]
# ===========================
TownView = FutureTownView  # backward-compatible alias
#==================================



#==================================
#==================================

# =========================================================
# [PATCHKEY: FT_MARKET_DYNAMICS_V1] — Daily Prices + Simple Crafting
# =========================================================
# [PATCHKEY: FT_MARKET_DYNAMICS_V3] — Daily Prices + Crafting + No-Freeze Safety
# Append-only patch. Keeps: dynamic prices (BioGel/Alloy/Data), Buy/Sell tabs,
# and Crafting (Alloy + Data → Toolkit+).
# Changes from V2:
#   • FIXED: no escaped quotes in f-strings (no SyntaxError).
#   • Does NOT wrap _handle_interact; your base file already safely notices at
#     non-Capital buildings with no assignment.
#   • Extra safety: focus/Unmap key clears; re-entrant messagebox guard; all
#     dialogs parented + refocus canvas afterwards.
# =========================================================

import time, random, tkinter as tk
from tkinter import ttk, messagebox

# ---------- day index (in-game preferred) ----------
def _md_day_of_year(app):
    try:
        if hasattr(app, "_game_clock_secs"):
            mins = int(app._game_clock_secs // 60)
            return max(0, mins // (24 * 60))
    except Exception:
        pass
    try:
        return int(time.localtime().tm_yday)
    except Exception:
        return 0

# ---------- catalog / recipes ----------
_MD_GOODS = {"BioGel": (28, 54), "Alloy": (36, 72), "Data": (22, 46)}
_MD_RECIPES = {("Alloy", 1, "Data", 1): ("Toolkit+", 1)}

def _md_roll_prices(prev=None):
    prices, arrows = {}, {}
    for k, (lo, hi) in _MD_GOODS.items():
        base = random.randint(lo, hi) + random.randint(-3, 3)
        price = max(1, base)
        prices[k] = price
        if prev and k in prev:
            arrows[k] = "↑" if price > prev[k] else ("↓" if price < prev[k] else "•")
        else:
            arrows[k] = "•"
    return prices, arrows

def _md_ensure_market(state):
    if not hasattr(state, "ft_market") or not isinstance(getattr(state, "ft_market"), dict):
        state.ft_market = {}
    m = state.ft_market
    m.setdefault("prices", {})
    m.setdefault("arrows", {})
    m.setdefault("last_roll_day", -1)
    return m

def _md_inventory(state):
    inv = getattr(state, "inventory", None)
    if inv is None:
        state.inventory = {}
        inv = state.inventory
    return inv

def _md_price_with_perk(price, state):
    role = _ensure_role(state)
    disc = _perk_for_role(role).get("shop_disc", 0.0)
    return int(round(price * (1.0 - float(disc))))

def _md_roll_if_needed(self):
    m = _md_ensure_market(self.state)
    day = _md_day_of_year(self.app)
    if m["last_roll_day"] != day:
        prev = m["prices"]
        prices, arrows = _md_roll_prices(prev)
        m["prices"], m["arrows"], m["last_roll_day"] = prices, arrows, day

# ---------- safe notice & focus restore ----------
def _md_safe_notice(self, title, text, parent=None):
    if getattr(self, "_ui_lock", False):
        return
    self._ui_lock = True
    try:
        if parent is None:
            parent = self.winfo_toplevel()
        messagebox.showinfo(title, text, parent=parent)
        try:
            _raise_window(parent)
        except Exception:
            pass
    finally:
        try:
            self.after(10, lambda: setattr(self, "_ui_lock", False))
        except Exception:
            self._ui_lock = False
        try:
            self.canvas.focus_set()
            self.keys.clear()
        except Exception:
            pass

# ---------- enhanced Trade popup ----------
def _md_open_trade(self, parent):
    _play_sfx_beep(self, "ok")
    _md_roll_if_needed(self)
    m = _md_ensure_market(self.state)
    prices, arrows = dict(m["prices"]), dict(m["arrows"])

    top = tk.Toplevel(parent)
    top.title("Trade Terminal — Exchange Center")
    top.geometry("460x380+240+140")
    try: top.transient(parent)
    except Exception: pass
    top.grab_set()
    _raise_window(top)

    # Header
    hdr = ttk.Frame(top, padding=(10, 6)); hdr.pack(fill="x")
    ttk.Label(hdr, text="Exchange Center", font=("Segoe UI", 12, "bold")).pack(side="left")
    bal_var = tk.StringVar(value=f"Your Credits: ${getattr(self.state, 'money', 0)}")
    ttk.Label(hdr, textvariable=bal_var).pack(side="right")

    nb = ttk.Notebook(top); nb.pack(fill="both", expand=True, padx=8, pady=6)

    # ---- BUY ----
    buy_fr = ttk.Frame(nb); nb.add(buy_fr, text="Buy")
    ttk.Label(buy_fr, text="Goods (daily prices)").pack(anchor="w", padx=8, pady=(6,2))
    buy_lb = tk.Listbox(buy_fr, height=8); buy_lb.pack(fill="both", expand=True, padx=8)

    role = _ensure_role(self.state)
    disc = _perk_for_role(role).get("shop_disc", 0.0)
    ttk.Label(
        buy_fr,
        text=(f"Penguin discount {int(disc*100)}%" if disc > 0 else "No discount"),
        foreground="#1f4a8a"
    ).pack(anchor="w", padx=8, pady=(2,6))

    def refresh_buy():
        buy_lb.delete(0, "end")
        for name in ("BioGel", "Alloy", "Data"):
            p = prices.get(name, 0)
            adj = _md_price_with_perk(p, self.state)
            arrow = arrows.get(name, "•")
            tail = f" {arrow}" if arrow != "•" else ""
            buy_lb.insert("end", f"{name:8s}  ${adj:>3} (base ${p}){tail}")
    refresh_buy()

    def do_buy():
        sel = buy_lb.curselection()
        if not sel:
            _md_safe_notice(self, "Trade", "Select a good first.", parent=top); return
        name = ("BioGel","Alloy","Data")[sel[0]]
        price = _md_price_with_perk(prices.get(name, 0), self.state)
        bal = int(getattr(self.state, "money", 0))
        if bal < price:
            _play_sfx_beep(self, "warn")
            _md_safe_notice(self, "Trade", "Not enough credits.", parent=top); return
        self.state.money = bal - price
        inv = _md_inventory(self.state)
        inv[name] = int(inv.get(name, 0)) + 1
        _play_sfx_beep(self, "ok")
        _md_safe_notice(self, "Trade", f"Purchased {name} for ${price}.", parent=top)
        bal_var.set(f"Your Credits: ${self.state.money}")
        try: self.app.update_stats()
        except Exception: pass

    ttk.Button(buy_fr, text="Buy Selected", command=do_buy).pack(pady=6)

    # ---- SELL ----
    sell_fr = ttk.Frame(nb); nb.add(sell_fr, text="Sell")
    ttk.Label(sell_fr, text="Your inventory (sell @ 70% of base price)").pack(anchor="w", padx=8, pady=(6,2))
    sell_lb = tk.Listbox(sell_fr, height=8); sell_lb.pack(fill="both", expand=True, padx=8)

    def refresh_sell():
        sell_lb.delete(0, "end")
        inv = _md_inventory(self.state)
        for name in ("BioGel","Alloy","Data"):
            qty = int(inv.get(name, 0))
            p = prices.get(name, 0)
            sell_price = max(1, int(p * 0.70))
            sell_lb.insert("end", f"{name:8s}  x{qty:<3d}  →  ${sell_price} each")
    refresh_sell()

    def do_sell():
        sel = sell_lb.curselection()
        if not sel:
            _md_safe_notice(self, "Trade", "Select a good to sell.", parent=top); return
        name = ("BioGel","Alloy","Data")[sel[0]]
        inv = _md_inventory(self.state)
        if int(inv.get(name, 0)) <= 0:
            _play_sfx_beep(self, "warn")
            _md_safe_notice(self, "Trade", f"No {name} to sell.", parent=top); return
        p = prices.get(name, 0)
        sell_price = max(1, int(p * 0.70))
        inv[name] = int(inv.get(name, 0)) - 1
        self.state.money = int(getattr(self.state, "money", 0)) + sell_price
        _play_sfx_beep(self, "ok")
        _md_safe_notice(self, "Trade", f"Sold 1 {name} for ${sell_price}.", parent=top)
        bal_var.set(f"Your Credits: ${self.state.money}")
        refresh_sell()
        try: self.app.update_stats()
        except Exception: pass

    ttk.Button(sell_fr, text="Sell Selected", command=do_sell).pack(pady=6)

    # ---- CRAFT ----
    craft_fr = ttk.Frame(nb); nb.add(craft_fr, text="Craft")
    ttk.Label(craft_fr, text="Combine materials into useful items").pack(anchor="w", padx=8, pady=(6,2))
    craft_lb = tk.Listbox(craft_fr, height=6); craft_lb.pack(fill="x", padx=8)
    craft_lb.insert("end", "Alloy (1) + Data (1) → Toolkit+ (1)")

    inv_view = tk.StringVar()
    def refresh_inv_view():
        inv = _md_inventory(self.state)
        inv_s = ", ".join(f"{k}:{v}" for k, v in inv.items()
                          if k in ("BioGel","Alloy","Data","Toolkit","Toolkit+"))
        inv_view.set(f"Inventory: {inv_s or '(empty)'}")
    refresh_inv_view()
    ttk.Label(craft_fr, textvariable=inv_view, foreground="#1f4a8a").pack(anchor="w", padx=8, pady=(2,6))

    def do_craft():
        inv = _md_inventory(self.state)
        if int(inv.get("Alloy", 0)) < 1 or int(inv.get("Data", 0)) < 1:
            _play_sfx_beep(self, "warn")
            _md_safe_notice(self, "Craft", "Not enough materials.", parent=top); return
        inv["Alloy"]  = int(inv.get("Alloy", 0))  - 1
        inv["Data"]   = int(inv.get("Data", 0))   - 1
        inv["Toolkit+"] = int(inv.get("Toolkit+", 0)) + 1
        _play_sfx_beep(self, "ok")
        _md_safe_notice(self, "Craft", "Crafted Toolkit+ x1.", parent=top)
        refresh_inv_view()
        refresh_sell()
        try: self.app.update_stats()
        except Exception: pass

    ttk.Button(craft_fr, text="Craft", command=do_craft).pack(pady=6)

    # keep front-most & healthy focus
    top.bind("<FocusIn>", lambda e: _raise_window(top))
    _raise_window(top)

# ---------- installer: small init guards + trade replacement ----------
try:
    _MD_OLD_INIT = FutureTownView.__init__
    def _MD_INIT_WRAP(self, parent, state, app):
        _MD_OLD_INIT(self, parent, state, app)
        # dialog/UI guard + key safety on focus changes
        self._ui_lock = False
        try:
            self.canvas.bind("<FocusOut>", lambda e: self.keys.clear(), add="+")
            self.canvas.bind("<Unmap>",    lambda e: self.keys.clear(), add="+")
        except Exception:
            pass
        # ensure daily prices exist on first frame
        try:
            self.after(0, lambda: _md_roll_if_needed(self))
        except Exception:
            _md_roll_if_needed(self)
    FutureTownView.__init__ = _MD_INIT_WRAP

    # Swap in enhanced Trade; keep original around as fallback
    _MD_OLD_TRADE = FutureTownView._cap_trade_popup
    def _MD_TRADE_WRAP(self, parent):
        try:
            _md_open_trade(self, parent)
        except Exception:
            _MD_OLD_TRADE(self, parent)
    FutureTownView._cap_trade_popup = _MD_TRADE_WRAP
except Exception:
    # If anything fails, leave the base game untouched.
    pass



#==================================
#==================================
# town_racetrack_module.py — Town Racetrack v6.2 (stable loop + PB HUD + Difficulty + Start Lights)
# -------------------------------------------------------------------------------------------------
# View class: RaceTrackView(parent, state, app)
# - GameMain-compatible (App._swap_view(...)); Esc returns to Classic Town via app.show_town_classic()
# - Fixes prior "can’t start new race" + freezing issues by using canvas-scoped input, guarded tick,
#   and cancel-on-destroy scheduling.
# - Clean state machine: IDLE → COUNTDOWN → RACING → RESULTS → IDLE.
# - New: Session & All-time PB HUD; Difficulty selector (persisted); Start lights + input lock.
# - Patch-friendly: Large patches can be appended at the bottom in the PATCHES section without
#   touching core flow.
#
# Tracks & Unlocks:
#   T1: open
#   T2: Intelligence ≥ 20
#   T3: Level ≥ 20 (best-effort from app/state/xp)
#   T4: Intelligence ≥ 40
#
# Controls:
#   Arrow/WASD up/down = change lane
#   Space/Left-Shift   = boost (short burst + cooldown)
#   Esc                = back to Classic Town

from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
import math, random, time, json, os, threading
from typing import Optional, List, Tuple

__all__ = ["RaceTrackView"]

# ---------- Look & feel ----------
W, H   = 1000, 640
FPS    = 60
LANES  = 5                 # player + 4 bots
LANE_W = 20
TICK_MS = int(1000 / FPS)

# Oval geometry
OVAL_RX, OVAL_RY = (W//2 - 120, H//2 - 120)
CENTER = (W//2, H//2)

# Player physics
PLAYER_ACCEL = 0.05
PLAYER_MAX_SPEED = 3.0
FRICTION = 0.03

# Laps to win
LAPS_TO_WIN = 3

# ---------- Progression & Rewards ----------
REQS = {
   1: None,
   2: ("intelligence", 20, "Track 2 locked: Intelligence ≥ 20 required"),
   3: ("level",       20, "Track 3 locked: Level ≥ 20 required"),
   4: ("intelligence", 40, "Track 4 locked: Intelligence ≥ 40 required"),
}

REWARDS = {
   1: {"money": 150, "xp":  40},
   2: {"money": 250, "xp":  70},
   3: {"money": 350, "xp": 110},
   4: {"money": 500, "xp": 160},
}

BOT_SPEED = {
   1: (1.60, 2.00),
   2: (1.80, 2.20),
   3: (2.05, 2.45),
   4: (2.25, 2.75),
}

# ---------- Optional SFX (non-blocking) ----------
ENABLE_SFX = False  # set True if you want beeps

def _beep_async(f=880, d=120):
    if not ENABLE_SFX: return
    def _worker():
        try:
            import winsound
            winsound.Beep(int(f), int(d))
        except Exception:
            pass
    threading.Thread(target=_worker, daemon=True).start()

# ---------- Math helpers ----------
def angle_wrap(a: float) -> float:
    while a < -math.pi: a += 2*math.pi
    while a >= math.pi: a -= 2*math.pi
    return a

def oval_xy_from_angle(theta: float, lane_index: int) -> Tuple[float, float]:
    r_lane = lane_index * LANE_W
    rx = OVAL_RX - r_lane
    ry = OVAL_RY - r_lane
    cx, cy = CENTER
    return cx + rx*math.cos(theta), cy + ry*math.sin(theta)

# ---------- Obstacles ----------
class Obstacle:
    def __init__(self, lane: int, theta: float, width_deg=12, color="#CC3333"):
        self.lane = lane
        self.theta = theta
        self.width = math.radians(width_deg)
        self.color = color
        self.vtheta = 0.0
    def update(self, dt: float):
        self.theta = angle_wrap(self.theta + self.vtheta * dt)
    def conflicts(self, theta: float, lane: int) -> bool:
        if lane != self.lane: return False
        d = abs(angle_wrap(theta - self.theta))
        return d < (self.width * 0.5)

class LaneSwapObstacle(Obstacle):
    """Swaps lanes on a timer and drifts angularly — used on Track 4."""
    def __init__(self, lane: int, theta: float, lanes: int, swap_secs=2.5, color="#AA22AA"):
        super().__init__(lane, theta, width_deg=12, color=color)
        self._lanes = lanes
        self._timer = 0.0
        self._swap = swap_secs
    def update(self, dt: float):
        self._timer += dt
        if self._timer >= self._swap:
            self._timer = 0.0
            self.lane = 1 + (self.lane % max(1, self._lanes - 1))
        self.vtheta = 0.2
        super().update(dt)

# ---------- Cars ----------
class Car:
    def __init__(self, name: str, lane: int, color: str, ai=False):
        self.name = name
        self.lane = lane
        self.color = color
        self.theta = -math.pi/2  # start at top (start line)
        self.speed = 0.0
        self.ai = ai
        self.laps = 0
        self.last_theta = self.theta
        self.finished = False
        # boost/cooldown
        self.boost_t = 0.0
        self.cooldown_t = 0.0
    def effective_speed(self) -> float:
        s = self.speed + (0.85 if self.boost_t > 0 else 0.0)
        return max(0.5, s)
    def update(self, dt: float, track_id: int, obstacles: List[Obstacle]):
        if self.finished: return
        if self.ai:
            target = random.uniform(*BOT_SPEED.get(track_id, (1.6, 2.0)))
            ahead_danger = any(o.conflicts(self.theta + 0.25, self.lane) for o in obstacles)
            if ahead_danger: target *= 0.72
            if self.speed < target: self.speed = min(target, self.speed + 0.8*dt)
            else: self.speed = max(0.6, self.speed - 1.0*dt)
        else:
            # player friction (boost handled by input)
            self.speed = max(0.0, self.speed - FRICTION)
        # slow when overlapping obstacle
        if any(o.conflicts(self.theta, self.lane) for o in obstacles):
            self.speed *= 0.5
        self.last_theta = self.theta
        self.theta = angle_wrap(self.theta + (self.speed * dt))
        # lap crossing at -π/2 going upward
        crossed = (self.last_theta < -math.pi/2 <= self.theta) or \
                  (self.last_theta > self.theta and self.theta >= -math.pi/2)
        if crossed:
            self.laps += 1

# ---------- Session stats (wins + lap PBs + difficulty) ----------
class SessionStats:
    def __init__(self):
        self.win_counts = {"You": 0, "Bot1": 0, "Bot2": 0, "Bot3": 0, "Bot4": 0}
        self._stats_path = os.path.join(os.path.dirname(__file__), "race_stats.json") if "__file__" in globals() else "race_stats.json"
        self.pb = {"t1": None, "t2": None, "t3": None, "t4": None}
        self.difficulty = "Normal"  # "Easy" | "Normal" | "Hard"
        self._load_json()
    def _load_json(self):
        try:
            if os.path.exists(self._stats_path):
                with open(self._stats_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Back-compat: accept either flat PBs or dict
                if isinstance(data, dict):
                    for k in self.pb.keys():
                        if k in data: self.pb[k] = data[k]
                    if "difficulty" in data:
                        self.difficulty = data.get("difficulty", self.difficulty)
        except Exception:
            pass
    def _save_json(self):
        try:
            out = dict(self.pb)
            out["difficulty"] = self.difficulty
            with open(self._stats_path, "w", encoding="utf-8") as f:
                json.dump(out, f, indent=2)
        except Exception:
            pass
    def record_win(self, name: str):
        self.win_counts[name] = self.win_counts.get(name, 0) + 1
    def best_lap_for(self, track_index: int):
        return self.pb.get(f"t{track_index}")
    def consider_lap_time(self, track_index: int, lap_time: float):
        key = f"t{track_index}"
        old = self.pb.get(key)
        if (old is None) or (lap_time < old):
            self.pb[key] = lap_time
            self._save_json()

# ---------- View (Frame) ----------
class RaceTrackView(ttk.Frame):
    """
    GameMain-compatible view:
      RaceTrackView(parent, state, app)
    - Mounted via App._swap_view(RaceTrackView)
    - Uses parent frame (no new windows)
    - Esc returns to Classic Town via app.show_town_classic()
    """
    # States
    S_IDLE = "IDLE"
    S_COUNTDOWN = "COUNTDOWN"
    S_RACING = "RACING"
    S_RESULTS = "RESULTS"

    def __init__(self, parent, state, app):
        super().__init__(parent)
        self.state, self.app = state, app
        self.stats = SessionStats()

        # Freeze-proof scheduling
        self._tick_job = None
        self._exiting = False

        # Layout container
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True)
        container.grid_columnconfigure(1, weight=1)
        container.grid_rowconfigure(0, weight=1)

        # Left panel: leaderboard + wins + PB HUD
        self.lb_frame = ttk.Frame(container, padding=(8,8))
        self.lb_frame.grid(row=0, column=0, sticky="ns")
        ttk.Label(self.lb_frame, text="Leaderboard", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        self.lb = ttk.Treeview(self.lb_frame, columns=("pos","name","laps"), show="headings", height=22)
        self.lb.heading("pos", text="#"); self.lb.column("pos", width=28, anchor="center")
        self.lb.heading("name", text="Racer"); self.lb.column("name", width=110, anchor="w")
        self.lb.heading("laps", text="Laps");  self.lb.column("laps", width=52, anchor="e")
        self.lb.grid(row=1, column=0, sticky="n")
        self.win_var = tk.StringVar(value=self._wins_text())
        ttk.Label(self.lb_frame, textvariable=self.win_var).grid(row=2, column=0, pady=(6,0), sticky="w")
        self.pb_label_var = tk.StringVar(value="Best Lap — Session: –    All-time: –")
        ttk.Label(self.lb_frame, textvariable=self.pb_label_var, foreground="#4aeea4").grid(row=3, column=0, pady=(4,0), sticky="w")

        # Center: canvas (scoped input + focus)
        self.canvas = tk.Canvas(container, width=W, height=H, bg="#114411", highlightthickness=0)
        self.canvas.grid(row=0, column=1, sticky="nsew", padx=(6,6))
        self.canvas.bind("<KeyPress>", self._on_keydown)
        self.canvas.bind("<KeyRelease>", self._on_keyup)
        self.canvas.bind("<F3>", lambda e: self._toggle_debug())
        self.canvas.focus_set()

        # Right: controls
        panel = ttk.Frame(container, padding=(8,8))
        panel.grid(row=0, column=2, sticky="ns")
        ttk.Label(panel, text="Tracks").grid(row=0, column=0, pady=(0,4))
        self.track_var = tk.IntVar(value=1)
        for i in range(1,5):
            ttk.Radiobutton(panel, text=f"Track {i}", variable=self.track_var, value=i).grid(row=i, column=0, sticky="w")
        self.req_lbl = ttk.Label(panel, text="", foreground="#AA2222")
        self.req_lbl.grid(row=5, column=0, pady=(4,8))
        self.start_btn = ttk.Button(panel, text="Start Race", command=self._start_pressed)
        self.start_btn.grid(row=6, column=0, pady=6, sticky="ew")
        self.btn_boost = ttk.Button(panel, text="Boost (Hold Space)", state="disabled")
        self.btn_boost.grid(row=7, column=0, pady=(0,6), sticky="ew")
        self.info_var = tk.StringVar(value="Select a track and press Start.")
        ttk.Label(panel, textvariable=self.info_var, wraplength=200).grid(row=8, column=0, pady=(6,0))
        # Difficulty
        ttk.Label(panel, text="Difficulty").grid(row=9, column=0, pady=(10,2), sticky="w")
        self.diff_var = tk.StringVar(value=getattr(self.stats, "difficulty", "Normal"))
        for i, d in enumerate(("Easy", "Normal", "Hard"), start=10):
            ttk.Radiobutton(panel, text=d, value=d, variable=self.diff_var,
                            command=lambda: self._on_diff_changed()).grid(row=i, column=0, sticky="w")

        # World state
        self.cars: List[Car] = []
        self.obstacles: List[Obstacle] = []
        self.player: Optional[Car] = None
        self.state_mode = self.S_IDLE
        self.countdown = 0.0
        self._space_down = False
        self._last_time = time.time()
        self.target_laps = LAPS_TO_WIN
        self._last_lane_bump = 0.0   # lane-change debounce
        self._input_locked = False    # during countdown
        self._grid_lights: List[int] = []

        # Debug overlay
        self.debug_overlay = False

        # Draw / loops
        self._draw_static()
        self._update_requirements_label()
        self._schedule_leaderboard_update()
        self._enter_idle()
        self._arm_tick()

        # Lap timing
        self.last_lap_ts = None
        self.best_lap_session = None

        # Clean teardown
        self.bind("<Destroy>", self._on_destroy)

    # ---------- Lifecycle & safety ----------
    def _arm_tick(self):
        if self._exiting: return
        self._tick_job = self.after(TICK_MS, self._tick)
    def _cancel_tick(self):
        if self._tick_job is not None:
            try: self.after_cancel(self._tick_job)
            except Exception: pass
            self._tick_job = None
    def _on_destroy(self, _evt):
        self._exiting = True
        self._cancel_tick()
    def _safe_exists(self) -> bool:
        try: return bool(self.winfo_exists())
        except Exception: return False

    # ---------- HUD helpers ----------
    def _wins_text(self) -> str:
        wc = self.stats.win_counts
        return (f"Wins — You: {wc.get('You',0)} | Bot1: {wc.get('Bot1',0)} | "
                f"Bot2: {wc.get('Bot2',0)} | Bot3: {wc.get('Bot3',0)} | Bot4: {wc.get('Bot4',0)}")
    def _toggle_debug(self):
        self.debug_overlay = not self.debug_overlay
        self._render_cars()
        self.info_var.set(f"Debug overlay {'ON' if self.debug_overlay else 'OFF'} (F3)")

    # ---------- Input (canvas-scoped) ----------
    def _on_keydown(self, e):
        k = e.keysym.lower()
        if k == "escape":
            self._exiting = True
            self._cancel_tick()
            try: self.app.show_town_classic()
            except Exception: pass
            return
        if self._input_locked:
            return
        if k in ("space","shift_l"): self._space_down = True
        if k in ("w","up"):
            t = time.time()
            if self.player and self.player.lane > 0 and (t - self._last_lane_bump) > 0.06:
                self.player.lane -= 1; self._last_lane_bump = t
        if k in ("s","down"):
            t = time.time()
            if self.player and self.player.lane < LANES-1 and (t - self._last_lane_bump) > 0.06:
                self.player.lane += 1; self._last_lane_bump = t
    def _on_keyup(self, e):
        k = e.keysym.lower()
        if k in ("space","shift_l"): self._space_down = False

    # ---------- Requirements ----------
    def _get_level(self) -> int:
        try:
            if hasattr(self.app, "get_player_stat"):
                lv = self.app.get_player_stat("level")
                if isinstance(lv, int): return lv
        except Exception: pass
        try:
            lv = getattr(self.state, "level")
            if isinstance(lv, int): return lv
        except Exception: pass
        try:
            xp = getattr(self.state, "xp")
            return int(xp) // 100
        except Exception:
            return 0
    def _get_stat(self, name, default=0) -> int:
        try:
            if hasattr(self.app, "get_player_stat"):
                return int(self.app.get_player_stat(name))
        except Exception: pass
        try:
            return int(getattr(self.state, name))
        except Exception:
            return int(default)
    def _can_play_track(self, tid: int) -> Tuple[bool, str]:
        req = REQS.get(tid)
        if not req: return True, ""
        stat, need, msg = req
        have = self._get_level() if stat == "level" else self._get_stat(stat, 0)
        return (True, "") if have >= need else (False, msg)
    def _update_requirements_label(self):
        ok, msg = self._can_play_track(self.track_var.get())
        self.req_lbl.configure(text="" if ok else msg)
        if self._safe_exists(): self.after(250, self._update_requirements_label)

    # ---------- Setup ----------
    def _reset_world(self):
        # cars
        self.cars.clear()
        colors = ["#00E5FF", "#FF4D4D", "#FFCC00", "#66FF66", "#CC99FF"]
        self.player = Car("You", lane=0, color=colors[0], ai=False)
        self.cars.append(self.player)
        for ln in range(1, LANES):
            self.cars.append(Car(f"Bot{ln}", lane=ln, color=colors[ln%len(colors)], ai=True))
        # laps & timing
        for c in self.cars:
            c.laps, c.theta, c.speed, c.finished = 0, -math.pi/2, 0.0, False
            c.last_theta = c.theta
        self.last_lap_ts = None
        self.best_lap_session = None
        # obstacles
        self._create_obstacles(self.track_var.get())
        # draw
        self._render_cars(force=True)
        self._refresh_pb_hud()

    def _create_obstacles(self, tid: int):
        self.obstacles.clear()
        if tid == 1:
            return
        if tid == 2:
            o = Obstacle(lane=2, theta=0.0, width_deg=16, color="#DD5522"); o.vtheta = 0.35
            self.obstacles = [o]; return
        if tid == 3:
            o = Obstacle(lane=1, theta=math.pi/3, width_deg=14, color="#33AAEE"); o.vtheta = 0.25
            self.obstacles = [o]; return
        if tid == 4:
            o1 = LaneSwapObstacle(lane=1, theta=math.pi/2, lanes=LANES, swap_secs=2.2, color="#AA22AA")
            o2 = LaneSwapObstacle(lane=3, theta=-math.pi/6, lanes=LANES, swap_secs=3.0, color="#FF6699")
            self.obstacles = [o1, o2]

    # ---------- Difficulty ----------
    def _on_diff_changed(self):
        self.stats.difficulty = self.diff_var.get()
        self.stats._save_json()
        self._toast(f"Difficulty: {self.stats.difficulty}", 700)
    def _bot_speed_mult(self) -> float:
        d = getattr(self.stats, "difficulty", "Normal")
        return 0.9 if d == "Easy" else (1.0 if d == "Normal" else 1.12)

    # ---------- State transitions ----------
    def _enter_idle(self):
        self.state_mode = self.S_IDLE
        self.info_var.set("Select a track and press Start.")
        self.start_btn.config(text="Start Race", state="normal")
        self.btn_boost.config(state="disabled")
        self._reset_world()
    def _enter_countdown(self):
        self.state_mode = self.S_COUNTDOWN
        self.countdown = 3.0
        self.info_var.set("Get ready… 3")
        self.start_btn.config(state="disabled")
        self.btn_boost.config(state="disabled")
        self._input_locked = True
        self._draw_lights(stage=3)  # red
        _beep_async(740, 90)
    def _enter_racing(self):
        self.state_mode = self.S_RACING
        self.info_var.set("Go!")
        self.btn_boost.config(state="normal")
        self._input_locked = False
        self._draw_lights(stage=0)  # clear / green
        _beep_async(880, 120)
    def _enter_results(self, winner: str):
        self.state_mode = self.S_RESULTS
        self.btn_boost.config(state="disabled")
        self.start_btn.config(text="Race Again", state="normal")
        self.info_var.set(f"{winner} wins! Press 'Race Again' or choose another track.")

    # ---------- Buttons ----------
    def _start_pressed(self):
        tid = self.track_var.get()
        ok, msg = self._can_play_track(tid)
        if not ok:
            messagebox.showinfo("Track Locked", msg)
            return
        if self.state_mode in (self.S_IDLE, self.S_RESULTS):
            self._reset_world()
            self._enter_countdown()

    # ---------- Tick (guarded + always reschedules) ----------
    def _tick(self):
        if self._exiting or not self._safe_exists():
            return
        now = time.time()
        dt = min(0.05, max(0.001, now - self._last_time))
        self._last_time = now

        if self.state_mode == self.S_COUNTDOWN:
            self.countdown -= dt
            if self.countdown <= 0:
                self._enter_racing()
            else:
                whole = int(math.ceil(self.countdown))
                self.info_var.set(f"Get ready… {whole}")
                # 3→red, 2→yellow, 1→yellow
                stage = 3 if whole >= 3 else (2 if whole == 2 else (1 if whole == 1 else 0))
                self._draw_lights(stage=stage)
                if abs(self.countdown - whole) < 0.04:
                    _beep_async(620 if stage>0 else 880, 70)
        elif self.state_mode == self.S_RACING:
            self._update_race(dt)

        # draw regardless of state
        self._render_cars()
        self._arm_tick()

    def _update_race(self, dt: float):
        # player input: boost & accelerate
        if self.player:
            if self._space_down and self.player.cooldown_t <= 0.0:
                self.player.boost_t = min(1.5, self.player.boost_t + dt)  # fill while held
                self.player.speed = min(PLAYER_MAX_SPEED + 0.7, self.player.speed + PLAYER_ACCEL*1.4)
            else:
                # spend boost if any; then cooldown
                if self.player.boost_t > 0:
                    self.player.boost_t = max(0.0, self.player.boost_t - 1.5*dt)
                    if self.player.boost_t == 0.0:
                        self.player.cooldown_t = 1.2
                else:
                    self.player.cooldown_t = max(0.0, self.player.cooldown_t - dt)
                self.player.speed = min(PLAYER_MAX_SPEED, self.player.speed + PLAYER_ACCEL)

        # obstacles
        for o in self.obstacles: o.update(dt)

        # cars
        tid = self.track_var.get()
        mult = self._bot_speed_mult()
        for c in self.cars:
            c.update(dt, tid, self.obstacles)
            if c.ai and c.speed > 0:
                c.speed *= mult
            # handle per-lap timing for player
            if c is self.player:
                crossed = (c.last_theta < -math.pi/2 <= c.theta) or (c.last_theta > c.theta and c.theta >= -math.pi/2)
                if crossed:
                    now = time.time()
                    if self.last_lap_ts is not None:
                        lap_time = now - self.last_lap_ts
                        self.stats.consider_lap_time(tid, lap_time)
                        if (self.best_lap_session is None) or (lap_time < self.best_lap_session):
                            self.best_lap_session = lap_time
                            self._toast("New personal lap best!", 800)
                        self._refresh_pb_hud()
                    self.last_lap_ts = now
            # finish condition
            if not c.finished and c.laps >= self.target_laps:
                c.finished = True
                self._on_finish(c)
                break

    # ---------- Finish / Rewards ----------
    def _on_finish(self, winner_car: Car):
        winner = winner_car.name
        self.stats.record_win(winner)
        self.win_var.set(self._wins_text())
        # Award rewards if player wins
        if winner == "You":
            tid = self.track_var.get()
            reward = REWARDS.get(tid, {"money":0,"xp":0})
            try:
                self.state.money = int(getattr(self.state, "money", 0)) + int(reward["money"])
                if hasattr(self.app, "update_stats"): self.app.update_stats()
            except Exception: pass
            try:
                if hasattr(self.app, "gain_experience"):
                    self.app.gain_experience(int(reward["xp"]), f"Race Track {tid} Win")
            except Exception: pass
        self._enter_results(winner)

    # ---------- Drawing ----------
    def _draw_static(self):
        c = self.canvas
        c.delete("static")
        # outer grass
        c.create_rectangle(0,0,W,H, fill="#114411", outline="", tag="static")
        # lanes (simple ovals)
        for li in range(LANES):
            rx = OVAL_RX - li*LANE_W
            ry = OVAL_RY - li*LANE_W
            cx, cy = CENTER
            c.create_oval(cx-rx, cy-ry, cx+rx, cy+ry, outline="#2a6f2a", width=2, tag="static")
        # start/finish line marker at top
        cx, cy = CENTER
        rx, ry = OVAL_RX, OVAL_RY
        c.create_line(cx-40, cy-ry-6, cx+40, cy-ry-6, fill="#eeeeee", width=3, tag="static")

    def _render_cars(self, force=False):
        c = self.canvas
        c.delete("cars")
        # obstacles
        for o in self.obstacles:
            x, y = oval_xy_from_angle(o.theta, o.lane)
            c.create_oval(x-8, y-8, x+8, y+8, fill=o.color, outline="#222", width=2, tag="cars")
        # cars
        for car in self.cars:
            x, y = oval_xy_from_angle(car.theta, car.lane)
            c.create_oval(x-10, y-10, x+10, y+10, fill=car.color, outline="#111", width=2, tag="cars")
            c.create_text(x, y-16, text=("P" if car.name=="You" else car.name), fill="#fff",
                          font=("Segoe UI", 8, "bold"), tag="cars")
        self._refresh_leaderboard()
        # debug overlay hook could go here

    def _refresh_leaderboard(self):
        self.lb.delete(*self.lb.get_children())
        items = []
        for car in self.cars:
            progress = car.laps + (angle_wrap(car.theta + math.pi/2) / (2*math.pi))
            items.append((progress, car))
        items.sort(reverse=True, key=lambda t: t[0])
        for pos, (_, car) in enumerate(items, start=1):
            self.lb.insert("", "end", values=(pos, car.name, car.laps))

    def _schedule_leaderboard_update(self):
        self._refresh_leaderboard()
        if self._safe_exists(): self.after(250, self._schedule_leaderboard_update)

    # ---------- UI helpers ----------
    def _toast(self, text: str, ms=800):
        t = self.canvas.create_text(W//2, 36, text=text, fill="#ffffff", font=("Segoe UI", 14, "bold"), tag="toast")
        self.after(ms, lambda: self.canvas.delete(t))
    def _refresh_pb_hud(self):
        tid = self.track_var.get()
        session = (None if self.best_lap_session is None else f"{self.best_lap_session:.2f}s")
        alltime = self.stats.best_lap_for(tid)
        alltime = (None if alltime is None else f"{alltime:.2f}s")
        self.pb_label_var.set(f"Best Lap — Session: {session or '–'}    All-time: {alltime or '–'}")
    def _draw_lights(self, stage:int):
        # stage: 3/2/1 counting, 0=clear/green-go
        for it in self._grid_lights:
            try: self.canvas.delete(it)
            except Exception: pass
        self._grid_lights.clear()
        cols = []
        if stage == 3: cols = ["#e33", "#333", "#333"]
        elif stage == 2: cols = ["#e33", "#dd3", "#333"]
        elif stage == 1: cols = ["#e33", "#dd3", "#dd3"]
        elif stage == 0: cols = ["#3e3", "#3e3", "#3e3"]
        if not cols: return
        cx, cy = self.canvas.winfo_width()//2, 70
        r, spacing = 12, 36
        for i, col in enumerate(cols):
            it = self.canvas.create_oval(cx- spacing + i*spacing - r, cy-r,
                                         cx- spacing + i*spacing + r, cy+r,
                                         fill=col, outline="#111", width=2, tag="toast")
            self._grid_lights.append(it)

# -------------------------------------------------------------------------------------------------
# PATCHES — append large features below without touching core flow
# -------------------------------------------------------------------------------------------------
# Examples / Guidance:
# - Add new minigame hooks, cinematics, or AI profiles by defining functions here and calling them
#   from the safe extension points above (e.g., inside _update_race, on finish, etc.).
# - Keep teardown rules: do not create new global binds; bind to self.canvas, and cancel timers on exit.
# - Use self._toast(...) for small HUD messages; prefer storing persistent values in SessionStats.
#
# Patch A: (example) Alternate AI profiles per track (not enabled by default)
# def _apply_ai_profile(self, track_id:int, car:Car):
#     ...
#
# Patch B: (example) Power-ups
# def add_powerups(self):
#     ...

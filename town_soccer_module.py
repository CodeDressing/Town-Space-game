# town_soccer_module.py — TownSoccerView (compatible with game_main.py v5)
# - 1P vs CPU (default) or 2-Player (press 1/2 to switch at any time)
# - P1: WASD move, E to kick (hold to charge)
# - P2: Arrows move, Space to kick (hold to charge)
# - Goals register reliably; P1 goals grant XP; GameState soccer scores updated

from __future__ import annotations
import tkinter as tk
from tkinter import ttk
import math, time, random

__all__ = ["TownSoccerView"]

# Field & timing
FIELD_W, FIELD_H = 960, 540
GOAL_W, GOAL_H = 16, 180
FPS = 60

# Entities & physics
PLAYER_RADIUS = 16
BALL_RADIUS = 10
STEAL_DISTANCE = 20
INTERCEPT_DISTANCE = 18
MOVE_SPEED = 7.0
DRIBBLE_OFFSET = 22
BALL_FRICTION = 0.985
KICK_SPEED_MIN = 10.0
KICK_SPEED_MAX = 22.0
KICK_CHARGE_RATE = 28.0
AI_KICK_BASE = 0.65
AI_MARK_DIST = 120.0
GOAL_XP = 10   # XP granted when P1 (left team) scores

# Controls
KICK_KEY_P1 = "e"
KICK_KEY_P2 = "space"

COL = {
    "pitch": "#0e5f2e",
    "lines": "#dfe7dd",
    "p1": "#4da3ff",
    "p2": "#ff6b6b",
    "cpu": "#ffa24d",
    "ball": "#f7ee7e",
    "text": "#ffffff",
}

def clamp(v,a,b): return a if v<a else b if v>b else v
def length(vx,vy): return math.hypot(vx,vy)
def norm(vx,vy):
    l = length(vx,vy)
    return (vx/l, vy/l) if l>1e-6 else (0.0,0.0)

def safe_xp(app, amount, source="Soccer"):
    try:
        if amount > 0 and hasattr(app, "gain_experience"):
            app.gain_experience(int(amount), source)
    except Exception:
        pass

class TownSoccerView(ttk.Frame):
    """
    Integration: App._swap_view(TownSoccerView)
    - Esc: exit view
    - 1: Single vs CPU (default), 2: 2-Player
    - P1: WASD to move, E to kick (hold to charge)
    - P2: Arrows to move, Space to kick (hold to charge)
    """
    def __init__(self, parent, state, app):
        super().__init__(parent)
        self.state = state
        self.app = app

        # Layout
        try: self.winfo_toplevel().geometry(f"{FIELD_W+40}x{FIELD_H+140}")
        except Exception: pass

        self.canvas = tk.Canvas(self, width=FIELD_W, height=FIELD_H,
                                bg=COL["pitch"], highlightthickness=1, highlightbackground="#1c3a24")
        self.canvas.pack(pady=10)

        # Mode & input (focus only on canvas)
        self.single_player = True   # default 1P vs CPU
        self.keys = set()
        self.canvas.bind("<KeyPress>", self._on_keydown)
        self.canvas.bind("<KeyRelease>", self._on_keyup)
        self.canvas.focus_set()

        # Init world
        self._init_game()
        self.last_time = time.time()
        self._tick()

    # ---------- Setup / Reset ----------
    def _init_game(self):
        # Reset scoreboard both locally and into GameState
        self.score_L = int(getattr(self.state, "soccer_score_p1", 0))
        self.score_R = int(getattr(self.state, "soccer_score_p2", 0))

        self.canvas.delete("all")
        self._draw_field()

        # HUD
        self.hud = self.canvas.create_text(FIELD_W//2, 14, fill=COL["text"],
                                           font=("Segoe UI", 14, "bold"), text="")
        self.tip = self.canvas.create_text(
            FIELD_W//2, FIELD_H-12, fill="#eeeeee", font=("Segoe UI", 11),
            text="1: Single vs CPU • 2: 2-Player • P1 WASD + E (hold) • P2 Arrows + Space (hold) • R reset • Esc exit"
        )

        self._kickoff(side=random.choice(("L","R")))

    def _kickoff(self, side="L"):
        self.p1 = {"x": FIELD_W*0.25, "y": FIELD_H*0.5, "vx":0, "vy":0, "kick_chg":0.0, "has": (side=="L")}
        self.p2 = {"x": FIELD_W*0.75, "y": FIELD_H*0.5, "vx":0, "vy":0, "kick_chg":0.0, "has": (side=="R")}
        self.cpu_timer = 0.0

        bx = self.p1["x"] if self.p1["has"] else self.p2["x"]
        by = self.p1["y"] if self.p1["has"] else self.p2["y"]
        self.ball = {"x": bx, "y": by, "vx":0.0, "vy":0.0, "owner": ("p1" if self.p1["has"] else "p2")}
        self._draw_all()

    # ---------- Input ----------
    def _on_keydown(self, e):
        k = e.keysym.lower()
        self.keys.add(k)
        if k == "r":
            self._kickoff(side=random.choice(("L","R")))
        elif k == "1":
            self.single_player = True
        elif k == "2":
            self.single_player = False
        elif k == "escape":
            try: self.destroy()
            except Exception: pass

    def _on_keyup(self, e):
        k = e.keysym.lower()
        self.keys.discard(k)

    # ---------- Loop ----------
    def _tick(self):
        now = time.time()
        dt = min(0.05, now - self.last_time)
        self.last_time = now

        self._update_players(dt)
        self._update_ball(dt)
        if self.single_player:
            self._update_ai(dt)

        self._check_goal()
        self._draw_all()
        self.after(int(1000/FPS), self._tick)

    # ---------- Field / Draw ----------
    def _draw_field(self):
        c = self.canvas
        c.create_rectangle(0,0,FIELD_W,FIELD_H, fill=COL["pitch"], outline="")
        # center
        c.create_line(FIELD_W//2, 0, FIELD_W//2, FIELD_H, fill=COL["lines"], width=2)
        r = 60
        c.create_oval(FIELD_W//2-r, FIELD_H//2-r, FIELD_W//2+r, FIELD_H//2+r, outline=COL["lines"], width=2)
        # boxes
        box_w, box_h = 140, 260
        c.create_rectangle(0, (FIELD_H-box_h)//2, box_w, (FIELD_H+box_h)//2, outline=COL["lines"], width=2)
        c.create_rectangle(FIELD_W-box_w, (FIELD_H-box_h)//2, FIELD_W, (FIELD_H+box_h)//2, outline=COL["lines"], width=2)
        # goals (mouth rectangles)
        self.goal_L = (0, (FIELD_H-GOAL_H)//2, GOAL_W, (FIELD_H+GOAL_H)//2)
        self.goal_R = (FIELD_W-GOAL_W, (FIELD_H-GOAL_H)//2, FIELD_W, (FIELD_H+GOAL_H)//2)
        c.create_rectangle(*self.goal_L, outline=COL["lines"], width=3)
        c.create_rectangle(*self.goal_R, outline=COL["lines"], width=3)

    def _draw_all(self):
        c = self.canvas
        c.delete("dyn")
        mode = "1P vs CPU" if self.single_player else "2-Player"
        c.itemconfigure(self.hud, text=f"Mode: {mode}    Score  P1(L): {self.score_L}  -  P2/CPU(R): {self.score_R}")

        # players
        self._draw_player(self.p1["x"], self.p1["y"], COL["p1"], tag="dyn")
        col2 = COL["cpu"] if self.single_player else COL["p2"]
        self._draw_player(self.p2["x"], self.p2["y"], col2, tag="dyn")

        # ball
        c.create_oval(self.ball["x"]-BALL_RADIUS, self.ball["y"]-BALL_RADIUS,
                      self.ball["x"]+BALL_RADIUS, self.ball["y"]+BALL_RADIUS,
                      fill=COL["ball"], outline="#333", width=2, tag="dyn")

    def _draw_player(self, x,y,color, tag=None):
        c = self.canvas
        c.create_oval(x-PLAYER_RADIUS, y-PLAYER_RADIUS, x+PLAYER_RADIUS, y+PLAYER_RADIUS,
                      fill=color, outline="#111", width=2, tag=tag)
        # indicator if owning ball
        if self.ball["owner"] == "p1" and abs(x-self.p1["x"])<0.1 and abs(y-self.p1["y"])<0.1:
            nx,ny = self._aim_dir_for_owner("p1")
            c.create_line(x,y, x+nx*DRIBBLE_OFFSET*0.7, y+ny*DRIBBLE_OFFSET*0.7, fill="#fff", width=3, tag=tag)
        if self.ball["owner"] == "p2" and abs(x-self.p2["x"])<0.1 and abs(y-self.p2["y"])<0.1:
            nx,ny = self._aim_dir_for_owner("p2")
            c.create_line(x,y, x+nx*DRIBBLE_OFFSET*0.7, y+ny*DRIBBLE_OFFSET*0.7, fill="#fff", width=3, tag=tag)

    # ---------- Player updates ----------
    def _update_players(self, dt: float):
        # P1 move (WASD)
        dx = (-1 if "a" in self.keys else 0) + (1 if "d" in self.keys else 0)
        dy = (-1 if "w" in self.keys else 0) + (1 if "s" in self.keys else 0)
        vx, vy = norm(dx, dy)
        self.p1["x"] += vx * MOVE_SPEED
        self.p1["y"] += vy * MOVE_SPEED
        self._clamp_player(self.p1)

        # P2 move (arrows) in 2P mode; CPU moves itself in 1P
        if not self.single_player:
            dx2 = (-1 if "left" in self.keys else 0) + (1 if "right" in self.keys else 0)
            dy2 = (-1 if "up" in self.keys else 0) + (1 if "down" in self.keys else 0)
            vx2, vy2 = norm(dx2, dy2)
            self.p2["x"] += vx2 * MOVE_SPEED
            self.p2["y"] += vy2 * MOVE_SPEED
            self._clamp_player(self.p2)

        # Kick charge/release — P1 uses E, P2 uses Space
        if KICK_KEY_P1 in self.keys:
            self.p1["kick_chg"] = clamp(self.p1["kick_chg"] + KICK_CHARGE_RATE*dt, 0, 100)
        else:
            if self.p1["kick_chg"] > 0:
                self._trigger_kick("p1", self.p1["kick_chg"]/100.0)
                self.p1["kick_chg"] = 0

        if not self.single_player:
            if KICK_KEY_P2 in self.keys:
                self.p2["kick_chg"] = clamp(self.p2["kick_chg"] + KICK_CHARGE_RATE*dt, 0, 100)
            else:
                if self.p2["kick_chg"] > 0:
                    self._trigger_kick("p2", self.p2["kick_chg"]/100.0)
                    self.p2["kick_chg"] = 0

        # Steals (touch dribbled ball)
        self._try_steal("p1","p2")
        self._try_steal("p2","p1")

    def _clamp_player(self, p):
        p["x"] = clamp(p["x"], PLAYER_RADIUS, FIELD_W-PLAYER_RADIUS)
        p["y"] = clamp(p["y"], PLAYER_RADIUS, FIELD_H-PLAYER_RADIUS)

    # ---------- AI (P2) ----------
    def _update_ai(self, dt: float):
        p2, p1, ball = self.p2, self.p1, self.ball
        self.cpu_timer += dt

        if p2["has"]:
            gx, gy = 8, FIELD_H/2  # CPU attacks left goal
            tx, ty = gx, gy + clamp((p1["y"]-gy)*0.4, -80, 80)
            self._cpu_to(p2, tx, ty)
            if math.hypot(p2["x"]-gx, p2["y"]-gy) < 200 or self.cpu_timer > 2.0:
                power = clamp(AI_KICK_BASE + random.uniform(-0.1,0.2), 0.3, 1.0)
                self._trigger_kick("p2", power)
                self.cpu_timer = 0.0
        else:
            if ball["owner"] is None:
                self._cpu_to(p2, ball["x"], ball["y"])
            else:
                vx, vy = self._dir_to_goal(for_player="p1")
                px = p1["x"] + vx*AI_MARK_DIST*0.7
                py = p1["y"] + vy*AI_MARK_DIST*0.7
                self._cpu_to(p2, px, py)

    def _cpu_to(self, p, tx, ty):
        vx, vy = norm(tx - p["x"], ty - p["y"])
        p["x"] += vx * MOVE_SPEED * 0.95
        p["y"] += vy * MOVE_SPEED * 0.95
        self._clamp_player(p)

    def _dir_to_goal(self, for_player="p1"):
        if for_player == "p1":
            gx, gy = FIELD_W-8, FIELD_H/2  # P1 attacks right goal
            return norm(gx - self.p1["x"], gy - self.p1["y"])
        else:
            gx, gy = 8, FIELD_H/2
            return norm(gx - self.p2["x"], gy - self.p2["y"])

    # ---------- Ball actions ----------
    def _aim_dir_for_owner(self, who: str):
        if who == "p1":
            gx, gy = FIELD_W-8, FIELD_H/2
            dirx, diry = norm(gx - self.p1["x"], gy - self.p1["y"])
            # nudge aim with movement keys
            dx = (-1 if "a" in self.keys else 0) + (1 if "d" in self.keys else 0)
            dy = (-1 if "w" in self.keys else 0) + (1 if "s" in self.keys else 0)
            return norm(dirx + dx*0.6, diry + dy*0.6)
        else:
            gx, gy = 8, FIELD_H/2
            vx, vy = norm(gx - self.p2["x"], gy - self.p2["y"])
            return norm(vx + random.uniform(-0.15,0.15), vy + random.uniform(-0.05,0.05))

    def _trigger_kick(self, owner: str, power: float):
        if self.ball["owner"] != owner: return
        dirx, diry = self._aim_dir_for_owner(owner)
        spd = KICK_SPEED_MIN + (KICK_SPEED_MAX - KICK_SPEED_MIN) * clamp(power, 0.0, 1.0)
        self.ball["vx"], self.ball["vy"] = dirx*spd, diry*spd
        self.ball["owner"] = None
        # step forward a bit to avoid instant re-catch
        self.ball["x"] += dirx*(DRIBBLE_OFFSET*0.4)
        self.ball["y"] += diry*(DRIBBLE_OFFSET*0.4)

    def _try_steal(self, taker: str, holder: str):
        if self.ball["owner"] != holder: return
        P = self.p1 if taker=="p1" else self.p2
        H = self.p1 if holder=="p1" else self.p2
        dirx,diry = self._aim_dir_for_owner(holder)
        bx = H["x"] + dirx*DRIBBLE_OFFSET
        by = H["y"] + diry*DRIBBLE_OFFSET
        if math.hypot(P["x"]-bx, P["y"]-by) <= STEAL_DISTANCE:
            self.ball["owner"] = taker
            self.p1["has"] = (taker=="p1"); self.p2["has"] = (taker=="p2")

    def _update_ball(self, dt: float):
        # Dribbled?
        if self.ball["owner"] == "p1":
            dirx, diry = self._aim_dir_for_owner("p1")
            self.ball["x"] = self.p1["x"] + dirx*DRIBBLE_OFFSET
            self.ball["y"] = self.p1["y"] + diry*DRIBBLE_OFFSET
            self.p1["has"] = True; self.p2["has"] = False
            return
        if self.ball["owner"] == "p2":
            dirx, diry = self._aim_dir_for_owner("p2")
            self.ball["x"] = self.p2["x"] + dirx*DRIBBLE_OFFSET
            self.ball["y"] = self.p2["y"] + diry*DRIBBLE_OFFSET
            self.p2["has"] = True; self.p1["has"] = False
            return

        # Free ball physics
        prev_x, prev_y = self.ball["x"], self.ball["y"]
        self.ball["x"] += self.ball["vx"]
        self.ball["y"] += self.ball["vy"]
        self.ball["vx"] *= BALL_FRICTION
        self.ball["vy"] *= BALL_FRICTION

        # Let the ball enter goals without bouncing off the inside edge
        in_left_mouth  = self.goal_L[1] + BALL_RADIUS <= self.ball["y"] <= self.goal_L[3] - BALL_RADIUS
        in_right_mouth = self.goal_R[1] + BALL_RADIUS <= self.ball["y"] <= self.goal_R[3] - BALL_RADIUS

        if self.ball["x"] < BALL_RADIUS and not in_left_mouth:
            self.ball["x"] = BALL_RADIUS; self.ball["vx"] = abs(self.ball["vx"])
        if self.ball["x"] > FIELD_W - BALL_RADIUS and not in_right_mouth:
            self.ball["x"] = FIELD_W - BALL_RADIUS; self.ball["vx"] = -abs(self.ball["vx"])
        if self.ball["y"] < BALL_RADIUS:
            self.ball["y"] = BALL_RADIUS; self.ball["vy"] = abs(self.ball["vy"])
        if self.ball["y"] > FIELD_H - BALL_RADIUS:
            self.ball["y"] = FIELD_H - BALL_RADIUS; self.ball["vy"] = -abs(self.ball["vy"])

        # Interception on the segment from prev->now
        self._check_intercept(prev_x, prev_y, self.ball["x"], self.ball["y"])

    def _check_intercept(self, x0,y0,x1,y1):
        if length(x1-x0, y1-y0) < 0.1: return
        for who in ("p1","p2"):
            if self.ball["owner"] is not None: continue
            P = self.p1 if who=="p1" else self.p2
            if self._dist_point_to_segment(P["x"], P["y"], x0,y0,x1,y1) <= INTERCEPT_DISTANCE:
                self.ball["owner"] = who
                self.ball["vx"] = self.ball["vy"] = 0.0
                self.p1["has"] = (who=="p1"); self.p2["has"] = (who=="p2")
                dirx,diry = self._aim_dir_for_owner(who)
                self.ball["x"], self.ball["y"] = (P["x"] + dirx*DRIBBLE_OFFSET, P["y"] + diry*DRIBBLE_OFFSET)
                break

    def _dist_point_to_segment(self, px,py, x0,y0,x1,y1):
        abx, aby = (x1-x0, y1-y0)
        apx, apy = (px-x0, py-y0)
        ab2 = abx*abx + aby*aby
        t = 0.0 if ab2==0 else max(0.0, min(1.0, (apx*abx + apy*aby)/ab2))
        cx = x0 + abx*t; cy = y0 + aby*t
        return math.hypot(px-cx, py-cy)

    # ---------- Goals / Scoring ----------
    def _check_goal(self):
        x,y = self.ball["x"], self.ball["y"]
        lx0,ly0,lx1,ly1 = self.goal_L
        rx0,ry0,rx1,ry1 = self.goal_R

        # Right team scores on LEFT goal
        if (x - BALL_RADIUS) <= lx1 and ly0 <= y <= ly1:
            self.score_R += 1
            self._sync_scores()
            self._goal_reset(last_scored="R")
            return

        # Left team scores on RIGHT goal
        if (x + BALL_RADIUS) >= rx0 and ry0 <= y <= ry1:
            self.score_L += 1
            # Only P1 goals grant XP
            safe_xp(self.app, GOAL_XP, "Soccer Goal (P1)")
            self._sync_scores()
            self._goal_reset(last_scored="L")
            return

    def _sync_scores(self):
        # reflect into GameState so menu/returns keep the tally
        try:
            self.state.soccer_score_p1 = int(self.score_L)
            self.state.soccer_score_p2 = int(self.score_R)
        except Exception:
            pass

    def _goal_reset(self, last_scored: str):
        # kickoff from conceding side after a brief splash
        self.canvas.create_text(FIELD_W//2, FIELD_H//2, text="GOAL!",
                                fill="#fff", font=("Segoe UI", 36, "bold"), tag="dyn")
        side = "R" if last_scored=="L" else "L"
        self.after(700, lambda: (self.canvas.delete("dyn"), self._kickoff(side=side)))

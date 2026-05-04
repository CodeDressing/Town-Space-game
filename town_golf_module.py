# town_golf_module.py
import tkinter as tk
from tkinter import ttk, messagebox
import math, time, random

W, H = 1000, 700
GREEN = "#dfffe7"
WALL = "#7bbf8d"

BALL_RADIUS = 8
PLAYER_RADIUS = 14
HOLE_RADIUS = 14  # “touch = sink” per request
FRICTION = 0.985
MAX_POWER = 22.0
CHARGE_RATE = 0.25  # power added per tick while space is held
RETRIEVE_RADIUS = 36  # distance to hole to retrieve

BALL_PRICE = 25
CLUB_PRICE = 100

class TownGolfView(ttk.Frame):
    """
    Putt Putt Park (multi-hole)
    Controls:
      Move: Arrows / WASD
      Aim:  Mouse (arrow points from player to mouse)
      Shoot: Hold Space to charge; release Space to shoot
      Retrieve ball from sunk hole: move close and press E
      Spawn new ball (consume 1 from inventory): N
      Back to town: Esc

      Pro Shop (top-left building):
        Stand inside and press Enter to open shop (Buy Club $100, Balls $25)
    """
    def __init__(self, parent, state, app):
        super().__init__(parent)
        self.state, self.app = state, app
        self.canvas = tk.Canvas(self, width=W, height=H, bg=GREEN, highlightthickness=0)
        self.canvas.pack()

        # World setup
        self.player = [160, H-140]
        self.player_speed = 6
        self.ball = None           # [x, y]
        self.vel = [0.0, 0.0]      # [vx, vy]
        self.ball_in_motion = False
        self.ball_sunk = False
        self.sunk_hole_index = None

        # Power charge
        self.charging = False
        self.power = 0.0
        self.last_charge_tick = time.time()

        # Make 5 holes with light randomization
        random.seed(108)
        self.holes = []
        spots = [(W-180, 120), (W-280, 260), (W-140, H//2),
                 (W-300, H-200), (W-120, H-120)]
        for (hx, hy) in spots:
            self.holes.append({"x": hx + random.randint(-10, 10),
                               "y": hy + random.randint(-10, 10),
                               "r": HOLE_RADIUS})

        # Simple interior walls/rails for flavor
        self.obstacles = [
            (240, 160, 260, H-120),
            (420, 80, 440, H-260),
            (600, H-240, 620, H-80),
        ]

        # Pro shop area
        self.shop_rect = (40, 40, 220, 140)

        # Ensure inventory keys exist
        self.state.inventory.setdefault("golf_balls", self.state.golf_balls)
        self.state.golf_balls = self.state.inventory["golf_balls"]
        self.state.golf_has_club = getattr(self.state, "golf_has_club", False)

        # Start with one ball ready if possible
        self.spawn_or_attach_ball(initial=True)

        # Input
        self.bind_all("<KeyPress>", self.on_key_press)
        self.bind_all("<KeyRelease>", self.on_key_release)
        self.after(16, self.loop)

    # ----------------- Core Loop -----------------
    def loop(self):
        # Continue charging if holding space
        if self.charging and not self.ball_in_motion and not self.ball_sunk and self.ball is not None:
            # Accumulate power per frame
            self.power = min(MAX_POWER, self.power + CHARGE_RATE)

        # Physics update
        if self.ball_in_motion and self.ball is not None:
            self.ball[0] += self.vel[0]
            self.ball[1] += self.vel[1]
            self.vel[0] *= FRICTION
            self.vel[1] *= FRICTION

            # Wall bounces
            if self.ball[0] < BALL_RADIUS or self.ball[0] > W - BALL_RADIUS:
                self.vel[0] *= -0.8
                self.ball[0] = max(BALL_RADIUS, min(W - BALL_RADIUS, self.ball[0]))
            if self.ball[1] < BALL_RADIUS or self.ball[1] > H - BALL_RADIUS:
                self.vel[1] *= -0.8
                self.ball[1] = max(BALL_RADIUS, min(H - BALL_RADIUS, self.ball[1]))

            # Obstacle collisions (treat as lines/rects)
            bx, by = self.ball
            for (x1, y1, x2, y2) in self.obstacles:
                if x1 - BALL_RADIUS < bx < x2 + BALL_RADIUS and y1 < by < y2:
                    # vertical post
                    # decide which side to reflect based on proximity
                    if abs(bx - x1) < abs(bx - x2):
                        self.ball[0] = x1 - BALL_RADIUS
                    else:
                        self.ball[0] = x2 + BALL_RADIUS
                    self.vel[0] *= -0.85
                if y1 - BALL_RADIUS < by < y2 + BALL_RADIUS and x1 < bx < x2:
                    # horizontal post
                    if abs(by - y1) < abs(by - y2):
                        self.ball[1] = y1 - BALL_RADIUS
                    else:
                        self.ball[1] = y2 + BALL_RADIUS
                    self.vel[1] *= -0.85

            # Sink on touch (no speed check per request)
            for i, hole in enumerate(self.holes):
                if (self.ball[0] - hole["x"]) ** 2 + (self.ball[1] - hole["y"]) ** 2 < (hole["r"]) ** 2:
                    self.ball_in_motion = False
                    self.ball_sunk = True
                    self.sunk_hole_index = i
                    self.ball[0], self.ball[1] = hole["x"], hole["y"]
                    self.vel = [0.0, 0.0]
                    # XP reward (flat + slight distance bonus)
                    dist = self._dist(self.player, [hole["x"], hole["y"]])
                    xp = 15 + int(dist / 80)
                    self.app.gain_experience(xp, "Putt sunk")
                    break

            # Stop if nearly motionless
            if abs(self.vel[0]) + abs(self.vel[1]) < 0.12:
                self.ball_in_motion = False

        self.draw()
        self.after(16, self.loop)

    # ----------------- Input -----------------
    def on_key_press(self, e):
        k = e.keysym.lower()
        dx = dy = 0

        if k in ("left", "a"):   dx = -self.player_speed
        elif k in ("right", "d"): dx =  self.player_speed
        elif k in ("up", "w"):    dy = -self.player_speed
        elif k in ("down", "s"):  dy =  self.player_speed
        elif k == "space":
            # Start charging only if ball is ready to shoot
            if self.ball is not None and not self.ball_in_motion and not self.ball_sunk:
                self.charging = True
                # If user taps, power will be small—exactly as requested
        elif k == "return":
            # Shop interaction if inside shop
            if self._in_rect(self.player, self.shop_rect):
                self.open_shop()
        elif k == "e":
            # Retrieve ball if sunken and near its hole
            if self.ball_sunk and self.sunk_hole_index is not None:
                hx, hy = self.holes[self.sunk_hole_index]["x"], self.holes[self.sunk_hole_index]["y"]
                if self._dist(self.player, [hx, hy]) <= RETRIEVE_RADIUS:
                    self.ball_sunk = False
                    self.sunk_hole_index = None
                    self.attach_ball_to_player()
        elif k == "n":
            # Spawn a new ball (consumes inventory ball)
            if self.ball is None or self.ball_sunk:
                if self.state.golf_balls > 0:
                    self.state.golf_balls -= 1
                    self.state.inventory["golf_balls"] = self.state.golf_balls
                    self.ball_sunk = False
                    self.sunk_hole_index = None
                    self.attach_ball_to_player()
                else:
                    messagebox.showinfo("No Balls", "You're out of balls—buy more at the Pro Shop (Enter).")
        elif k == "escape":
            self.master.master.show_town_classic()
            return

        if dx or dy:
            # Move player
            self.player[0] = max(20, min(W - 20, self.player[0] + dx))
            self.player[1] = max(20, min(H - 20, self.player[1] + dy))
            # If ball attached, keep it with the player
            if self.ball is not None and not self.ball_in_motion and not self.ball_sunk:
                self.attach_ball_to_player()

    def on_key_release(self, e):
        k = e.keysym.lower()
        if k == "space":
            if self.charging:
                self.charging = False
                # Fire if possible
                if self.ball is not None and not self.ball_in_motion and not self.ball_sunk:
                    if not self.state.golf_has_club:
                        messagebox.showinfo("No Club", "Buy a club at the Pro Shop first (Enter).")
                        self.power = 0.0
                        return
                    # Aim from player toward mouse pointer
                    mx, my = self._mouse_on_canvas()
                    ang = math.atan2(my - self.player[1], mx - self.player[0])
                    power = max(2.0, min(MAX_POWER, self.power))
                    self.power = 0.0
                    # Launch
                    self.ball_in_motion = True
                    self.vel = [math.cos(ang) * power, math.sin(ang) * power]

    # ----------------- Helpers -----------------
    def attach_ball_to_player(self):
        self.ball = [self.player[0] + 24, self.player[1]]
        self.vel = [0.0, 0.0]
        self.ball_in_motion = False

    def spawn_or_attach_ball(self, initial=False):
        """
        If player has a ball in inventory OR we're initial and they don't,
        still give one free ball the first time so they can try the mode.
        """
        if initial and self.state.golf_balls <= 0:
            # one courtesy ball at start if none
            self.state.golf_balls = 1
            self.state.inventory["golf_balls"] = 1
        if self.state.golf_balls > 0:
            # Don't consume for attach—consumption happens only when player presses N to spawn a new without retrieving
            self.attach_ball_to_player()
        else:
            self.ball = None

    def open_shop(self):
        # Simple options dialog
        opts = []
        if not self.state.golf_has_club:
            opts.append(f"Buy Club (${CLUB_PRICE})")
        opts.append(f"Buy Ball (${BALL_PRICE})")
        opts_text = "\n".join(f"{i+1}. {t}" for i, t in enumerate(opts)) or "(No items)"
        choice = messagebox.askquestion("Pro Shop",
                                        f"Welcome to the Pro Shop!\n\n{opts_text}\n\n"
                                        "Yes = first item, No = second (if exists).")
        if choice == "yes" and opts:
            item = opts[0]
        elif choice == "no" and len(opts) > 1:
            item = opts[1]
        else:
            return

        if "Club" in item:
            if self.state.money >= CLUB_PRICE:
                self.state.money -= CLUB_PRICE
                self.state.golf_has_club = True
                self.app.gain_experience(5, "Bought club")
                messagebox.showinfo("Purchased", "You bought a putter. (Easier aiming unlocked!)")
                self.app.update_stats()
            else:
                messagebox.showinfo("Insufficient Funds", "Not enough money for a club.")
        elif "Ball" in item:
            if self.state.money >= BALL_PRICE:
                self.state.money -= BALL_PRICE
                self.state.golf_balls += 1
                self.state.inventory["golf_balls"] = self.state.golf_balls
                self.app.gain_experience(2, "Bought ball")
                self.app.update_stats()
                messagebox.showinfo("Purchased", "You bought a golf ball (+1).")
            else:
                messagebox.showinfo("Insufficient Funds", "Not enough money for a ball.")

    def _mouse_on_canvas(self):
        x = self.winfo_pointerx() - self.winfo_rootx()
        y = self.winfo_pointery() - self.winfo_rooty()
        x = max(0, min(W, x))
        y = max(0, min(H, y))
        return x, y

    @staticmethod
    def _dist(a, b):
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    @staticmethod
    def _in_rect(pt, rect):
        x, y = pt
        x1, y1, x2, y2 = rect
        return x1 <= x <= x2 and y1 <= y <= y2

    # ----------------- Drawing -----------------
    def draw(self):
        c = self.canvas
        c.delete("all")

        # Course background dividers
        c.create_rectangle(0, 0, W, 60, fill="#c8f6d6", outline="")
        c.create_rectangle(0, H-60, W, H, fill="#c8f6d6", outline="")

        # Obstacles
        for (x1, y1, x2, y2) in self.obstacles:
            c.create_rectangle(x1, y1, x2, y2, fill=WALL, outline="#3a6")

        # Shop
        x1, y1, x2, y2 = self.shop_rect
        c.create_rectangle(x1, y1, x2, y2, fill="#fff7cc", outline="#553")
        c.create_text((x1+x2)//2, y1+18, text="PRO SHOP", font=("Segoe UI", 12, "bold"))
        c.create_text((x1+x2)//2, y1+40, text="Enter to Open", font=("Segoe UI", 10))

        # Holes
        for idx, hole in enumerate(self.holes, start=1):
            c.create_oval(hole["x"]-hole["r"], hole["y"]-hole["r"],
                          hole["x"]+hole["r"], hole["y"]+hole["r"],
                          fill="#333", outline="#111")
            c.create_text(hole["x"], hole["y"]-24, text=f"H{idx}", font=("Segoe UI", 9), fill="#222")

        # Player
        px, py = self.player
        c.create_oval(px-PLAYER_RADIUS, py-PLAYER_RADIUS, px+PLAYER_RADIUS, py+PLAYER_RADIUS,
                      fill="#2a78ff", outline="#133a77")

        # Aim arrow (toward mouse)
        mx, my = self._mouse_on_canvas()
        ang = math.atan2(my - py, mx - px)
        c.create_line(px, py, px + math.cos(ang)*48, py + math.sin(ang)*48, width=3)

        # Ball
        if self.ball is not None:
            bx, by = self.ball
            c.create_oval(bx-BALL_RADIUS, by-BALL_RADIUS, bx+BALL_RADIUS, by+BALL_RADIUS,
                          fill="#ffffff", outline="#222")

        # Power bar
        if self.charging:
            bar_w = 200
            frac = min(1.0, self.power / MAX_POWER)
            c.create_rectangle(px-100, py-28, px+100, py-14, fill="#eee", outline="#444")
            c.create_rectangle(px-100, py-28, px-100 + bar_w*frac, py-14, fill="#5be07d", outline="")
            c.create_text(px, py-38, text=f"Power: {self.power:.1f}", font=("Segoe UI", 9))

        # UI text
        c.create_text(10, 10,
                      text="Move: WASD/Arrows  |  Aim: Mouse  |  Shoot: Hold & release Space  |  Esc: Back",
                      anchor="nw", font=("Segoe UI", 10, "bold"))
        c.create_text(10, 30,
                      text="Retrieve sunken ball: walk to hole & press E  |  Spawn new ball: N (uses inventory)",
                      anchor="nw", font=("Segoe UI", 10))
        c.create_text(10, 50,
                      text=f"Balls: {self.state.golf_balls}   Money: ${self.state.money}   Club: {'Yes' if self.state.golf_has_club else 'No'}",
                      anchor="nw", font=("Segoe UI", 10))
        if self.ball_sunk and self.sunk_hole_index is not None:
            hx, hy = self.holes[self.sunk_hole_index]["x"], self.holes[self.sunk_hole_index]["y"]
            d = self._dist(self.player, [hx, hy])
            msg = "Ball sunk! Walk to the hole and press E to retrieve, or press N to spawn a new ball."
            if d <= RETRIEVE_RADIUS:
                msg = "Press E to retrieve your sunken ball."
            c.create_text(W//2, H-30, text=msg, font=("Segoe UI", 10, "bold"))

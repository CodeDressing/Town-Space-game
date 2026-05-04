# town_zombies_module.py — Frontier Town (Zombies) v5.1 (ALL UPGRADES + focus/unpause fixes)
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
import math, random, time

__all__ = ["TownZombiesView"]

# --- Field / timing ---
W, H = 960, 540
FPS = 60

# --- Player ---
PLAYER_R = 14
BASE_SPEED = 4.0
SPRINT_SPEED = 6.5
ENERGY_MAX = 100
ENERGY_DRAIN = 22.0 / FPS
ENERGY_REGEN = 14.0 / FPS
PLAYER_LIVES = 3

# --- Weapons (tiers) ---
WEAPONS = [
    ("Pistol", 0.18, 11.0, 1, 1, 0.00, 0, 0),  # name, cd, speed, dmg, pellets, spread, ammo/shot, pierce
    ("SMG",    0.09, 12.0, 1, 1, 0.06, 1, 0),
    ("Shotgun",0.50, 10.0, 1, 6, 0.35, 4, 0),
    ("Laser",  0.12, 16.0, 1, 1, 0.00, 2, 3),
]
GRENADE_SPEED = 9.0
GRENADE_FUSE  = 0.40
GRENADE_RADIUS = 70
GRENADE_DMG = 6

# --- Bullets ---
BULLET_R = 4
BULLET_TTL = 1.8

# --- Zombies ---
Z_R = 14
WALKER = ("walker", 1.4, 1)
RUNNER = ("runner", 2.1, 1)
BRUTE  = ("brute",  1.0, 3)

# Boss every 5th wave
BOSS_SPEED = 1.1
BOSS_HP_BASE = 30
BOSS_HP_STEP = 6
BOSS_SHOCK_COOLDOWN = 3.5
BOSS_SHOCK_RADIUS = 120
BOSS_SHOCK_DMG = 2

# --- Rewards / damage ---
XP_PER_KILL = 5
MONEY_PER_KILL = 10
XP_WAVE_BONUS = 20
WAVE_MONEY_BONUS = 50
PLAYER_TOUCH_DMG = 12
ZOMBIE_HIT_COOLDOWN = 0.7

# Drops
PICKUP_AMMO_CHANCE   = 0.14
PICKUP_MEDKIT_CHANCE = 0.12
MEDKIT_HEAL = 50

# --- Barricades ---
BARR_T = 10
BARR_MAX_HP = 120
BARR_REPAIR_STEP = 40
BARR_REPAIR_COST = 50
BARR_SLOW = 0.45
BARR_DMG_RATE = 18.0 / FPS

# --- Perks ---
PERKS = {
    "Fleet-Footed": {"desc": "+15% move speed", "apply": "self.perk_speed = 1.15"},
    "Tough Skin":   {"desc": "+20 max HP and heal +20", "apply": "self.max_hp += 20; self.hp = min(self.max_hp, self.hp+20)"},
    "Adrenal Surge":{"desc": "+25% energy regen", "apply": "self.perk_energy = 1.25"},
    "Lucky Drops":  {"desc": "x1.6 pickup chance", "apply": "self.perk_lucky = 1.6"},
}

# --- Colors ---
COL = {
    "bg": "#0d0f14",
    "hud": "#ffffff",
    "muted": "#bbbbbb",
    "p": "#4da3ff",
    "z_w": "#8cff66",
    "z_r": "#ff7f50",
    "z_b": "#ff4d94",
    "z_boss": "#ffd166",
    "b": "#ffee77",
    "hp_bar": "#ff5c5c",
    "hp_back": "#2a2a2a",
    "energy": "#8ecae6",
    "pickup": "#c4f5a1",
    "med": "#ffb3c1",
    "barr": "#8b9bb5",
    "gren": "#ffef9f",
}

def clamp(v,a,b): return a if v<a else b if v>b else v
def dist(ax,ay,bx,by): return math.hypot(ax-bx, ay-by)
def norm(vx,vy):
    l = math.hypot(vx,vy)
    return (vx/l, vy/l) if l>1e-6 else (0.0,0.0)

class TownZombiesView(ttk.Frame):
    """
    Controls:
      Move: WASD / Arrow Keys
      Shoot: F (hold to auto-fire, toward mouse)
      Sprint: Shift
      Grenade: G
      Build/Repair Barricade (near edges): B
      Exit: Esc
    """
    def __init__(self, parent, state, app):
        super().__init__(parent)
        self.state = state
        self.app = app

        try: self.winfo_toplevel().geometry(f"{W+40}x{H+160}")
        except Exception: pass

        self.canvas = tk.Canvas(self, width=W, height=H, bg=COL["bg"],
                                highlightthickness=1, highlightbackground="#161a22")
        self.canvas.pack(pady=10)

        # Inputs bound to canvas only
        self.keys = set()
        self.canvas.bind("<KeyPress>", self._on_keydown)
        self.canvas.bind("<KeyRelease>", self._on_keyup)
        self.canvas.bind("<Motion>", self._on_mouse)
        self.canvas.focus_set()

        # Game state
        self._init_game()

        self.last_t = time.time()
        self._tick()

    # ----- Setup -----
    def _init_game(self):
        # Player
        self.px, self.py = W/2, H/2
        self.max_hp = 100
        self.hp = clamp(int(getattr(self.state, "health", 100)), 1, self.max_hp)
        self.lives = PLAYER_LIVES
        self.energy = ENERGY_MAX
        self.mouse_x, self.mouse_y = W/2, H/2

        # Perks multipliers
        self.perk_speed = 1.0
        self.perk_energy = 1.0
        self.perk_lucky = 1.0
        self.taken_perks = set()

        # Scores
        self.wave = 1
        self.kills_total = int(getattr(self.state, "kills", 0))
        self.kills_wave = 0

        # Weapons / grenades
        self.weapon_level = 0
        self.fire_cd = 0.0
        self.bullets = []
        try:
            if not hasattr(self.state, "ammo"): self.state.ammo = 0
        except Exception:
            pass
        self.grenades = 0
        self.gren_objs = []

        # Enemies / drops
        self.zombies = []
        self.pickups = []

        # Barricades
        self.barr = {
            "left":   {"x1":0,   "y1":80, "x2":BARR_T,        "y2":H-80, "hp":0},
            "right":  {"x1":W-BARR_T,"y1":80, "x2":W,         "y2":H-80, "hp":0},
            "top":    {"x1":80, "y1":0,  "x2":W-80,           "y2":BARR_T, "hp":0},
            "bottom": {"x1":80, "y1":H-BARR_T, "x2":W-80,     "y2":H, "hp":0},
        }

        self.paused = False
        self.shop_win = None
        self._spawn_wave()

        # HUD static
        self.hud_text = self.canvas.create_text(
            8, 12, anchor="w", fill=COL["hud"], font=("Segoe UI", 12, "bold")
        )
        self.canvas.create_text(
            W-8, 12, anchor="e", fill=COL["muted"], font=("Segoe UI", 10),
            text="Move WASD/Arrows • F shoot • Shift sprint • G grenade • B build/repair • Esc exit"
        )

        self._draw_all(hard=True)
        self._sync_up()

    # ----- Input -----
    def _on_keydown(self, e):
        k = e.keysym.lower()
        self.keys.add(k)
        if k == "escape":
            self._commit_highscores_and_exit()
        elif k == "g":
            self._throw_grenade()
        elif k == "b":
            self._build_or_repair_barricade()

    def _on_keyup(self, e):
        k = e.keysym.lower()
        self.keys.discard(k)

    def _on_mouse(self, e):
        self.mouse_x, self.mouse_y = e.x, e.y

    # ----- Loop -----
    def _tick(self):
        now = time.time()
        dt = max(0.001, min(0.05, now - self.last_t))
        self.last_t = now

        if not self.paused:
            self._update_player(dt)
            self._update_bullets(dt)
            self._update_grenades(dt)
            self._update_zombies(dt)
            self._update_pickups(dt)
            self._maybe_fire(dt)
            self._check_end_of_wave()

        self._draw_all()
        self.after(int(1000 / FPS), self._tick)

    # ----- Player -----
    def _update_player(self, dt):
        dx = (-1 if "a" in self.keys or "left" in self.keys else 0) + (1 if "d" in self.keys or "right" in self.keys else 0)
        dy = (-1 if "w" in self.keys or "up" in self.keys else 0) + (1 if "s" in self.keys or "down" in self.keys else 0)
        vx, vy = norm(dx, dy)
        sprinting = ("shift_l" in self.keys) or ("shift_r" in self.keys)
        speed = (SPRINT_SPEED if sprinting and self.energy > 0 else BASE_SPEED) * self.perk_speed

        self.px = clamp(self.px + vx*speed, PLAYER_R, W-PLAYER_R)
        self.py = clamp(self.py + vy*speed, PLAYER_R, H-PLAYER_R)

        if sprinting and (vx or vy):
            self.energy = clamp(self.energy - ENERGY_DRAIN, 0, ENERGY_MAX)
        else:
            self.energy = clamp(self.energy + ENERGY_REGEN * self.perk_energy, 0, ENERGY_MAX)

        self.fire_cd = max(0.0, self.fire_cd - dt)

    # ----- Shooting / Weapons -----
    def _maybe_fire(self, dt):
        if "f" not in self.keys or self.fire_cd > 0.0:
            return
        name, cd, spd, dmg, pellets, spread, ammo_shot, pierce = WEAPONS[self.weapon_level]
        # fallback to pistol if ammo insufficient
        if ammo_shot > 0 and int(getattr(self.state, "ammo", 0)) < ammo_shot:
            name, cd, spd, dmg, pellets, spread, ammo_shot, pierce = WEAPONS[0]

        self.fire_cd = max(0.05, cd * self._fire_rate_mod())

        base_ang = math.atan2(self.mouse_y - self.py, self.mouse_x - self.px)
        for _ in range(pellets):
            ang = base_ang + random.uniform(-spread, spread)
            vx = math.cos(ang) * spd
            vy = math.sin(ang) * spd
            self.bullets.append({
                "x": self.px, "y": self.py, "vx": vx, "vy": vy,
                "ttl": BULLET_TTL, "dmg": dmg, "pierce": pierce
            })

        if ammo_shot > 0 and hasattr(self.state, "ammo"):
            self.state.ammo = max(0, int(self.state.ammo) - ammo_shot)
            if hasattr(self.app, "update_stats"): self.app.update_stats()

    def _fire_rate_mod(self):
        return getattr(self, "_fire_rate_mult", 1.0)

    # ----- Grenades -----
    def _throw_grenade(self):
        if self.grenades <= 0: return
        self.grenades -= 1
        ang = math.atan2(self.mouse_y - self.py, self.mouse_x - self.px)
        vx, vy = math.cos(ang)*GRENADE_SPEED, math.sin(ang)*GRENADE_SPEED
        self.gren_objs.append({"x": self.px, "y": self.py, "vx": vx, "vy": vy, "t": GRENADE_FUSE})

    def _update_grenades(self, dt):
        kept = []
        for g in self.gren_objs:
            g["x"] += g["vx"]; g["y"] += g["vy"]; g["t"] -= dt
            if g["t"] <= 0:
                self._explode(g["x"], g["y"])
            else:
                kept.append(g)
        self.gren_objs = kept

    def _explode(self, x, y):
        for z in self.zombies:
            if dist(x, y, z["x"], z["y"]) <= GRENADE_RADIUS:
                z["hp"] -= GRENADE_DMG
        s = self.canvas.create_oval(x-GRENADE_RADIUS, y-GRENADE_RADIUS, x+GRENADE_RADIUS, y+GRENADE_RADIUS,
                                    outline=COL["gren"], width=3, tag="dyn")
        self.after(180, lambda: self.canvas.delete(s))

    # ----- Bullets -----
    def _update_bullets(self, dt):
        kept = []
        for b in self.bullets:
            b["x"] += b["vx"]; b["y"] += b["vy"]; b["ttl"] -= dt
            if b["ttl"] <= 0: continue
            if b["x"] < -20 or b["x"] > W+20 or b["y"] < -20 or b["y"] > H+20: continue

            hit_any = False
            for z in self.zombies:
                if dist(b["x"], b["y"], z["x"], z["y"]) <= (BULLET_R + Z_R):
                    z["hp"] -= b["dmg"]
                    hit_any = True
                    if b["pierce"] > 0:
                        b["pierce"] -= 1
                        b["ttl"] *= 0.85
                        continue
                    else:
                        b["ttl"] = -1
                        break
            if b["ttl"] > 0 and (not hit_any or b["pierce"] > 0):
                kept.append(b)
        self.bullets = kept

        i = 0
        while i < len(self.zombies):
            if self.zombies[i]["hp"] <= 0:
                self._reward_kill(self.zombies[i].get("is_boss", False))
                drop_bonus = self.perk_lucky
                if random.random() < PICKUP_AMMO_CHANCE * drop_bonus:
                    self.pickups.append({"x": self.zombies[i]["x"], "y": self.zombies[i]["y"], "type": "ammo"})
                elif random.random() < PICKUP_MEDKIT_CHANCE * drop_bonus:
                    self.pickups.append({"x": self.zombies[i]["x"], "y": self.zombies[i]["y"], "type": "med"})
                self.zombies.pop(i)
            else:
                i += 1

    # ----- Zombies -----
    def _spawn_wave(self):
        self.kills_wave = 0
        self._maybe_perk_choice()

        if self.wave % 5 == 0:
            self._spawn_boss_wave(); return

        n = 6 + self.wave * 2
        for _ in range(n):
            t = random.random()
            if self.wave >= 4 and t > 0.75: kind = BRUTE
            elif self.wave >= 2 and t > 0.45: kind = RUNNER
            else: kind = WALKER
            x, y = self._spawn_edge()
            self.zombies.append({"x": x, "y": y, "speed": kind[1], "hp": kind[2], "type": kind[0],
                                 "atk_cd": 0.0, "is_boss": False, "shock_cd": 0.0})

    def _spawn_boss_wave(self):
        bx, by = self._spawn_edge()
        boss_index = (self.wave // 5) - 1
        hp = BOSS_HP_BASE + boss_index * BOSS_HP_STEP
        self.zombies.append({"x": bx, "y": by, "speed": BOSS_SPEED, "hp": hp, "type": "boss",
                             "atk_cd": 0.0, "is_boss": True, "shock_cd": BOSS_SHOCK_COOLDOWN})
        adds = 6 + self.wave
        for _ in range(adds):
            x, y = self._spawn_edge()
            kind = random.choice([WALKER, RUNNER])
            self.zombies.append({"x": x, "y": y, "speed": kind[1], "hp": kind[2], "type": kind[0],
                                 "atk_cd": 0.0, "is_boss": False, "shock_cd": 0.0})

    def _spawn_edge(self):
        side = random.choice(("top","bottom","left","right"))
        m = 24
        if side=="top": return random.randint(m, W-m), -m
        if side=="bottom": return random.randint(m, W-m), H+m
        if side=="left": return -m, random.randint(m, H-m)
        return W+m, random.randint(m, H-m)

    def _update_zombies(self, dt):
        for z in self.zombies:
            # barricades slow / take damage
            slow = 1.0
            for b in self.barr.values():
                if b["hp"] <= 0: continue
                if self._inside_rect(z["x"], z["y"], b["x1"]-2, b["y1"]-2, b["x2"]+2, b["y2"]+2):
                    slow = min(slow, BARR_SLOW)
                    b["hp"] = max(0, b["hp"] - BARR_DMG_RATE)

            nx, ny = norm(self.px - z["x"], self.py - z["y"])
            z["x"] += nx * z["speed"] * slow
            z["y"] += ny * z["speed"] * slow
            z["x"] = clamp(z["x"], -60, W+60)
            z["y"] = clamp(z["y"], -60, H+60)

            # boss shockwave
            if z.get("is_boss"):
                z["shock_cd"] -= dt
                if z["shock_cd"] <= 0.0:
                    z["shock_cd"] = BOSS_SHOCK_COOLDOWN
                    self._boss_shock(z["x"], z["y"])

            # touch damage
            z["atk_cd"] = max(0.0, z["atk_cd"] - dt)
            if z["atk_cd"] <= 0.0 and dist(z["x"], z["y"], self.px, self.py) <= (Z_R + PLAYER_R - 2):
                self._take_damage(PLAYER_TOUCH_DMG)
                z["atk_cd"] = ZOMBIE_HIT_COOLDOWN

    def _boss_shock(self, x, y):
        s = self.canvas.create_oval(x-BOSS_SHOCK_RADIUS, y-BOSS_SHOCK_RADIUS,
                                    x+BOSS_SHOCK_RADIUS, y+BOSS_SHOCK_RADIUS,
                                    outline=COL["z_boss"], width=3, tag="dyn")
        self.after(180, lambda: self.canvas.delete(s))
        if dist(x, y, self.px, self.py) <= BOSS_SHOCK_RADIUS:
            self._take_damage(BOSS_SHOCK_DMG)

    def _inside_rect(self, x,y,x1,y1,x2,y2):
        return (x1 <= x <= x2) and (y1 <= y <= y2)

    # ----- Pickups -----
    def _update_pickups(self, dt):
        i = 0
        while i < len(self.pickups):
            p = self.pickups[i]
            if dist(p["x"], p["y"], self.px, self.py) <= 20:
                if p["type"] == "ammo":
                    try:
                        self.state.ammo = int(getattr(self.state, "ammo", 0)) + 12
                    except Exception:
                        pass
                    if hasattr(self.app, "update_stats"): self.app.update_stats()
                elif p["type"] == "med":
                    self.hp = min(self.max_hp, self.hp + MEDKIT_HEAL)
                self.pickups.pop(i); continue
            i += 1

    # ----- Damage / Rewards / Waves -----
    def _take_damage(self, dmg):
        self.hp = max(0, self.hp - int(dmg))
        try:
            self.state.health = int(self.hp)
            if hasattr(self.app, "update_stats"):
                self.app.update_stats()
        except Exception:
            pass
        if self.hp <= 0:
            self.lives -= 1
            if self.lives <= 0:
                self._splash("YOU DIED", "#ff6b6b")
                self.after(1200, self._commit_highscores_and_exit)
                return
            self.hp = self.max_hp
            self.px, self.py = W/2, H/2

    def _reward_kill(self, boss=False):
        self.kills_wave += 1
        self.kills_total += 1 + (2 if boss else 0)
        try:
            self.state.kills = int(self.kills_total)
            self.state.money = int(getattr(self.state, "money", 0)) + (MONEY_PER_KILL * (2 if boss else 1))
            if hasattr(self.app, "gain_experience"):
                self.app.gain_experience(XP_PER_KILL * (2 if boss else 1), "Zombie kill")
            if hasattr(self.app, "update_stats"):
                self.app.update_stats()
        except Exception:
            pass

    def _check_end_of_wave(self):
        if not self.zombies:
            try:
                if hasattr(self.app, "gain_experience"):
                    self.app.gain_experience(XP_WAVE_BONUS, f"Wave {self.wave} cleared")
                self.state.money = int(getattr(self.state, "money", 0)) + WAVE_MONEY_BONUS
                if hasattr(self.app, "update_stats"): self.app.update_stats()
            except Exception:
                pass
            self.wave += 1
            self._splash(f"WAVE {self.wave}", "#ffd166", t=700)
            self._open_shop()

    # ----- Shop & Perks (with robust unpause/focus) -----
    def _open_shop(self):
        self._pause_game()
        win = tk.Toplevel(self); self.shop_win = win
        win.title("Frontier Shop")
        win.geometry("+{}+{}".format(self.winfo_rootx()+40, self.winfo_rooty()+40))
        win.transient(self.winfo_toplevel()); win.grab_set()

        # unified resume handler (works for button, Esc, or window X)
        def resume_next_wave():
            if win.winfo_exists():
                try: win.grab_release()
                except Exception: pass
                win.destroy()
            self._unpause_game()
            self._spawn_wave()

        win.bind("<Escape>", lambda e: resume_next_wave())
        win.protocol("WM_DELETE_WINDOW", resume_next_wave)

        frm = ttk.Frame(win, padding=10); frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=f"Wave {self.wave-1} cleared! Spend your cash:",
                  font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0,6))

        money_var = tk.StringVar(value=f"Money: ${int(getattr(self.state, 'money', 0))}")
        ttk.Label(frm, textvariable=money_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0,10))

        def spend(cost):
            money = int(getattr(self.state, "money", 0))
            if money < cost:
                messagebox.showwarning("Shop", f"Need ${cost}.")
                return False
            self.state.money = money - cost
            if hasattr(self.app, "update_stats"): self.app.update_stats()
            money_var.set(f"Money: ${self.state.money}")
            return True

        cost_weapon = [0, 150, 300, 600][min(self.weapon_level+1, 3)]
        cost_ammo = 80; cost_rate = 120; cost_speed = 120
        cost_hp = 120; cost_gren = 100; cost_repair_all = 60

        def buy_weapon():
            if self.weapon_level >= len(WEAPONS)-1: return
            if spend(cost_weapon): self.weapon_level += 1

        def buy_ammo():
            if spend(cost_ammo):
                self.state.ammo = int(getattr(self.state, "ammo", 0)) + 24
                if hasattr(self.app, "update_stats"): self.app.update_stats()

        def buy_rate():
            if spend(cost_rate):
                self._fire_rate_mult = getattr(self, "_fire_rate_mult", 1.0) * 0.90

        def buy_speed():
            if spend(cost_speed):
                self.perk_speed *= 1.10

        def buy_hp():
            if spend(cost_hp):
                self.max_hp += 20
                self.hp = min(self.max_hp, self.hp + 20)

        def buy_gren():
            if spend(cost_gren): self.grenades += 3

        def repair_all():
            if spend(cost_repair_all):
                for b in self.barr.values(): b["hp"] = BARR_MAX_HP

        row = 2
        ttk.Button(frm, text=f"Upgrade Weapon → {WEAPONS[self.weapon_level+1][0]} (${cost_weapon})",
                   command=buy_weapon, state=("disabled" if self.weapon_level>=len(WEAPONS)-1 else "normal")).grid(row=row, column=0, sticky="ew", pady=4); row+=1
        ttk.Button(frm, text=f"Buy Ammo +24 (${cost_ammo})", command=buy_ammo).grid(row=row, column=0, sticky="ew", pady=4); row+=1
        ttk.Button(frm, text=f"Fire Rate +10% (${cost_rate})", command=buy_rate).grid(row=row, column=0, sticky="ew", pady=4); row+=1
        ttk.Button(frm, text=f"Speed +10% (${cost_speed})", command=buy_speed).grid(row=row, column=0, sticky="ew", pady=4); row+=1
        ttk.Button(frm, text=f"Max HP +20 (${cost_hp})", command=buy_hp).grid(row=row, column=0, sticky="ew", pady=4); row+=1
        ttk.Button(frm, text=f"Grenades +3 (${cost_gren})", command=buy_gren).grid(row=row, column=0, sticky="ew", pady=4); row+=1
        ttk.Button(frm, text=f"Repair ALL Barricades (${cost_repair_all})", command=repair_all).grid(row=row, column=0, sticky="ew", pady=4); row+=1

        ttk.Separator(frm, orient="horizontal").grid(row=row, column=0, columnspan=2, sticky="ew", pady=8); row+=1
        ttk.Button(frm, text="Resume — Next Wave", command=resume_next_wave).grid(row=row, column=0, sticky="ew")

    def _maybe_perk_choice(self):
        if self.wave in (2,5,8) or ((self.wave-2) % 3 == 0 and self.wave > 2):
            self._open_perk_picker()

    def _open_perk_picker(self):
        choices = [k for k in PERKS.keys() if k not in self.taken_perks]
        if not choices: return
        options = random.sample(choices, k=min(2, len(choices)))

        self._pause_game()
        win = tk.Toplevel(self)
        win.title("Choose a Perk")
        win.geometry("+{}+{}".format(self.winfo_rootx()+120, self.winfo_rooty()+90))
        win.transient(self.winfo_toplevel()); win.grab_set()

        def finish_and_resume():
            if win.winfo_exists():
                try: win.grab_release()
                except Exception: pass
                win.destroy()
            self._unpause_game()

        win.bind("<Escape>", lambda e: finish_and_resume())
        win.protocol("WM_DELETE_WINDOW", finish_and_resume)

        ttk.Label(win, text="Pick ONE perk:", font=("Segoe UI", 12, "bold")).pack(padx=12, pady=(10,6))
        for name in options:
            desc = PERKS[name]["desc"]
            def take(n=name):
                self.taken_perks.add(n)
                exec(PERKS[n]["apply"])  # apply perk effect
                finish_and_resume()
            ttk.Button(win, text=f"{name} — {desc}", command=take).pack(fill="x", padx=12, pady=6)

    # ----- Pause helpers: always restore canvas focus -----
    def _pause_game(self):
        self.paused = True

    def _unpause_game(self):
        self.paused = False
        # important: restore keyboard focus to the canvas
        try: self.canvas.focus_set()
        except Exception: pass

    # ----- Barricades -----
    def _build_or_repair_barricade(self):
        for b in self.barr.values():
            cx = clamp(self.px, b["x1"], b["x2"]); cy = clamp(self.py, b["y1"], b["y2"])
            if dist(self.px, self.py, cx, cy) <= 28:
                money = int(getattr(self.state, "money", 0))
                if money < BARR_REPAIR_COST:
                    messagebox.showwarning("Barricade", f"Need ${BARR_REPAIR_COST} to build/repair.")
                    return
                self.state.money = money - BARR_REPAIR_COST
                if hasattr(self.app, "update_stats"): self.app.update_stats()
                b["hp"] = min(BARR_MAX_HP, b["hp"] + BARR_REPAIR_STEP)
                s = self.canvas.create_rectangle(b["x1"], b["y1"], b["x2"], b["y2"], outline="#fff", width=3, tag="dyn")
                self.after(160, lambda: self.canvas.delete(s))
                return

    # ----- Draw / HUD -----
    def _draw_all(self, hard=False):
        c = self.canvas
        c.delete("dyn")

        wname = WEAPONS[self.weapon_level][0]
        c.itemconfigure(self.hud_text, text=(
            f"Wave {self.wave}   Kills: {self.kills_total}   Lives: {self.lives}   "
            f"HP:{self.hp}/{self.max_hp}   Energy:{int(self.energy)}   Ammo:{getattr(self.state, 'ammo', 0)}   "
            f"Weapon:{wname}   Grenades:{self.grenades}"
        ))

        self._bar(10, 26, 220, 16, self.hp/self.max_hp, COL["hp_bar"], COL["hp_back"])
        self._bar(10, 46, 220, 10, self.energy/ENERGY_MAX, COL["energy"], "#1a2730")

        for b in self.barr.values():
            if b["hp"] <= 0:
                c.create_rectangle(b["x1"], b["y1"], b["x2"], b["y2"], outline="#222", width=1, tag="dyn")
            else:
                c.create_rectangle(b["x1"], b["y1"], b["x2"], b["y2"], fill=COL["barr"], outline="#233247", width=2, tag="dyn")
                length = 40
                bx = (b["x1"] + b["x2"]) / 2 - length/2; by = (b["y1"] + b["y2"]) / 2
                frac = clamp(b["hp"]/BARR_MAX_HP, 0.0, 1.0)
                c.create_rectangle(bx, by-3, bx+length, by+3, fill="#2a2a2a", outline="#000", width=1, tag="dyn")
                c.create_rectangle(bx, by-3, bx+length*frac, by+3, fill="#78a1ff", outline="", tag="dyn")

        c.create_oval(self.px-PLAYER_R, self.py-PLAYER_R, self.px+PLAYER_R, self.py+PLAYER_R,
                      fill=COL["p"], outline="#0b2239", width=2, tag="dyn")
        nx, ny = norm(self.mouse_x - self.px, self.mouse_y - self.py)
        c.create_line(self.px, self.py, self.px + nx*22, self.py + ny*22, fill="#fff", width=2, tag="dyn")

        for z in self.zombies:
            col = COL["z_boss"] if z.get("is_boss") else (COL["z_w"] if z["type"]=="walker" else COL["z_r"] if z["type"]=="runner" else COL["z_b"])
            c.create_oval(z["x"]-Z_R, z["y"]-Z_R, z["x"]+Z_R, z["y"]+Z_R, fill=col, outline="#121212", width=2, tag="dyn")

        for b in self.bullets:
            c.create_oval(b["x"]-BULLET_R, b["y"]-BULLET_R, b["x"]+BULLET_R, b["y"]+BULLET_R,
                          fill=COL["b"], outline="#664", width=1, tag="dyn")

        for g in self.gren_objs:
            c.create_oval(g["x"]-6, g["y"]-6, g["x"]+6, g["y"]+6, fill=COL["gren"], outline="#775", width=2, tag="dyn")

        for p in self.pickups:
            if p["type"] == "ammo":
                c.create_rectangle(p["x"]-6, p["y"]-6, p["x"]+6, p["y"]+6, fill=COL["pickup"], outline="#284e1b", width=2, tag="dyn")
            else:
                c.create_rectangle(p["x"]-6, p["y"]-6, p["x"]+6, p["y"]+6, fill=COL["med"], outline="#6b1b1b", width=2, tag="dyn")

    def _bar(self, x,y,w,h, frac, fg, bg):
        frac = clamp(frac, 0.0, 1.0)
        self.canvas.create_rectangle(x, y, x+w, y+h, fill=bg, outline="#000", width=1, tag="dyn")
        self.canvas.create_rectangle(x, y, x+int(w*frac), y+h, fill=fg, outline="", tag="dyn")

    def _splash(self, text, color="#fff", t=900):
        s = self.canvas.create_text(W/2, H/2, text=text, fill=color,
                                    font=("Segoe UI", 42, "bold"), tag="dyn")
        self.after(t, lambda: self.canvas.delete(s))

    def _sync_up(self):
        try:
            self.state.health = int(self.hp)
            if hasattr(self.app, "update_stats"): self.app.update_stats()
        except Exception:
            pass

    def _commit_highscores_and_exit(self):
        try:
            best_w = int(getattr(self.state, "best_wave", 0))
            best_k = int(getattr(self.state, "best_kills", 0))
            if self.wave-1 > best_w: self.state.best_wave = self.wave-1
            if self.kills_total > best_k: self.state.best_kills = self.kills_total
        except Exception:
            pass
        try: self.destroy()
        except Exception: pass

# space_module.py — SpaceView v7 (ALL FEATURES)
# - Explosions & screen shake
# - Upgrade Shop between boss waves (fire-rate, speed, shields, drone)
# - Town↔Space integration: coins + XP payout on Exit/Game Over
# - Achievements & titles (persist to state.space_achievements)
# - Co-op (same keyboard): P2 = IJKL to move, H fire, U power (shared lives & power)
# - Audio pass: winsound beeps (Windows) or tk bell fallback, pause menu volume slider, M to mute
#
# Controls:
#   P1 Move: WASD/Arrows     P1 Fire: F (hold)     Power Beam: E (when full)
#   P2 Move: I J K L         P2 Fire: H (hold)     Power Beam: U (when full)
#   Pause: P     Sound: M     Exit & cash-out to Town: Esc     Restart: Enter or R
#
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
import time, random, math
from dataclasses import dataclass




# ---------------- Canvas ----------------
CANVAS_W, CANVAS_H = 1280, 720  # keeps your 2× size




# ---------------- Tuning ----------------
BASE_SHIP_SPEED = 18
BULLET_SPEED = 16
BASE_FIRE_COOLDOWN_MS = 80      # fast ROF (shop can reduce further)
WING_BULLET_SPREAD_VX = 3
POWERUP_FALL_SPEED = 4
LEFT_WING_SPAWN_MS  = 4000
RIGHT_WING_SPAWN_MS = 11000




ENEMY_SPAWN_EVERY_MS = 900
ENEMY_SPEED_MIN, ENEMY_SPEED_MAX = 2, 4   # slowed enemies
ENEMY_SCORE = 100
ENEMY_XP = 4




BOSS_KILLS_THRESHOLD = 25
BOSS_BASE_HP = 30
BOSS_HP_PER_WAVE = 12
BOSS_SPEED_X = 4
BOSS_FIRE_EVERY_MS = 900
BOSS_SCORE = 2500
BOSS_XP = 40




RESPAWN_IFRAME_MS = 1500
POWER_MAX = 100
POWER_PER_KILL = 6
POWER_PER_SEC = 2
POWER_BEAM_SPEED = 28
POWER_BEAM_WIDTH = 10




# Shop prices / caps
SHOP_COST_FIRE   = 1500
SHOP_COST_SPEED  = 1500
SHOP_COST_SHIELD = 2000
SHOP_COST_DRONE  = 2200




FIRE_MIN_COOLDOWN = 40   # ms
SPEED_PER_UPGRADE = 2
MAX_SHIELDS = 3




# ---------------- Colors ----------------
COL = {
  "bg": "#050914",
  "ship": "#88e0ff",
  "ship2":"#9DF1A8",
  "ship_core": "#eaffff",
  "bullet": "#ffe082",
  "power_left": "#ff7aa8",
  "power_right": "#9dff7a",
  "enemy": "#ff6b6b",
  "enemy_bullet": "#ffb3b3",
  "boss": "#ff4d4d",
  "hud": "#dfe7fd",
  "hud_dim": "#9fb3d1",
  "hud_warn": "#ffcc66",
  "star_fast": "#cfe8ff",
  "star_slow": "#7aa6cc",
  "beam": "#a0f0ff",
  "explosion": "#ffd27f",
}




# ---------------- Helpers ----------------
def safe_xp(app, amount, source=""):
  try:
      if amount > 0 and hasattr(app, "gain_experience"):
          app.gain_experience(int(amount), source or "Space")
  except Exception:
      pass




def try_beep(freq=800, dur_ms=80, volume=1.0, enabled=True):
  if not enabled or volume <= 0.0: return
  # crude volume gate by duration scaling
  dur_ms = int(max(10, dur_ms * (0.5 + 0.5*volume)))
  try:
      import winsound
      winsound.Beep(int(freq), int(dur_ms))
  except Exception:
      try:
          root = tk._default_root
          if root: root.bell()
      except Exception:
          pass




@dataclass
class Bullet:
  x: float; y: float; vx: float; vy: float; item: int = -1




@dataclass
class PowerUp:
  kind: str; x: float; y: float; vy: float = POWERUP_FALL_SPEED; item: int = -1




@dataclass
class Enemy:
  x: float; y: float; vy: float; item: int = -1




@dataclass
class EnemyShot:
  x: float; y: float; vy: float; item: int = -1




@dataclass
class Boss:
  x: float; y: float; hp: int; dirx: int = 1; last_shot_ms: float = 0.0; item: int = -1




@dataclass
class Particle:
  x: float; y: float; vx: float; vy: float; life: float; item: int = -1




class Starfield:
  def __init__(self, canvas: tk.Canvas, w: int, h: int):
      self.c = canvas; self.w = w; self.h = h
      self.slow = [(random.randint(0,w-1), random.randint(0,h-1)) for _ in range(90)]
      self.fast = [(random.randint(0,w-1), random.randint(0,h-1)) for _ in range(60)]
      self.items_slow = [self.c.create_oval(x, y, x+2, y+2, fill=COL["star_slow"], outline="") for x,y in self.slow]
      self.items_fast = [self.c.create_oval(x, y, x+2, y+2, fill=COL["star_fast"], outline="") for x,y in self.fast]
  def tick(self):
      for i,(x,y) in enumerate(self.slow):
          y += 1;  x = x if y < self.h else random.randint(0, self.w-1)
          y = 0 if y >= self.h else y
          self.slow[i] = (x,y); self.c.coords(self.items_slow[i], x, y, x+2, y+2)
      for i,(x,y) in enumerate(self.fast):
          y += 2;  x = x if y < self.h else random.randint(0, self.w-1)
          y = 0 if y >= self.h else y
          self.fast[i] = (x,y); self.c.coords(self.items_fast[i], x, y, x+2, y+2)




class SpaceView(ttk.Frame):
  """
  Full-featured arcade space mode with co-op, shop, bosses, SFX, and Town cash-out.
  """
  def __init__(self, parent, state, app):
      super().__init__(parent)
      self.state = state
      self.app = app




      try: self.tk.call('tk', 'scaling', 1.0)
      except Exception: pass
      try: self.winfo_toplevel().geometry(f"{CANVAS_W+40}x{CANVAS_H+160}")
      except Exception: pass




      self.canvas = tk.Canvas(self, width=CANVAS_W, height=CANVAS_H,
                              bg=COL["bg"], highlightthickness=1, highlightbackground="#222")
      self.canvas.pack(pady=10)




      # Input
      self.keys = set()
      self.bind_all("<KeyPress>", self._on_keydown)
      self.bind_all("<KeyRelease>", self._on_keyup)




      # Players (shared lives & power)
      self.p1_x = CANVAS_W*0.45; self.p1_y = CANVAS_H*0.8
      self.p1_item = None; self.p1_glow = None
      self.p2_x = CANVAS_W*0.55; self.p2_y = CANVAS_H*0.8
      self.p2_item = None; self.p2_glow = None
      self.p2_active = True  # co-op always available; if you don't touch IJKL/H, it just sits




      # Wings (team-wide)
      self.have_left = False
      self.have_right = False
      self.left_wing_item_p1 = None
      self.right_wing_item_p1 = None
      self.left_wing_item_p2 = None
      self.right_wing_item_p2 = None




      # Ships shared stats
      self.ship_speed = BASE_SHIP_SPEED
      self.fire_cd_ms = BASE_FIRE_COOLDOWN_MS
      self.shields = 0        # prevents life loss on hit, max via shop
      self.drone = False      # extra straight bullet stream
      self.iframes_until = 0.0




      # Audio
      self.sound_enabled = True
      self.volume = 1.0      # 0..1 (beep-gated)
      self._fire_sound_gate = 0




      # Fire / power
      self.p1_firing = False
      self.p2_firing = False
      self.last_shot_ms = 0.0
      self.power = 0.0
      self.last_power_tick = time.time()
      self.beam_items: list[int] = []




      # Entities
      self.bullets: list[Bullet] = []
      self.powerups: list[PowerUp] = []
      self.enemies: list[Enemy] = []
      self.enemy_shots: list[EnemyShot] = []
      self.particles: list[Particle] = []




      # Boss / waves
      self.kills_since_boss = 0
      self.wave_index = 0
      self.boss: Boss | None = None
      self.lives = 10
      self.score = 0
      if not hasattr(self.state, "space_high_score"):
          self.state.space_high_score = 0
      self.high_score = int(getattr(self.state, "space_high_score", 0))
      self.game_over = False
      self.paused = False
      self.shop_open = False




      # Achievements
      if not hasattr(self.state, "space_achievements"):
          self.state.space_achievements = []
      self.achievements: set[str] = set(self.state.space_achievements)
      self._lives_at_boss_spawn = None




      # HUD / overlays
      self.hud_text = self.canvas.create_text(12, 10, anchor="nw",
                                              fill=COL["hud"], font=("Segoe UI", 12, "bold"), text="")
      self.hud_flash_id = None
      self.pause_overlay = None




      # Stars & shake
      self.stars = Starfield(self.canvas, CANVAS_W, CANVAS_H)
      self.shake_ms_left = 0
      self.shake_mag = 0
      self._last_shake_dx = 0
      self._last_shake_dy = 0




      # Timers
      now = time.time()
      self._left_spawn_due  = now + LEFT_WING_SPAWN_MS/1000.0
      self._right_spawn_due = now + RIGHT_WING_SPAWN_MS/1000.0
      self._next_enemy_due  = now + ENEMY_SPAWN_EVERY_MS/1000.0
      self._difficulty_accel = 0




      self._draw_ships()
      self._tick()




  # ---------- Input ----------
  def _on_keydown(self, e):
      k = e.keysym.lower()
      self.keys.add(k)
      if k == "f": self.p1_firing = True
      if k == "h": self.p2_firing = True
      if k == "e": self._try_power_shot()
      if k == "u": self._try_power_shot()
      if k == "m": self.sound_enabled = not self.sound_enabled; self._flash_hud(f"Sound: {'On' if self.sound_enabled else 'Off'}")
      if k == "p": self._toggle_pause()
      if k == "escape": self._exit_to_town()
      if self.game_over and k in ("return", "r"):
          self._restart()




  def _on_keyup(self, e):
      k = e.keysym.lower()
      if k in self.keys: self.keys.remove(k)
      if k == "f": self.p1_firing = False
      if k == "h": self.p2_firing = False




  def _toggle_pause(self):
      if self.game_over or self.shop_open: return
      self.paused = not self.paused
      if self.paused:
          if not self.pause_overlay:
              frm = ttk.Frame(self)
              scale = ttk.Scale(frm, from_=0.0, to=1.0, value=self.volume,
                                command=lambda v: self._set_volume(float(v)))
              ttk.Label(frm, text="Volume").pack(pady=(10,2))
              scale.pack(fill="x", padx=20)
              self.pause_overlay = (
                  self.canvas.create_rectangle(0,0,CANVAS_W,CANVAS_H, fill="#000", stipple="gray50", outline=""),
                  self.canvas.create_window(CANVAS_W//2, CANVAS_H//2, window=frm)
              )
              ttk.Label(frm, text="PAUSED").pack(pady=(16,6))
              ttk.Label(frm, text="P: Resume   •   M: Toggle Sound   •   Enter/R: Restart   •   Esc: Exit & Cash-out").pack()
      else:
          if self.pause_overlay:
              for x in self.pause_overlay:
                  try: self.canvas.delete(x)
                  except Exception: pass
              self.pause_overlay = None




  def _set_volume(self, v: float):
      self.volume = max(0.0, min(1.0, v))




  # ---------- Game loop ----------
  def _tick(self):
      # Starfield and shake always animate
      self.stars.tick()
      self._apply_shake()




      now = time.time()
      if self.paused or self.shop_open:
          self._draw_hud()
          self.after(16, self._tick)
          return




      if not self.game_over:
          # passive power gain
          if now - self.last_power_tick >= 1.0:
              self._add_power(POWER_PER_SEC)
              self.last_power_tick = now




          # movement
          dx1 = (-1 if ("left" in self.keys or "a" in self.keys) else 0) + (1 if ("right" in self.keys or "d" in self.keys) else 0)
          dy1 = (-1 if ("up" in self.keys or "w" in self.keys) else 0) + (1 if ("down" in self.keys or "s" in self.keys) else 0)
          dx2 = (-1 if ("j" in self.keys) else 0) + (1 if ("l" in self.keys) else 0)
          dy2 = (-1 if ("i" in self.keys) else 0) + (1 if ("k" in self.keys) else 0)
          if dx1 or dy1:
              mag = math.hypot(dx1, dy1); pad = 20
              self.p1_x += (dx1/mag)*self.ship_speed if mag else 0
              self.p1_y += (dy1/mag)*self.ship_speed if mag else 0
              self.p1_x = max(pad, min(CANVAS_W-pad, self.p1_x))
              self.p1_y = max(pad, min(CANVAS_H-pad, self.p1_y))
          if self.p2_active and (dx2 or dy2):
              mag = math.hypot(dx2, dy2); pad = 20
              self.p2_x += (dx2/mag)*self.ship_speed if mag else 0
              self.p2_y += (dy2/mag)*self.ship_speed if mag else 0
              self.p2_x = max(pad, min(CANVAS_W-pad, self.p2_x))
              self.p2_y = max(pad, min(CANVAS_H-pad, self.p2_y))




          # shooting
          if (self.p1_firing or self.p2_firing) and (now*1000.0 - self.last_shot_ms) >= self.fire_cd_ms:
              self._fire_team()
              self.last_shot_ms = now*1000.0
              self._fire_sound_gate = (self._fire_sound_gate + 1) % 3
              if self._fire_sound_gate == 0:
                  try_beep(900, 40, self.volume, self.sound_enabled)




          # entities
          self._update_bullets()
          self._update_beams()
          self._update_powerups(now)
          self._update_enemies(now)
          self._update_boss(now)
          self._update_enemy_shots()
          self._update_particles()
          self._check_enemy_ship_collisions(now)




          self._draw_ships()




      self._draw_hud()
      self.after(16, self._tick)




  # ---------- Shake / Explosions / Particles ----------
  def _shake(self, ms=200, mag=8):
      self.shake_ms_left = max(self.shake_ms_left, ms)
      self.shake_mag = max(self.shake_mag, mag)




  def _apply_shake(self):
      # move canvas content by small jitter each frame, revert previous offset first
      if self._last_shake_dx or self._last_shake_dy:
          self.canvas.move(tk.ALL, -self._last_shake_dx, -self._last_shake_dy)
          self._last_shake_dx = self._last_shake_dy = 0
      if self.shake_ms_left > 0:
          self.shake_ms_left -= 16
          dx = random.randint(-self.shake_mag, self.shake_mag)
          dy = random.randint(-self.shake_mag, self.shake_mag)
          self.canvas.move(tk.ALL, dx, dy)
          self._last_shake_dx, self._last_shake_dy = dx, dy




  def _spawn_explosion(self, x: float, y: float, n=10):
      for _ in range(n):
          ang = random.random()*math.tau
          spd = random.uniform(2, 6)
          vx, vy = math.cos(ang)*spd, math.sin(ang)*spd
          item = self.canvas.create_oval(x-2, y-2, x+2, y+2, fill=COL["explosion"], outline="")
          self.particles.append(Particle(x, y, vx, vy, life=0.5 + random.random()*0.4, item=item))
      self._shake(220, 9)




  def _update_particles(self):
      alive: list[Particle] = []
      dt = 16/1000.0
      for p in self.particles:
          p.life -= dt
          if p.life <= 0:
              self.canvas.delete(p.item); continue
          p.x += p.vx; p.y += p.vy
          self.canvas.coords(p.item, p.x-2, p.y-2, p.x+2, p.y+2)
          alive.append(p)
      self.particles = alive




  # ---------- Power / Beams ----------
  def _add_power(self, amt: float):
      self.power = min(POWER_MAX, self.power + amt)




  def _try_power_shot(self):
      if self.game_over or self.paused or self.shop_open: return
      if self.power >= POWER_MAX:
          # beam from BOTH ships (merged into one wide column at their average x)
          x = (self.p1_x + (self.p2_x if self.p2_active else self.p1_x)) / 2
          rect = self.canvas.create_rectangle(x-POWER_BEAM_WIDTH//2, -10, x+POWER_BEAM_WIDTH//2, min(self.p1_y, self.p2_y if self.p2_active else self.p1_y)-26,
                                              fill=COL["beam"], outline="")
          self.beam_items.append(rect)
          self.power = 0.0
          if "Power Technician" not in self.achievements:
              self.achievements.add("Power Technician")
          try_beep(1200, 150, self.volume, self.sound_enabled)




  def _update_beams(self):
      alive = []
      for r in self.beam_items:
          x0,y0,x1,y1 = self.canvas.coords(r)
          y0 -= POWER_BEAM_SPEED
          self.canvas.coords(r, x0, y0, x1, y1)
          if y1 < -20:
              self.canvas.delete(r); continue
          # hits
          killed = []
          for e in self.enemies:
              if x0 <= e.x <= x1:
                  killed.append(e)
          for e in killed:
              try: self.enemies.remove(e)
              except ValueError: pass
              self.canvas.delete(e.item)
              self._on_enemy_killed(e.x, e.y)
          if self.boss is not None:
              bx0,by0,bx1,by1 = self.canvas.bbox(self.boss.item)
              if not (x1 < bx0 or x0 > bx1):
                  self.boss.hp -= 4
                  if self.boss.hp <= 0:
                      self._destroy_boss()
          alive.append(r)
      self.beam_items = alive




  # ---------- Firing ----------
  def _fire_team(self):
      # P1 center + wings + optional drone
      self._spawn_bullet(self.p1_x, self.p1_y - 24, 0, -BULLET_SPEED)
      if self.have_left:  self._spawn_bullet(self.p1_x - 22, self.p1_y - 14, -WING_BULLET_SPREAD_VX, -BULLET_SPEED)
      if self.have_right: self._spawn_bullet(self.p1_x + 22, self.p1_y - 14,  WING_BULLET_SPREAD_VX, -BULLET_SPEED)
      if self.drone:      self._spawn_bullet(self.p1_x, self.p1_y - 28, 0, -BULLET_SPEED-4)




      # P2 if active
      if self.p2_active:
          self._spawn_bullet(self.p2_x, self.p2_y - 24, 0, -BULLET_SPEED)
          if self.have_left:  self._spawn_bullet(self.p2_x - 22, self.p2_y - 14, -WING_BULLET_SPREAD_VX, -BULLET_SPEED)
          if self.have_right: self._spawn_bullet(self.p2_x + 22, self.p2_y - 14,  WING_BULLET_SPREAD_VX, -BULLET_SPEED)
          if self.drone:      self._spawn_bullet(self.p2_x, self.p2_y - 28, 0, -BULLET_SPEED-4)




  def _spawn_bullet(self, x, y, vx, vy):
      item = self.canvas.create_oval(x-3, y-8, x+3, y+2, fill=COL["bullet"], outline="")
      self.bullets.append(Bullet(x, y, vx, vy, item))




  def _update_bullets(self):
      alive: list[Bullet] = []
      for b in self.bullets:
          b.x += b.vx; b.y += b.vy
          if b.y < -20 or b.y > CANVAS_H+20 or b.x < -20 or b.x > CANVAS_W+20:
              self.canvas.delete(b.item); continue
          self.canvas.coords(b.item, b.x-3, b.y-8, b.x+3, b.y+2)
          # hits on enemies
          hit_enemy = None
          for e in self.enemies:
              if (e.x-12 <= b.x <= e.x+12) and (e.y-12 <= b.y <= e.y+8):
                  hit_enemy = e; break
          if hit_enemy is not None:
              self.canvas.delete(b.item)
              try: self.enemies.remove(hit_enemy)
              except ValueError: pass
              self.canvas.delete(hit_enemy.item)
              self._on_enemy_killed(hit_enemy.x, hit_enemy.y)
              continue
          # hit boss
          if self.boss is not None:
              bx0,by0,bx1,by1 = self.canvas.bbox(self.boss.item)
              if (bx0 <= b.x <= bx1) and (by0 <= b.y <= by1):
                  self.canvas.delete(b.item)
                  self.boss.hp -= 1
                  if self.boss.hp <= 0: self._destroy_boss()
                  continue
          alive.append(b)
      self.bullets = alive




  def _on_enemy_killed(self, x, y):
      self.score += ENEMY_SCORE
      self.high_score = max(self.high_score, self.score)
      setattr(self.state, "space_high_score", self.high_score)
      safe_xp(self.app, ENEMY_XP, "Space: Enemy down")
      self.kills_since_boss += 1
      self._add_power(POWER_PER_KILL)
      self._spawn_explosion(x, y, n=8)
      if self.kills_since_boss >= BOSS_KILLS_THRESHOLD and self.boss is None:
          self._spawn_boss()




  # ---------- Power-ups ----------
  def _update_powerups(self, now: float):
      if not self.have_left and now >= self._left_spawn_due and not any(p.kind == "left" for p in self.powerups):
          self._spawn_powerup("left")
      if not self.have_right and now >= self._right_spawn_due and not any(p.kind == "right" for p in self.powerups):
          self._spawn_powerup("right")




      remaining: list[PowerUp] = []
      for p in self.powerups:
          p.y += p.vy
          self.canvas.coords(p.item, p.x-14, p.y-10, p.x+14, p.y+10)
          # pickup if either ship touches
          if (abs(p.x - self.p1_x) < 24 and abs(p.y - self.p1_y) < 24) or \
             (self.p2_active and abs(p.x - self.p2_x) < 24 and abs(p.y - self.p2_y) < 24):
              if p.kind == "left":  self.have_left  = True
              if p.kind == "right": self.have_right = True
              self.canvas.delete(p.item)
              if self.have_left and self.have_right and "Wingman" not in self.achievements:
                  self.achievements.add("Wingman")
              try_beep(600, 90, self.volume, self.sound_enabled)
              self._flash_hud(f"Collected {p.kind.title()} Wing!")
              continue
          if p.y > CANVAS_H + 30:
              self.canvas.delete(p.item); continue
          remaining.append(p)
      self.powerups = remaining




  def _spawn_powerup(self, kind: str):
      x = random.randint(40, CANVAS_W - 40)
      y = -20
      color = COL["power_left"] if kind == "left" else COL["power_right"]
      item = self.canvas.create_rectangle(x-14, y-10, x+14, y+10, fill=color, outline="")
      self.powerups.append(PowerUp(kind, x, y, POWERUP_FALL_SPEED, item))




  # ---------- Enemies ----------
  def _update_enemies(self, now: float):
      if self.boss is None and now >= self._next_enemy_due:
          self._spawn_enemy()
          base = max(480, ENEMY_SPAWN_EVERY_MS - self._difficulty_accel*12)
          self._next_enemy_due = now + base/1000.0
          self._difficulty_accel = min(self._difficulty_accel + 1, 60)




      remaining: list[Enemy] = []
      for e in self.enemies:
          e.y += e.vy
          self.canvas.coords(e.item, e.x, e.y-12, e.x-12, e.y+8, e.x+12, e.y+8)
          if e.y > CANVAS_H + 20:
              self.canvas.delete(e.item)
              self._lose_life()
              continue
          remaining.append(e)
      self.enemies = remaining




  def _spawn_enemy(self):
      x = random.randint(30, CANVAS_W - 30)
      y = -16
      vy = random.randint(ENEMY_SPEED_MIN, ENEMY_SPEED_MAX)
      item = self.canvas.create_polygon(x, y-12, x-12, y+8, x+12, y+8, fill=COL["enemy"], outline="")
      self.enemies.append(Enemy(x, y, vy, item))




  # ---------- Boss ----------
  def _spawn_boss(self):
      self.wave_index += 1
      hp = BOSS_BASE_HP + (self.wave_index-1)*BOSS_HP_PER_WAVE
      item = self.canvas.create_rectangle(CANVAS_W//2-90, 50, CANVAS_W//2+90, 110, fill=COL["boss"], outline="")
      self.boss = Boss(CANVAS_W//2, 80, hp, 1, time.time()*1000.0, item)
      self._lives_at_boss_spawn = self.lives
      try_beep(500, 300, self.volume, self.sound_enabled)
      self._flash_hud(f"Boss Wave {self.wave_index}!", warn=True)




  def _update_boss(self, now: float):
      if self.boss is None: return
      b = self.boss
      b.x += b.dirx * BOSS_SPEED_X
      if b.x < 120: b.x = 120; b.dirx = 1
      if b.x > CANVAS_W-120: b.x = CANVAS_W-120; b.dirx = -1
      self.canvas.coords(b.item, b.x-90, b.y-30, b.x+90, b.y+30)
      if (now*1000.0 - b.last_shot_ms) >= BOSS_FIRE_EVERY_MS:
          b.last_shot_ms = now*1000.0
          for offx in (-60, 0, 60):
              self._spawn_enemy_shot(b.x+offx, b.y+30, vy=6)




  def _destroy_boss(self):
      if self.boss is None: return
      self._spawn_explosion(*self.canvas.coords(self.boss.item)[0:2], n=16)
      self.canvas.delete(self.boss.item)
      self.boss = None
      self.kills_since_boss = 0
      self.score += BOSS_SCORE
      self.high_score = max(self.high_score, self.score)
      setattr(self.state, "space_high_score", self.high_score)
      safe_xp(self.app, BOSS_XP, f"Space: Boss {self.wave_index} down")
      # Achievement: no-hit boss
      if self._lives_at_boss_spawn is not None and self.lives == self._lives_at_boss_spawn:
          self.achievements.add("No-Hit Boss")
      self._flash_hud("Boss defeated! Shop open")
      try_beep(880, 220, self.volume, self.sound_enabled)
      self._open_shop()




  # ---------- Enemy shots ----------
  def _spawn_enemy_shot(self, x: float, y: float, vy: float):
      item = self.canvas.create_oval(x-4, y-4, x+4, y+4, fill=COL["enemy_bullet"], outline="")
      self.enemy_shots.append(EnemyShot(x, y, vy, item))




  def _update_enemy_shots(self):
      alive: list[EnemyShot] = []
      for s in self.enemy_shots:
          s.y += s.vy
          if s.y > CANVAS_H + 16:
              self.canvas.delete(s.item); continue
          self.canvas.coords(s.item, s.x-4, s.y-4, s.x+4, s.y+4)
          if time.time() >= self.iframes_until:
              # hit either ship
              if (abs(s.x - self.p1_x) < 16 and abs(s.y - self.p1_y) < 16) or \
                 (self.p2_active and abs(s.x - self.p2_x) < 16 and abs(s.y - self.p2_y) < 16):
                  self.canvas.delete(s.item)
                  self._lose_life()
                  self.iframes_until = time.time() + RESPAWN_IFRAME_MS/1000.0
                  continue
          alive.append(s)
      self.enemy_shots = alive




  # ---------- Collisions: enemies ↔ ships ----------
  def _check_enemy_ship_collisions(self, now: float):
      if now < self.iframes_until: return
      for e in list(self.enemies):
          if (abs(e.x - self.p1_x) < 18 and abs(e.y - self.p1_y) < 18) or \
             (self.p2_active and abs(e.x - self.p2_x) < 18 and abs(e.y - self.p2_y) < 18):
              try: self.enemies.remove(e)
              except ValueError: pass
              self.canvas.delete(e.item)
              self._lose_life()
              self.iframes_until = now + RESPAWN_IFRAME_MS/1000.0
              break
      if self.boss is not None:
          bx0,by0,bx1,by1 = self.canvas.bbox(self.boss.item)
          if (bx0 <= self.p1_x <= bx1 and by0 <= self.p1_y <= by1) or \
             (self.p2_active and bx0 <= self.p2_x <= bx1 and by0 <= self.p2_y <= by1):
              self._lose_life()
              self.iframes_until = now + RESPAWN_IFRAME_MS/1000.0




  def _lose_life(self):
      if self.lives <= 0 or self.game_over: return
      if self.shields > 0:
          self.shields -= 1
          self._flash_hud(f"Shield! ({self.shields} left)")
          try_beep(700, 90, self.volume, self.sound_enabled)
          self._shake(160, 6)
          return
      self.lives -= 1
      try_beep(300, 180, self.volume, self.sound_enabled)
      self._flash_hud(f"Hit! Lives: {self.lives}", warn=True)
      self._shake(240, 10)
      if self.lives <= 0:
          self._game_over()




  # ---------- Shop ----------
  def _open_shop(self):
      if self.shop_open or self.game_over: return
      self.shop_open = True
      self.paused = True
      win = tk.Toplevel(self)
      win.title("Upgrade Shop — Between Waves")
      win.geometry("420x420+200+120")
      win.transient(self.winfo_toplevel()); win.grab_set()




      lbl = ttk.Label(win, text="Spend score on upgrades (for this run only)", font=("Segoe UI", 11, "bold"))
      lbl.pack(pady=(12,6))
      bal = tk.StringVar(value=f"Score: {self.score}")
      ttk.Label(win, textvariable=bal).pack()




      def buy(cost, action, label):
          if self.score < cost:
              tk.messagebox.showwarning("Shop", f"Need {cost} score for {label}."); return
          action(); self.score -= cost; bal.set(f"Score: {self.score}")
          self.high_score = max(self.high_score, self.score)
          setattr(self.state, "space_high_score", self.high_score)
          self._flash_hud(f"Bought {label}")
          try_beep(650, 90, self.volume, self.sound_enabled)
          self.achievements.add("Mechanic")




      # Fire-rate
      def do_fire():
          self.fire_cd_ms = max(FIRE_MIN_COOLDOWN, self.fire_cd_ms - 10)
      ttk.Button(win, text=f"Fire Rate ↑  (-10ms)  [{SHOP_COST_FIRE}]",
                 command=lambda: buy(SHOP_COST_FIRE, do_fire, "Fire Rate")).pack(fill="x", padx=16, pady=6)




      # Speed
      def do_speed():
          self.ship_speed += SPEED_PER_UPGRADE
      ttk.Button(win, text=f"Speed ↑  (+{SPEED_PER_UPGRADE})  [{SHOP_COST_SPEED}]",
                 command=lambda: buy(SHOP_COST_SPEED, do_speed, "Speed")).pack(fill="x", padx=16, pady=6)




      # Shields
      def do_shield():
          if self.shields >= MAX_SHIELDS:
              tk.messagebox.showinfo("Shop", "Shields already maxed."); return
          self.shields += 1
      ttk.Button(win, text=f"Shield +1 (max {MAX_SHIELDS})  [{SHOP_COST_SHIELD}]",
                 command=lambda: buy(SHOP_COST_SHIELD, do_shield, "Shield")).pack(fill="x", padx=16, pady=6)




      # Drone
      def do_drone():
          self.drone = True
      ttk.Button(win, text=f"Drone (extra gun)  [{SHOP_COST_DRONE}]",
                 command=lambda: buy(SHOP_COST_DRONE, do_drone, "Drone")).pack(fill="x", padx=16, pady=6)




      ttk.Separator(win).pack(fill="x", pady=10)
      ttk.Button(win, text="Resume — Next Wave", command=lambda: close_shop()).pack(pady=8)




      def close_shop():
          if not self.shop_open: return
          self.shop_open = False
          self.paused = False
          try: win.destroy()
          except Exception: pass
          self._flash_hud("Wave continues!")




  # ---------- Town integration ----------
  def _exit_to_town(self):
      # Cash out coins & XP, then close SpaceView
      self._cash_out_to_town(final=True)
      try:
          # close view by destroying its parent frame; App usually swaps views on its own
          self.master.focus_set()
          self.destroy()
      except Exception:
          pass




  def _cash_out_to_town(self, final=False):
      # Coins: simple 10% of score; XP: 1 per 50 score
      coins = self.score // 10
      xp = self.score // 50
      if coins > 0:
          try:
              self.state.money = getattr(self.state, "money", 0) + coins
              if hasattr(self.app, "update_stats"): self.app.update_stats()
          except Exception: pass
      if xp > 0:
          safe_xp(self.app, xp, "Space Cash-out")
      # Persist achievements
      unique = set(self.state.space_achievements) | self.achievements
      self.state.space_achievements = sorted(unique)
      if final:
          self._flash_hud(f"Cashed out → +${coins}, +{xp} XP")




  # ---------- Game over / restart ----------
  def _game_over(self):
      self.game_over = True
      self._cash_out_to_town(final=False)
      self.high_score = max(self.high_score, self.score)
      setattr(self.state, "space_high_score", self.high_score)
      overlay = self.canvas.create_rectangle(0, 0, CANVAS_W, CANVAS_H, fill="#000", stipple="gray50", outline="")
      txt = self.canvas.create_text(
          CANVAS_W//2, CANVAS_H//2-30,
          text=f"GAME OVER\nScore: {self.score}   •   High: {self.high_score}\nCashed out: ${self.score//10}  •  XP: {self.score//50}",
          fill="#fff", font=("Segoe UI", 20, "bold"), justify="center"
      )
      ach_txt = ", ".join(sorted(self.achievements)) if self.achievements else "—"
      txt2 = self.canvas.create_text(
          CANVAS_W//2, CANVAS_H//2+80,
          text=f"Achievements this run: {ach_txt}\n(Enter/R) Restart   •   (Esc) Exit to Town",
          fill="#ddd", font=("Segoe UI", 12), justify="center"
      )
      self._game_over_overlay = (overlay, txt, txt2)




  def _restart(self):
      # Clear overlays
      if hasattr(self, "_game_over_overlay") and self._game_over_overlay:
          for i in self._game_over_overlay:
              try: self.canvas.delete(i)
              except Exception: pass
          self._game_over_overlay = None
      if self.pause_overlay:
          for x in self.pause_overlay:
              try: self.canvas.delete(x)
              except Exception: pass
          self.pause_overlay = None
      self.paused = False; self.shop_open = False; self.game_over = False




      # Reset run state (keep high score + persistent achievements)
      self.score = 0
      self.lives = 10
      self.ship_speed = BASE_SHIP_SPEED
      self.fire_cd_ms = BASE_FIRE_COOLDOWN_MS
      self.shields = 0
      self.drone = False
      self.have_left = False; self.have_right = False
      self.p1_x = CANVAS_W*0.45; self.p1_y = CANVAS_H*0.8
      self.p2_x = CANVAS_W*0.55; self.p2_y = CANVAS_H*0.8
      self.iframes_until = time.time() + 0.8
      self.power = 0.0
      self.kills_since_boss = 0; self.wave_index = 0
      # clear entities
      for it in self.beam_items: self.canvas.delete(it)
      for b in self.bullets: self.canvas.delete(b.item)
      for p in self.powerups: self.canvas.delete(p.item)
      for e in self.enemies: self.canvas.delete(e.item)
      for s in self.enemy_shots: self.canvas.delete(s.item)
      for pr in self.particles: self.canvas.delete(pr.item)
      if self.boss: self.canvas.delete(self.boss.item)
      self.beam_items.clear(); self.bullets.clear(); self.powerups.clear()
      self.enemies.clear(); self.enemy_shots.clear(); self.particles.clear()
      self.boss = None
      now = time.time()
      self._left_spawn_due  = now + LEFT_WING_SPAWN_MS/1000.0
      self._right_spawn_due = now + RIGHT_WING_SPAWN_MS/1000.0
      self._next_enemy_due  = now + ENEMY_SPAWN_EVERY_MS/1000.0
      self._difficulty_accel = 0
      self._draw_ships()
      self._flash_hud("Ready!", warn=False)




  # ---------- Rendering ----------
  def _draw_ships(self):
      # P1
      sx, sy = self.p1_x, self.p1_y
      tri = [sx, sy-22, sx-16, sy+14, sx+16, sy+14]
      if self.p1_item is None:
          self.p1_item = self.canvas.create_polygon(tri, fill=COL["ship"], outline="")
      else:
          self.canvas.coords(self.p1_item, *tri)
      if time.time() < self.iframes_until and (int(time.time()*10) % 2 == 0):
          self.canvas.itemconfigure(self.p1_item, fill="#587e91")
      else:
          self.canvas.itemconfigure(self.p1_item, fill=COL["ship"])
      if self.p1_glow is None:
          self.p1_glow = self.canvas.create_oval(sx-5, sy-9, sx+5, sy+1, fill=COL["ship_core"], outline="")
      else:
          self.canvas.coords(self.p1_glow, sx-5, sy-9, sx+5, sy+1)




      # P1 pods
      if self.have_left:
          if self.left_wing_item_p1 is None:
              self.left_wing_item_p1 = self.canvas.create_rectangle(sx-28, sy-7, sx-20, sy+7, fill=COL["power_left"], outline="")
          else:
              self.canvas.coords(self.left_wing_item_p1, sx-28, sy-7, sx-20, sy+7)
      else:
          if self.left_wing_item_p1 is not None:
              self.canvas.delete(self.left_wing_item_p1); self.left_wing_item_p1 = None
      if self.have_right:
          if self.right_wing_item_p1 is None:
              self.right_wing_item_p1 = self.canvas.create_rectangle(sx+20, sy-7, sx+28, sy+7, fill=COL["power_right"], outline="")
          else:
              self.canvas.coords(self.right_wing_item_p1, sx+20, sy-7, sx+28, sy+7)
      else:
          if self.right_wing_item_p1 is not None:
              self.canvas.delete(self.right_wing_item_p1); self.right_wing_item_p1 = None




      # P2
      if self.p2_active:
          sx2, sy2 = self.p2_x, self.p2_y
          tri2 = [sx2, sy2-22, sx2-16, sy2+14, sx2+16, sy2+14]
          if self.p2_item is None:
              self.p2_item = self.canvas.create_polygon(tri2, fill=COL["ship2"], outline="")
          else:
              self.canvas.coords(self.p2_item, *tri2)
          if self.p2_glow is None:
              self.p2_glow = self.canvas.create_oval(sx2-5, sy2-9, sx2+5, sy2+1, fill=COL["ship_core"], outline="")
          else:
              self.canvas.coords(self.p2_glow, sx2-5, sy2-9, sx2+5, sy2+1)




          # P2 pods
          if self.have_left:
              if self.left_wing_item_p2 is None:
                  self.left_wing_item_p2 = self.canvas.create_rectangle(sx2-28, sy2-7, sx2-20, sy2+7, fill=COL["power_left"], outline="")
              else:
                  self.canvas.coords(self.left_wing_item_p2, sx2-28, sy2-7, sx2-20, sy2+7)
          else:
              if self.left_wing_item_p2 is not None:
                  self.canvas.delete(self.left_wing_item_p2); self.left_wing_item_p2 = None
          if self.have_right:
              if self.right_wing_item_p2 is None:
                  self.right_wing_item_p2 = self.canvas.create_rectangle(sx2+20, sy2-7, sx2+28, sy2+7, fill=COL["power_right"], outline="")
              else:
                  self.canvas.coords(self.right_wing_item_p2, sx2+20, sy2-7, sx2+28, sy2+7)
          else:
              if self.right_wing_item_p2 is not None:
                  self.canvas.delete(self.right_wing_item_p2); self.right_wing_item_p2 = None




      # Boss HP bar
      if self.boss is not None:
          b = self.boss
          bx0,by0,bx1,by1 = self.canvas.bbox(b.item)
          full_hp = (BOSS_BASE_HP + (self.wave_index-1)*BOSS_HP_PER_WAVE)
          hp_ratio = max(0.0, min(1.0, b.hp / full_hp))
          bar_w = (bx1-bx0)
          self.canvas.create_rectangle(bx0, by0-12, bx1, by0-6, fill="#333", outline="")
          self.canvas.create_rectangle(bx0, by0-12, bx0 + bar_w*hp_ratio, by0-6, fill="#ff6666", outline="")




  def _draw_hud(self):
      wings = ("L" if self.have_left else "-") + "|" + ("R" if self.have_right else "-")
      pfull = "READY" if self.power >= POWER_MAX else f"{int(self.power)}%"
      snd = "On" if self.sound_enabled and self.volume > 0 else "Off"
      # notable achievements live
      maybe = []
      if "No-Hit Boss" in self.achievements: maybe.append("No-Hit Boss")
      if "Wingman" in self.achievements: maybe.append("Wingman")
      if "Power Technician" in self.achievements: maybe.append("PowerTech")
      if "Mechanic" in self.achievements: maybe.append("Mechanic")
      ach = (" • Achv: " + ",".join(maybe)) if maybe else ""
      text = (f"P1: WASD/F/E  •  P2: IJKL/H/U  •  P: Pause  •  M: Sound {snd}  •  Esc: Exit & Cash-out{ach}\n"
              f"Wings: {wings}  •  Lives: {self.lives}  •  Shields: {self.shields}  •  Score: {self.score}  •  High: {self.high_score}  •  Power: {pfull}")
      self.canvas.itemconfigure(self.hud_text, text=text)




  def _flash_hud(self, msg: str, warn: bool=False, ms: int=900):
      if self.hud_flash_id:
          try: self.canvas.delete(self.hud_flash_id)
          except Exception: pass
          self.hud_flash_id = None
      t = self.canvas.create_text(
          CANVAS_W - 8, 8, anchor="ne", fill=(COL["hud_warn"] if warn else COL["hud_dim"]),
          font=("Segoe UI", 12, "bold"), text=msg
      )
      self.hud_flash_id = t
      def fade(step=0):
          if step >= 10:
              try: self.canvas.delete(t)
              except Exception: pass
              if self.hud_flash_id == t: self.hud_flash_id = None
              return
          self.after(ms//10, lambda: fade(step+1))
      fade()









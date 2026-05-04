"""
town_racetrack_module.py — 4-lane Racetrack (Tkinter)
Players:
 P1: W/S lane up/down, A/D fine left/right, Left Shift = boost
 P2: Up/Down lane up/down, Left/Right fine left/right, Space = boost
AI: 2 cars. Pickups: green boost, red slow.
"""
import tkinter as tk
from tkinter import ttk
import random, time


W, H = 960, 540
LANE_COUNT = 4
LANE_H = 90
TRACK_Y0 = 80
FINISH_X = 2100
FPS = 60


class Car:
   def __init__(self, color, lane, is_ai=False, keys=None):
       self.color = color
       self.lane = lane
       self.x = 120
       self.w = 56; self.h = 30
       self.base_speed = 3.2
       self.boost = 0.0
       self.slow = 0.0
       self.cooldown = 0.0
       self.is_ai = is_ai
       self.keys = keys or {}


   def y(self):
       return TRACK_Y0 + self.lane*LANE_H + (LANE_H-self.h)//2


   def rect(self):
       return (self.x, self.y(), self.x+self.w, self.y()+self.h)


   def speed_now(self):
       s = self.base_speed
       if self.boost > 0: s += 2.4
       if self.slow > 0: s -= 1.2
       return max(1.2, s)


class Pickup:
   def __init__(self, lane, kind, x):
       self.lane = lane
       self.kind = kind  # "boost" or "slow"
       self.x = x
       self.w = 20; self.h = 20
   def rect(self):
       y = TRACK_Y0 + self.lane*LANE_H + (LANE_H-self.h)//2
       return (self.x, y, self.x+self.w, y+self.h)


class RaceTrackView(ttk.Frame):
   def __init__(self, parent, state, app):
       super().__init__(parent)
       self.state = state
       self.app = app


       self.canvas = tk.Canvas(self, width=W, height=H, bg="#226622", highlightthickness=1, highlightbackground="#1e1e1e")
       self.canvas.pack(pady=10)


       self.keys = set()
       self.canvas.bind("<KeyPress>", self._on_keydown)
       self.canvas.bind("<KeyRelease>", self._on_keyup)
       self.canvas.focus_set()


       self.cars = [
           Car("#ff8a8a", 0, is_ai=False, keys={"up":"w","down":"s","left":"a","right":"d","boost":"shift_l"}),
           Car("#8ecbff", 3, is_ai=False, keys={"up":"up","down":"down","left":"left","right":"right","boost":"space"}),
           Car("#d8bb55", 1, is_ai=True),
           Car("#7ed7a3", 2, is_ai=True),
       ]
       self.pickups = []
       self.spawn_cd = 0.0
       self.winner = None


       self._last = time.time()
       self._tick()


   def _on_keydown(self, e): self.keys.add(e.keysym.lower())
   def _on_keyup(self, e): self.keys.discard(e.keysym.lower())


   def _tick(self):
       now = time.time()
       dt = max(0.001, min(0.05, now - self._last)); self._last = now


       # Spawn pickups
       self.spawn_cd -= dt
       if self.spawn_cd <= 0:
           lane = random.randint(0, LANE_COUNT-1)
           kind = "boost" if random.random() < 0.55 else "slow"
           x = random.randint(420, 1800)
           self.pickups.append(Pickup(lane, kind, x))
           self.spawn_cd = random.uniform(0.6, 1.2)


       # Update cars
       for i, car in enumerate(self.cars):
           car.cooldown = max(0.0, car.cooldown - dt)
           car.boost = max(0.0, car.boost - dt)
           car.slow = max(0.0, car.slow - dt)


           if car.is_ai:
               # simple lane jitter + random boost
               if random.random() < 0.02:
                   car.lane = max(0, min(LANE_COUNT-1, car.lane + random.choice([-1,1])))
               if random.random() < 0.01 and car.cooldown <= 0:
                   car.boost = 0.8; car.cooldown = 0.9
           else:
               up = car.keys["up"] in self.keys
               down = car.keys["down"] in self.keys
               left = car.keys["left"] in self.keys
               right = car.keys["right"] in self.keys
               boost = car.keys["boost"] in self.keys
               if up and car.lane > 0: car.lane -= 1
               if down and car.lane < LANE_COUNT-1: car.lane += 1
               if left: car.x -= 180*dt
               if right: car.x += 180*dt
               if boost and car.cooldown <= 0:
                   car.boost = 0.7; car.cooldown = 0.9


           car.x += car.speed_now() * 60 * dt  # logical speed → px/s


       # Collisions with pickups
       for car in self.cars:
           cx1, cy1, cx2, cy2 = car.rect()
           for p in list(self.pickups):
               px1, py1, px2, py2 = p.rect()
               if (cx1 < px2 and cx2 > px1 and cy1 < py2 and cy2 > py1):
                   if p.kind == "boost": car.boost = 1.0
                   else:                 car.slow  = 1.0
                   self.pickups.remove(p)


       # Winner
       if self.winner is None:
           for idx, car in enumerate(self.cars):
               if car.x >= FINISH_X:
                   self.winner = idx


       self._draw()
       self.after(int(1000/FPS), self._tick)


   def _draw(self):
       c = self.canvas; c.delete("all")
       # Track
       c.create_rectangle(0, TRACK_Y0-20, W, TRACK_Y0 + LANE_COUNT*LANE_H + 20, fill="#505050", outline="")
       for i in range(LANE_COUNT+1):
           y = TRACK_Y0 + i*LANE_H
           c.create_line(0, y, W, y, fill="#dcdcdc", width=2)
       c.create_line(W-60, TRACK_Y0-20, W-60, TRACK_Y0 + LANE_COUNT*LANE_H + 20, fill="#ffffff", width=6)


       # Pickups
       for p in self.pickups:
           x1,y1,x2,y2 = p.rect()
           col = "#33cc33" if p.kind == "boost" else "#cc3333"
           c.create_rectangle(x1, y1, x2, y2, fill=col, outline="#111111")


       # Cars
       for car in self.cars:
           x1,y1,x2,y2 = car.rect()
           c.create_rectangle(x1, y1, x2, y2, fill=car.color, outline="#141414")


       # Winner banner
       if self.winner is not None:
           c.create_text(40, 28, anchor="w", text=f"Car #{self.winner+1} wins!  (Switch views to restart)",
                         fill="#ffffff", font=("Segoe UI", 16, "bold"))


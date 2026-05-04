"""
Town & Space — v6 "ChronoFusion"
- Six separate towns (Classic, Frontier/Zombies, Putt Putt Golf, Duel Dome Soccer, Future Town, Race Track)
- Space view (Space module)
- Global clock/calendar/season (in status bar) available to every module
- Preserves global XP/Level, money, intelligence, strength, energy, inventory, car/ship, etc.


Run:  python game_main.py
"""


import tkinter as tk
from tkinter import ttk, messagebox
from dataclasses import dataclass, field
import json, os, sys, importlib.util
from pathlib import Path


# ---- Robust local import helper (compatible with TownV2/V5 style) ----
def _safe_import(name: str, filename: str):
   try:
       return __import__(name)
   except ModuleNotFoundError:
       base = Path(__file__).resolve().parent
       path = base / filename
       if not path.exists():
           raise ModuleNotFoundError(f"Could not find '{name}'. Expected file at: {path}")
       spec = importlib.util.spec_from_file_location(name, path)
       if spec is None or spec.loader is None:
           raise ImportError(f"Could not load spec for '{name}' from {path}")
       mod = importlib.util.module_from_spec(spec)
       sys.modules[name] = mod
       spec.loader.exec_module(mod)
       return mod


# Existing modules (kept intact)
town_module         = _safe_import("town_module", "town_module.py")                 # Classic Town
space_module        = _safe_import("space_module", "space_module.py")               # Space
town_zombies_module = _safe_import("town_zombies_module", "town_zombies_module.py") # Frontier (Zombies)
town_golf_module    = _safe_import("town_golf_module", "town_golf_module.py")       # Putt Putt
town_soccer_module  = _safe_import("town_soccer_module", "town_soccer_module.py")   # Duel Dome (Soccer)


# New additive modules
chrono              = _safe_import("chrono", "chrono.py")                           # Clock/Calendar/Season
overlay_weather     = _safe_import("overlay_weather", "overlay_weather.py")         # Seasonal overlay for Classic
future_town_module  = _safe_import("future_town_module", "future_town_module.py")   # Future Town (3D-ish)
racetrack_module    = _safe_import("town_racetrack_module", "town_racetrack_module.py")  # 4-lane race


SAVE_FILE = "savefile.json"


@dataclass
class GameState:
   # Core stats
   money: int = 1000
   intelligence: int = 0
   strength: int = 0
   energy: int = 100
   inventory: dict = field(default_factory=lambda: {"coffee": 0})
   has_spaceship: bool = False


   # Vehicle
   has_car: bool = False
   car_equipped: bool = False


   # Town player position (grid coords)
   town_x: int = 5
   town_y: int = 5
   town_area: int = 0  # 0=Main, 1=South District


   # Space ship position (pixels)
   ship_x: int = 200
   ship_y: int = 160


   # Combat / zombies
   weapon: str = "None"
   ammo: int = 0
   health: int = 100
   kills: int = 0


   # Golf
   golf_balls: int = 0
   golf_has_club: bool = False
   golf_current_hole: int = 1
   golf_strokes: int = 0


   # Soccer
   soccer_score_p1: int = 0
   soccer_score_p2: int = 0


   # Global XP / Level (preserved from v5+ style)
   experience: int = 0
   level: int = 1


   def to_dict(self):
       return self.__dict__


   @classmethod
   def from_dict(cls, d):
       gs = cls()
       for k, v in d.items():
           if hasattr(gs, k):
               setattr(gs, k, v)
       return gs


# XP thresholds: simple curve (100, 200, 300, ...)
def required_xp_for_level(level: int) -> int:
   return 100 * level


class App(tk.Tk):
   """Main window that swaps between 6 Towns + Space."""
   def __init__(self):
       super().__init__()
       self.title("Town & Space — v6 ChronoFusion")
       self.geometry("1000x720")
       self.resizable(False, False)


       self.state = GameState()
       self.current_view = None


       # Top status bar
       self.stats_var = tk.StringVar()
       self._build_menu()
       self._build_status()


       # Content area (where views go)
       self.content = ttk.Frame(self, padding=8)
       self.content.pack(fill="both", expand=True)


       # Global clock/calendar/season ticker
       self._last_clock_t = None
       self._tick_clock()


       # Start in Classic Town
       self.show_town_classic()


       # Apply a nicer ttk theme if available
       try:
           style = ttk.Style()
           if "vista" in style.theme_names():
               style.theme_use("vista")
       except Exception:
           pass


   # ---------- Clock/Season ticker ----------
   def _tick_clock(self):
       import time
       now = time.time()
       if self._last_clock_t is None:
           self._last_clock_t = now
       dt = max(0.001, min(0.1, now - self._last_clock_t))
       self._last_clock_t = now
       chrono.manager.tick(dt)


       # augment status bar with time/date/season
       try:
           base = self._base_stats_text()
           self.stats_var.set(f"{base}   |   {chrono.hud_text()}")
       except Exception:
           pass


       self.after(250, self._tick_clock)  # refresh ~4x/sec


   # ---------- XP / Level helpers ----------
   def gain_experience(self, amount: int, source: str = ""):
       if amount <= 0:
           return
       self.state.experience += amount
       leveled = False
       while self.state.experience >= required_xp_for_level(self.state.level):
           self.state.experience -= required_xp_for_level(self.state.level)
           self.state.level += 1
           leveled = True
       self.update_stats()
       if leveled:
           messagebox.showinfo("Level Up!", f"You reached Level {self.state.level}!")


   # ---------- UI Shell ----------
   def _build_menu(self):
       menubar = tk.Menu(self)


       game_menu = tk.Menu(menubar, tearoff=0)
       game_menu.add_command(label="Save", command=self.save_game)
       game_menu.add_command(label="Load", command=self.load_game)
       game_menu.add_separator()
       game_menu.add_command(label="Quit", command=self.destroy)
       menubar.add_cascade(label="Game", menu=game_menu)


       town_menu = tk.Menu(menubar, tearoff=0)
       town_menu.add_command(label="Classic Town", command=self.show_town_classic)
       town_menu.add_command(label="Frontier Town (Zombies)", command=self.show_town_zombies)
       town_menu.add_command(label="Putt Putt Park (Golf)", command=self.show_town_golf)
       town_menu.add_command(label="Duel Dome (Soccer)", command=self.show_town_soccer)
       town_menu.add_command(label="Future Town", command=self.show_town_future)
       town_menu.add_command(label="Race Track (2P + 2 AI)", command=self.show_town_racetrack)
       menubar.add_cascade(label="Towns", menu=town_menu)


       view_menu = tk.Menu(menubar, tearoff=0)
       view_menu.add_command(label="Go to Space", command=self.show_space)
       menubar.add_cascade(label="View", menu=view_menu)


       help_menu = tk.Menu(menubar, tearoff=0)
       help_menu.add_command(label="Controls", command=self.show_controls)
       help_menu.add_command(label="About", command=lambda: messagebox.showinfo(
           "About", "Town & Space — v6 ChronoFusion\nGlobal XP/Level + Time/Season."))
       menubar.add_cascade(label="Help", menu=help_menu)


       self.config(menu=menubar)


   def _build_status(self):
       bar = ttk.Frame(self, padding=(8, 4))
       bar.pack(fill="x", side="top")
       ttk.Label(bar, textvariable=self.stats_var, font=("Segoe UI", 10, "bold")).pack(anchor="w")
       self.update_stats()


   def _base_stats_text(self):
       car = "On" if self.state.car_equipped else ("Owned" if self.state.has_car else "No")
       return (
           f"Lvl {self.state.level}  XP:{self.state.experience}/{required_xp_for_level(self.state.level)}   "
           f"Money:${self.state.money}  INT:{self.state.intelligence}  STR:{self.state.strength}   "
           f"Energy:{self.state.energy}  Coffee:{self.state.inventory.get('coffee',0)}   "
           f"Ship:{'Yes' if self.state.has_spaceship else 'No'}  Car:{car}"
       )


   def update_stats(self):
       # rebuild core stats; clock/season appended in ticker
       self.stats_var.set(self._base_stats_text())


   def show_controls(self):
       messagebox.showinfo(
           "Controls",
           "Global: Save/Load from menu.\n"
           "\nClassic Town: Arrow/WASD to move. Enter to interact. 'C' to toggle car (once owned)."
           "\nFrontier (Zombies): Move WASD/Arrows, F to shoot. Earn money + XP per kill."
           "\nPutt Putt Park: Left/Right aim, Space hit. Sink to unlock next hole + XP."
           "\nDuel Dome (Soccer): P1 WASD + E shoot; P2 Arrows + Space shoot."
           "\nFuture Town: WASD/Arrows to roam parallax city."
           "\nRace Track: P1 W/S lanes + A/D nudge + Left Shift boost; P2 Up/Down lanes + Left/Right nudge + Space boost."
           "\nSpace: Fly WASD/Arrows; Enter on pads to start missions (Defense: F to shoot, XP per alien wave)."
       )


   # ---------- View Swapping ----------
   def _swap_view(self, new_view_cls):
       if self.current_view is not None:
           try:
               # turn off seasonal overlay when leaving Classic
               overlay_weather.disable()
           except Exception:
               pass
           self.current_view.destroy()
           self.current_view = None
       self.current_view = new_view_cls(self.content, self.state, self)
       self.current_view.pack(fill="both", expand=True)
       self.update_stats()


   def show_town_classic(self):
       self._swap_view(town_module.TownView)
       # Seasonal overlay only in Classic
       try:
           overlay_weather.enable(self.content, lambda: chrono.manager.time and ["Winter","Spring","Summer","Fall"][chrono.manager.time.season_index])
       except Exception:
           pass


   def show_town_zombies(self):  self._swap_view(town_zombies_module.TownZombiesView)
   def show_town_golf(self):     self._swap_view(town_golf_module.TownGolfView)
   def show_town_soccer(self):   self._swap_view(town_soccer_module.TownSoccerView)
   def show_town_future(self):   self._swap_view(future_town_module.FutureTownView)
   def show_town_racetrack(self):self._swap_view(racetrack_module.RaceTrackView)
   def show_space(self):         self._swap_view(space_module.SpaceView)


   # ---------- Persistence ----------
   def save_game(self):
       try:
           with open(SAVE_FILE, "w", encoding="utf-8") as f:
               json.dump(self.state.to_dict(), f, indent=2)
           messagebox.showinfo("Saved", f"Game saved to {os.path.abspath(SAVE_FILE)}")
       except Exception as e:
           messagebox.showerror("Save Failed", f"Could not save game:\n{e}")


   def load_game(self):
       if not os.path.exists(SAVE_FILE):
           messagebox.showinfo("Load", "No save file found.")
           return
       try:
           with open(SAVE_FILE, "r", encoding="utf-8") as f:
               data = json.load(f)
           self.state = GameState.from_dict(data)
           self.show_town_classic()
           messagebox.showinfo("Loaded", "Save loaded.")
       except Exception as e:
           messagebox.showerror("Load Failed", f"Could not load game:\n{e}")


if __name__ == "__main__":
   App().mainloop()



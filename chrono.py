"""
chrono.py — Global clock/calendar/season for Town (Tkinter)
Other modules can:  import chrono ;  read chrono.manager.time ;  show chrono.hud_text()
"""
from dataclasses import dataclass


SEASONS = ["Winter", "Spring", "Summer", "Fall"]


@dataclass
class GameTime:
   day: int = 1
   month: int = 1
   year: int = 1
   hour: int = 8
   minute: int = 0
   season_index: int = 0


   def __str__(self) -> str:
       ampm = "AM" if self.hour < 12 else "PM"
       h12 = self.hour % 12 or 12
       return f"{h12:02d}:{self.minute:02d} {ampm}  •  Y{self.year} M{self.month} D{self.day}  •  {SEASONS[self.season_index]}"


class TimeManager:
   """Advance in-game minutes every tick; ~6 minutes per real second @60fps by default."""
   def __init__(self, minutes_per_real_second: float = 6.0, target_fps: float = 60.0):
       self.minutes_per_real_second = minutes_per_real_second
       self.target_fps = target_fps
       self._accum = 0.0
       self.time = GameTime()


   def tick(self, dt_seconds: float):
       self._accum += dt_seconds * self.minutes_per_real_second
       while self._accum >= 1.0:
           self._advance_minute()
           self._accum -= 1.0


   def _advance_minute(self):
       t = self.time
       t.minute += 1
       if t.minute >= 60:
           t.minute = 0
           t.hour += 1
       if t.hour >= 24:
           t.hour = 0
           t.day += 1
           if t.day > 30:
               t.day = 1
               t.month += 1
               if t.month > 12:
                   t.month = 1
                   t.year += 1
           # rotate seasons on months: 1→Winter, 4→Spring, 7→Summer, 10→Fall
           if t.month in (1,4,7,10):
               t.season_index = {1:0,4:1,7:2,10:3}[t.month]


   def hud_string(self) -> str:
       return str(self.time)


# Singleton-style
manager = TimeManager()


def hud_text() -> str:
   return manager.hud_string()


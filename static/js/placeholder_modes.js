const PlaceholderModes = {
  town: createPlaceholderMode(
    "Classic Town",
    "#134629",
    "Classic Town hub will be converted here next. Use this as the main world map."
  ),

  space: createPlaceholderMode(
    "Space",
    "#05051f",
    "Space module will go here: ship movement, missions, alien defense."
  ),

  zombies: createPlaceholderMode(
    "Frontier Town Zombies",
    "#2b2418",
    "Zombies module will go here: weapons, ammo, enemies, kills."
  ),

  golf: createPlaceholderMode(
    "Putt Putt Park",
    "#1d5c2f",
    "Golf module will go here: aiming, holes, strokes, club, balls."
  ),

  soccer: createPlaceholderMode(
    "Duel Dome Soccer",
    "#103f5f",
    "Soccer module will go here: two players, ball physics, scoring."
  )
};

function createPlaceholderMode(title, bg, message) {
  return {
    start() {
      helpText.textContent = message;
      this.draw();
    },

    stop() {},

    draw() {
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      ctx.fillStyle = "white";
      ctx.font = "bold 42px Arial";
      ctx.fillText(title, 60, 90);

      ctx.font = "20px Arial";
      ctx.fillText(message, 60, 140);

      ctx.font = "16px Arial";
      ctx.fillText("This module is connected to the launcher but not fully ported yet.", 60, 190);
    }
  };
}
---
key: +weather
title: +Weather — Local Time and Weather
category: "Commands: World"
summary: Show the local time of day and any active weather affecting the area.
aliases: [+time, weather]
see_also: [+threat, look, +region]
tags: [weather, time, environment, command]
access_level: 0
examples:
  - cmd: "+weather"
    description: "Show local time and any active weather."
  - cmd: "+time"
    description: "Alias — same as +weather."
  - cmd: "weather"
    description: "Short alias."
---

Show the local time of day (in the planet's own idiom where one
exists) and any active weather that is affecting your location.

SYNTAX

  +weather
  +time
  weather

OUTPUT (TATOOINE EXAMPLE)

  Local time: Second Twilight
  Active weather: Sandstorm — Severe
    Perception penalty: -2D
    Ranged fire penalty: -2D

OUTPUT (CORUSCANT EXAMPLE)

  Local time: Late Evening
  No active weather.

TIME VOCABULARY

  Some planets use their own time idioms instead of standard
  galactic 24-hour notation:

  Tatooine    First Dawn · High Sun · Second Twilight · Night Cycle
              (keyed to its twin suns)
  Other planets use standard galactic time if no idiom is defined.

WEATHER EFFECTS

  Active storms impose penalties to dice rolls:

  Sandstorm         Reduces Perception and ranged attack pools.
  Gravel Storm      Similar to sandstorm — heavy particles in the air.
  Sandwhirl (minor) Light penalty; mostly atmospheric.

  Penalties are listed in D6 notation (e.g. -2D Perception).
  Weather clears automatically when the world event expires.

SEE ALSO

  +threat    Show the danger level of the current area.
  look       Room description often includes weather atmosphere.
  +region    Regional information including planet type.

EXAMPLES

  +weather
  → "Local time: High Sun | Active weather: Sandstorm — Severe"

  +weather (in a calm area)
  → "Local time: Late Evening | No active weather."

CHEAT SHEET
  +weather / +time / weather   = local time + weather conditions

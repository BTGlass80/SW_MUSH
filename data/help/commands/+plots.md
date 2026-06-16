---
key: +plots
title: +Plots — List Story Arcs
category: "Commands: Social"
summary: List open story arcs and plots. Create, link, and manage collaborative storylines.
aliases: ["+plot/list", "+arcs", "+plot"]
see_also: [+plot, +scene, +scenes, +events]
tags: [plots, story, arcs, roleplay, social, command]
access_level: 0
examples:
  - cmd: "+plots"
    description: "List all open story arcs."
  - cmd: "+plot 3"
    description: "View the details and linked scenes for plot #3."
  - cmd: "+plot/create The Missing Cargo=Shipment vanished near Nar Shaddaa"
    description: "Create a new plot arc."
---

List, view, and manage collaborative story arcs. Plots track
ongoing storylines and link them to scenes for narrative continuity.

SYNTAX

  +plots                               List all open plots
  +plot <id>                           View plot details and linked scenes
  +plot/create <title>=<summary>       Start a new plot
  +plot/summary <id>=<text>            Update the summary of a plot
  +plot/link <plot_id>=<scene_id>      Link a scene to a plot
  +plot/unlink <plot_id>=<scene_id>    Remove a scene from a plot
  +plot/close <id>                     Mark a plot complete
  +plot/reopen <id>                    Reopen a closed plot

WHAT IS A PLOT?

  A plot is a named story arc that groups related scenes together.
  Any player can create a plot. Scenes logged via +scene can be
  linked to one or more plots, building a persistent record of
  your storylines.

  Plots appear in +plots in chronological order. Each shows the
  creator, scene count, and a brief summary.

EXAMPLES

  +plots
  → Shows all open arcs: title, status, scene count, last update.

  +plot 5
  → Full detail: summary, creator, all linked scenes.

  +plot/create Espionage on Mandalore=Undercover mission for the Senate
  → Creates "Espionage on Mandalore" with that summary.

  +plot/link 5=12
  → Links scene #12 to plot #5.

  +plot/close 5
  → Closes the arc when the story concludes.

SEE ALSO

  +scene    Log a new scene.
  +scenes   Browse logged scenes.

CHEAT SHEET
  +plots                           list open arcs
  +plot <id>                       view arc detail
  +plot/create <title>=<summary>   start a new arc
  +plot/link <arc>=<scene>         link a scene
  +plot/close <id>                 close completed arc

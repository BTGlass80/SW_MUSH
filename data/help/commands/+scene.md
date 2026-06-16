---
key: +scene
title: +Scene — Scene Logging
category: "Commands: RP"
summary: Start, stop, and manage scene logs. Every IC pose in an active scene is archived with a timestamp.
aliases: [scene]
see_also: [+scenes, emote, say, +who]
tags: [scene, rp, logging, roleplay, command]
access_level: 0
examples:
  - cmd: "+scene/start The Cantina Deal"
    description: "Start a scene titled 'The Cantina Deal' in the current room."
  - cmd: "+scene"
    description: "Show the active scene's info in the current room."
  - cmd: "+scene 14"
    description: "View the pose log for scene #14."
  - cmd: "+scene/stop"
    description: "End the active scene and finalize the log."
  - cmd: "+scene/share 14"
    description: "Make scene #14 public in the archive."
---

Record and archive roleplay sessions. When a scene is active in a
room, every IC pose (emote, say, whisper) is logged automatically
with a timestamp. Scenes can be titled, typed, summarized, and
shared publicly when complete.

SYNTAX

  +scene                      Show active scene info (current room)
  +scene <id>                 View the log for a specific scene
  +scene/start [title]        Start a scene here (optional title)
  +scene/stop                 End the active scene
  +scene/title <text>         Rename the active scene
  +scene/type <type>          Set scene type (see TYPES below)
  +scene/summary <text>       Write a brief summary for the archive
  +scene/share [id]           Publish scene to the public archive
  +scene/unshare [id]         Revert a published scene to private
  +scene/poseorder            Start or view the pose-order tracker
  +scene/drop <name>          Remove someone from the pose rotation
  +scene/mode <mode>          Set pose-order mode (round-robin / 3-per)
  +scenes                     List all your recent scenes

TYPES

  Social     Conversation, downtime, character interaction
  Action     Combat, chase, crisis — high tension
  Plot       Staff-run or plot-driven scene
  Vignette   Solo or brief out-of-the-way moment

LOGGING

  An active scene captures every IC line (say, emote, whisper) sent
  while in the scene's room. Scene logger includes timestamps and
  the room name. System messages (combat results, etc.) are not logged.

POSE ORDER

  +scene/poseorder shows who is in the rotation. +scene/mode sets
  the pattern: round-robin (each person once per round) or 3-per
  (each person posts up to three times before passing).

SHARING

  Completed scenes are private by default. +scene/share publishes
  them to the public archive where any player can read the log via
  +scene <id>.

EXAMPLES

  +scene/start Negotiations on Platform 7
  → Opens a scene. Everyone in the room is notified.

  +scene/type Plot
  → Tags this scene as a staff plot arc.

  +scene/summary Kira cuts a deal with the spice merchant.
  → One-line archive summary for the log index.

  +scene/stop
  → Ends the scene. Total pose count announced to room.

  +scene/share
  → Publishes the most recently completed scene.

CHEAT SHEET
  +scene/start [title]   open a scene
  +scene/stop            close it
  +scene/type <type>     Social/Action/Plot/Vignette
  +scene/summary <text>  archive blurb
  +scene/share [id]      publish
  +scenes                list your scenes

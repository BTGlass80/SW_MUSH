---
key: building
title: Building Guide
category: Admin
summary: "Builders create and modify the game world: rooms, exits, objects."
aliases: [builder, worldbuilding]
see_also: ["@dig", "@tunnel", "@set", "@lock"]
access_level: 2
---
Builders create and modify the game world: rooms, exits, objects.

CREATING ROOMS
  @dig <name>          Create a new room
  @tunnel <dir>=<name> Create a room with a two-way exit
  @open <dir>=<room#>  Create an exit to an existing room

MODIFYING ROOMS
  @rdesc <text>        Set room description
  @rname <name>        Rename current room
  @set <prop>=<val>    Set room properties (cover_max, etc.)
  @zone <name>         Assign room to a zone

EXITS & LOCKS
  @link <dir>=<room#>  Link an exit to a room
  @unlink <dir>        Remove an exit link
  @lock <dir>=<expr>   Lock an exit (e.g., has:keycard & !wounded)

INFORMATION
  @examine             Show detailed room/object info
  @rooms               List all rooms
  @find <name>         Search for rooms by name
  @entrances           Show what exits lead to this room

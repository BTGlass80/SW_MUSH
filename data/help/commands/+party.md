---
key: +party
title: +Party — Group Party System
category: "Commands: Social"
summary: Form and manage an adventuring party with other online players. Share party chat and coordinate group activity.
aliases: [party, pc]
see_also: [+who, say, channels, pc]
tags: [party, group, social, command]
access_level: 0
examples:
  - cmd: "party invite Kira"
    description: "Invite the player Kira to your party."
  - cmd: "party accept"
    description: "Accept a pending party invitation."
  - cmd: "party list"
    description: "Show your current party members."
  - cmd: "party chat Let's head to the spaceport"
    description: "Send a private message to all party members."
  - cmd: "pc Incoming trouble!"
    description: "Short alias for party chat."
---

Form a party with other online players, manage membership, and
communicate privately via the party channel. Parties can hold up
to six members. The player who sends the first invite becomes the
party leader.

SYNTAX

  party invite <player>   Send an invitation to an online player
  party accept            Accept a pending invitation
  party decline           Decline a pending invitation
  party leave             Leave your current party
  party list              Show party members (online/offline status)
  party chat <message>    Send a message to all party members
  party kick <player>     Remove a member (leader only)
  pc <message>            Short alias for party chat

PARTY RULES

  • Parties hold a maximum of 6 members.
  • The player who creates the party is the leader.
  • If the leader leaves, leadership passes to the next member.
  • Invitations expire when accepted or declined; only one pending
    invite is tracked per recipient at a time.
  • Members can be offline — they appear in +party list as "offline"
    and rejoin the chat when they reconnect.

PARTY CHAT

  party chat <msg>  broadcasts privately to all online party members.
  Alias: pc <msg>

  Example:
    pc Watch for patrols near the south gate.
    → [Party] Kira Solenne: Watch for patrols near the south gate.

EXAMPLES

  party invite Tundra
  → Tundra receives an invitation and can type: party accept

  party list
  → Shows leader tag, names, and online/offline status.

  party kick Marko
  → Leader removes Marko; Marko is notified.

  party leave
  → You leave. If you were leader, leadership transfers.

SEE ALSO

  +who   Who is online right now.
  pc     Party chat shortcut.

CHEAT SHEET
  party invite <name>   invite a player
  party accept/decline  respond to an invite
  party list            show members
  party chat / pc       private party channel
  party kick <name>     leader only: remove member
  party leave           leave the party

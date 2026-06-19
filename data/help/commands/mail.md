---
key: mail
title: Mail — In-Game Persistent Messaging
category: "Commands: Social"
summary: Send and receive persistent messages with other players. Mail persists between sessions. Access via @mail, +mail, or mail — all equivalent.
aliases: [+mail]
see_also: [page, say, +channels, +news]
tags: [social, communication, command]
access_level: 0
examples:
  - cmd: "@mail"
    description: "List your inbox."
  - cmd: "@mail Jex = Welcome back"
    description: "Compose a message to Jex with subject 'Welcome back'. Then type the body and '-' to send."
  - cmd: "@mail/quick Jex/Meetup = Meet me at Docking Bay 94 in 10."
    description: "Send a one-line message without the compose flow."
  - cmd: "@mail/read 3"
    description: "Read message #3 in your inbox."
  - cmd: "@mail/reply 3"
    description: "Reply to message #3."
  - cmd: "@mail/delete 3"
    description: "Mark message #3 for deletion."
  - cmd: "@mail/purge"
    description: "Permanently delete all messages marked for deletion."
  - cmd: "@mail/unread"
    description: "Show how many unread messages you have."
---

The mail system lets you exchange persistent messages with other
players that survive across sessions. Unlike `page`, mail does not
require the recipient to be online.

**Access forms:** `@mail`, `+mail`, `mail` are all equivalent.

**Commands:**

    @mail                                — list inbox
    @mail <player> = <subject>           — begin composing
      (type message body, then '-' or @mail/send to send)
    @mail/quick <player>/<subj> = <body> — one-line send
    @mail/read <#>                       — read message
    @mail/reply <#>                      — reply to message
    @mail/forward <#> = <player>         — forward message
    @mail/delete <#|all>                 — mark for deletion
    @mail/purge                          — permanently delete
    @mail/sent                           — show sent messages
    @mail/unread                         — show unread count

**Compose flow:** Start with `@mail <player> = <subject>`, type your
message over one or more lines, then send with `-` (a dash on its own
line) or `@mail/send`.

**See also:** `page` for real-time private messages when the target is
online; `+channels` for faction/OOC group chat.

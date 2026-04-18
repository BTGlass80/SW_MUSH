---
key: navigation
title: Sublight Navigation
category: "Rules: Space"
summary: Sublight navigation moves your ship between adjacent zones.
aliases: [course, sublight, navigate]
see_also: [space, zonemap, hyperdrive]
---
Sublight navigation moves your ship between adjacent zones.

USAGE (pilot only)
  course                     Show current zone and neighbors
  course <zone name>         Set course for an adjacent zone
  course cancel              Cancel current transit

TRANSIT TIMES
  Dock <-> Orbit:           15 seconds
  Orbit <-> Deep Space:     20 seconds
  Deep Space <-> Lane:      25 seconds

DURING TRANSIT
Your ship is removed from the combat grid — you cannot fire or be fired
upon. You'll see an ETA countdown. On arrival, a piloting skill check
determines entry quality:
  Critical: brief +1D sensors bonus in the new zone
  Success:  clean entry
  Failure:  minor hazard table roll (you still arrive)

ZONE ADJACENCY
You can only set course to zones adjacent to your current zone. Use
'course' with no arguments to see what's connected.

ANOMALY INVESTIGATION
If the sensors operator has resolved an anomaly via 'deepscan', the
pilot can navigate to it: course anomaly <id>. Transit is only 10s.

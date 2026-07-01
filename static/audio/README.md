# SW_MUSH Ambient Audio

Zone-keyed ambient loop files for the fun16 ambient audio system.

## License requirement

All audio files placed here must be **CC0 (public domain)** or carry an
appropriate license permitting use in an online game without attribution
or royalty. Brian sources the audio; do not add files without verifying
the license.

## Expected files

One `.ogg` per track basename. Files must be **seamlessly loopable**
(the loop point is a clean crossfade, no click/gap at the wrap).

| Filename           | Zone types served                     |
|--------------------|---------------------------------------|
| `cantina.ogg`      | cantina                               |
| `spaceport.ogg`    | spaceport, landing                    |
| `market.ogg`       | market                                |
| `deep-space.ogg`   | space, deep_space                     |
| `city.ogg`         | urban, city                           |

## zone_type → track map (ZONE_AUDIO in static/client.html)

```js
var ZONE_AUDIO = {
  'cantina':      'cantina',
  'spaceport':    'spaceport',
  'landing':      'spaceport',
  'market':       'market',
  'space':        'deep-space',
  'deep_space':   'deep-space',
  'urban':        'city',
  'city':         'city',
};
```

Unmapped or absent `zone_type` values → silence (no file loaded).

## System behaviour

- **OFF by default.** The SOUND button in the client top strip must be
  clicked once to enable (satisfies browser autoplay policy).
- **Silent with no files present.** A missing `.ogg` (404) or a browser
  autoplay block produces silence via a `.catch()` swallow — no console
  error, no crash.
- **Crossfade on zone change.** The current loop fades out (~800ms) and
  the new loop fades in at 35% of the user's configured volume.
- **Persisted preference.** `localStorage` keys: `sw_ambient_enabled`
  (`'1'` = on, default off) and `sw_ambient_volume` (`0`–`1`, default
  `0.5`).

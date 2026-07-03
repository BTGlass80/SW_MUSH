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

## Sourcing guide (curated — links pre-vetted for license)

You don't need an ear or ogg-site knowledge: **every track behind the links
below is license-safe**, so just pick whichever *vibe* you like on a ~30-second
listen. There's no wrong pick — the beds play low and crossfaded, so they're
forgiving.

### The one license rule
Use only **OpenGameArt (filter: CC0)** or **Pixabay** links. Both are free for
use in the game with **no attribution required**. (Avoid Freesound unless a file
is explicitly tagged **CC0** — their licenses vary per file.)

### Per-track picks

| File             | Listen for                                              | Source |
|------------------|---------------------------------------------------------|--------|
| `city.ogg`       | futuristic city hum, distant traffic                    | OpenGameArt "Scifi City – Ambient Loop" — CC0, already `.ogg`, loops: <https://opengameart.org/content/scifi-city-ambient-loop> |
| `deep-space.ogg` | quiet low drone/hum, no melody                          | Pixabay "deep space drone": <https://pixabay.com/sound-effects/search/deep%20space%20drone/> · or OpenGameArt CC0: <https://opengameart.org/content/cc0-music-0> |
| `spaceport.ogg`  | busy hangar — engine rumble, distant ship whines        | Pixabay "spaceship ambience": <https://pixabay.com/sound-effects/search/spaceship%20ambience/> |
| `market.ogg`     | crowd bustle/voices, footsteps — **no music**           | Pixabay "busy marketplace": <https://pixabay.com/sound-effects/search/busy%20marketplace/> |
| `cantina.ogg`    | upbeat brassy "alien swing band," loungey (Mos Eisley)  | Pixabay "cantina band" (original royalty-free homages, safe): <https://pixabay.com/music/search/cantina%20band/> |

Length 1–3 min is ideal (longer = less repetitive). The system loops **and**
crossfades, so a perfectly seamless loop point is nice-to-have, not required.

### Get the file into the game
1. Download the track.
2. **Name it exactly** as the table's filename (e.g. `cantina.ogg`) and drop it
   in `static/audio/`.
3. Grabbed an **`.ogg`** (most OpenGameArt files)? You're done.
4. Grabbed an **`.mp3`** (most Pixabay files)? Convert it:
   ```
   ffmpeg -i cantina.mp3 -c:a libvorbis -q:a 5 cantina.ogg
   ```
   No ffmpeg? Install once: `winget install Gyan.FFmpeg` (then reopen the terminal).
5. In the client, click **SOUND** in the top strip (audio is off by default),
   then step into a room of that zone type to hear it.

### Two ways I can make this even easier — just ask
- **Skip conversion:** I can add `.mp3` fallback to the loader so Pixabay MP3s
  drop straight in (no ffmpeg needed).
- **Hand it off:** paste any track's **direct download URL** and I'll fetch,
  convert, name, and place it — you only listen and veto.

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

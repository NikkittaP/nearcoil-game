# NEARCOIL — website

Public pages for the Android game **NEARCOIL: Snake Arcade** (`com.nikitapetrovapps.nearcoil`),
served by GitHub Pages from the `main` branch, root folder.

- `index.html` — landing page
- `wiki/` — the player guide (en, ru), **generated**: edit `wiki-src/`, never `wiki/<lang>/*.html`
- `privacy/index.html` — privacy policy; this is the URL given to Google Play Console:
  `https://nikkittap.github.io/nearcoil-game/privacy/`

The source of truth for the policy is `privacy/index.html` here. The game repository
describes the same data in `docs/SUPABASE_SETUP.md` (step 22, store forms). When the
policy changes, edit it here first, bump "Last updated", then update the game docs.
Before any change that touches the network, data, telemetry or purchases, check it
against the manifest of the built AAB and the Supabase migrations.

## Wiki

`wiki-src/<lang>/<page>.html` holds the text (both languages), `wiki-src/game.json` the game
data, `wiki/img/<lang>/` the screenshots; `python tools/build_wiki.py` writes `wiki/<lang>/`.
The data and screenshots come from the game repository: `bash tools/wiki_update.sh` there
(see its `docs/WIKI.md`) exports them and rebuilds. A page placeholder the game no longer
has, or a missing screenshot, stops the build with the file and line.

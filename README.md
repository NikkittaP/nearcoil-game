# NEARCOIL — website

Public pages for the Android game **NEARCOIL: Snake Arcade** (`com.nikitapetrovapps.nearcoil`),
served by GitHub Pages from the `main` branch, root folder.

- `index.html` — landing page
- `privacy/index.html` — privacy policy; this is the URL given to Google Play Console:
  `https://nikkittap.github.io/nearcoil-game/privacy/`

The source of truth for the policy is `privacy/index.html` here. The game repository
describes the same data in `docs/SUPABASE_SETUP.md` (step 22, store forms). When the
policy changes, edit it here first, bump "Last updated", then update the game docs.
Before any change that touches the network, data, telemetry or purchases, check it
against the manifest of the built AAB and the Supabase migrations.

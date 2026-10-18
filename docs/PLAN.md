# Oracle of Ages bot: new game → D3 entrance, with replay + checkpoints

## Context
The user's old save was "about to enter D3 (Moonlit Grotto, Crescent Island)". We build a PyBoy bot that plays a
new game up to the D3 entrance (designed so it can extend to the whole game later). It keeps a complete
deterministic replay and checkpoints before and after every dungeon (Maku Path, D1, D2, before D3). Each checkpoint
has a PyBoy state **and** a portable battery `.sav`, so the user can continue in any emulator.

User decisions:
- **Must match the old save:**
  - file name `Link`
  - Bipin & Blossom child: name and answers set in config. Before D3 that means stage 0 (naming) and stage 1
    (doctor donation 150/50/10/1; needs ≥2 essences and ≥8 overworld screens walked before entering the house)
  - barrier-stone push direction in the intro (config, cosmetic)
  - other side quests are skipped; the user redoes them
- **Help for the bot:**
  - cheats for health, ammo and money are fine
  - the user takes over for bosses and nasty puzzles; their inputs are recorded in the replay
- **LLM role:** the route is compiled offline by Claude Code into a reviewable, version-controlled script. The Claude
  API is only a runtime stuck-fallback, built last and off by default.

Starting point:
- `X:\oracle_bot` has only `roms/oracle_of_ages.gbc` (US; md5 c4639cc6… equals oracles-disasm `ages.md5`; CGB-only,
  MBC5, 8 KiB SRAM, no RTC).
- Installed: Python 3.14.5, uv, git, gh. Not installed: make, WSL. So we don't build the disassembly.

## Approach (and answers to the user's four assumptions)
- **Don't fork a Link's Awakening framework.** They are all small, and the LA RAM map shares nothing with Ages.
  - The real asset is **Stewmath/oracles-disasm**: full RAM map, struct offsets, tile-property tables, save format.
  - Patterns borrowed: A* over a collision grid (ClaudePlaysPokemonStarter); frame-anchored input log
    (thibautbus/top, an Oracle PC port).
- **Cheats are logged RAM writes** applied by policy (below).
- **Human takeover:** our own SDL window; bot and human go through one input path, so the log is exact.
- **Low-level decisions:** primitives (walk/A*, talk, push, use item…) with closed-loop RAM feedback.
- **High-level planning:** an ordered route of steps authored from the StrategyWiki walkthrough (CC BY-SA, the most
  precise one), each step with a RAM predicate for "done".
  - No world graph in v1: about 60 traversals to D3, each a reviewable list of room hops.
  - The randomizer logic graph (oracles-randomizer-ng YAML) is the resource to use if we go past D3.

## Layout (~1,800 lines + route)
```
pyproject.toml   # pyboy==2.8.1 (pinned: save states/replays are version-bound), numpy, pillow; extra [llm]: anthropic
config.toml      # player names/choices, cheats, llm budget
oracle_bot/  emu.py record.py ram.py cheats.py nav.py act.py menus.py runner.py viewer.py cli.py llm.py
             data/ages.json   # generated symbols/struct offsets/tile tables (committed)
route/       __init__.py (segment order), places.py (named rooms/doors), s00_intro.py … s07_crescent.py
tools/       gen_symbols.py (vendor/oracles-disasm → data/ages.json), probe.py (determinism/speed)
tests/       pure tests: A*, BCD, log round-trip, .sav checksum
checkpoints/ replay.log + NN_name/{state.pyboy, game.sav, screen.png, meta.json}   # promoted canonical run
runs/, vendor/  (gitignored: dev runs, stuck bundles; disasm clone at a pinned commit)
```
We'll `git init`, but nothing gets committed until the user asks.

## Core design
- **emu.py:** PyBoy with `window="null"`, `sound_emulated=False`, `cgb=True`, zeroed 8 KiB SRAM.
  - One frame loop: `before_frame` hooks (cheats) → apply logged ops → `tick(1)` → `after_frame` hooks (viewer).
  - `set_buttons(mask)` uses the game's bit order. All memory writes go through `poke()`, which logs them.
  - Reads of `$D000–$DFFF` always pass an explicit WRAM bank.
  - Our own frame counter (PyBoy's isn't in save states).
  - No PyBoy hooks in the record/replay path: they patch ROM and aren't saved in states.
- **record.py: the replay log is the single source of truth.** States are caches; `.sav` files are exports.
  - Append-only text log:
    `#obot-replay 1 rom_sha1=… pyboy=2.8.1 cgb=1 sound=0 sram=zero8k`
    - `J` = held-button mask on change
    - `W` = write, `bank:addr bytes tag`, tag ∈ cheat/equip/rupees/respawn/dev
    - `C` = checkpoint + memory hash
    - `N` = note
    - `E` = end
  - `verify` re-simulates from power-on and compares hashes at every `C`. `verify --states` resumes from each saved
    state instead.
  - Checkpoints are only taken with all buttons released.
  - A run is promoted only if verify passes and it has no `dev` writes.
- **ram.py:** symbols from `data/ages.json`, generated from `wram.s` address comments and `structs.s`.
  - Lazy accessors: `room`, `link_px`, `has(treasure)`, `gflag`, `room_flag`, `essences`, `objects(kind)`.
  - Enemy fields are generated from structs (id `$Dn81`, health `$DnA9`, yh `$Dn8B`, xh `$Dn8D`), not hand-typed.
  - `controllable()`, `text_active()` and `option_prompt()` are calibrated from traces of real play. Watched
    variables: wGameState, wCutsceneIndex, wTextIsActive, wScrollMode, wPaletteThread_mode, wDisabledObjects,
    w1Link.state.
  - `summary()` produces a text snapshot for inspect, stuck bundles and the LLM.
- **nav.py:** live grid from wRoomCollisions `$CE00` and wRoomLayout `$CF00`.
  - 8px nodes. Collision is $00 free, $01–$0F quarter-tile masks, $10+ special.
  - A small subset of `tile_properties` overlays: breakables (bush/pot/rock), ledge jump directions, door/warp tiles
    (avoided unless they are the target), water/holes (only with `allow`).
  - `ascii()` dumps the map for debugging.
- **act.py:** primitives. They raise `Stuck` on failure and always return with Link controllable.
  - `settle(choices)` advances text and fails on any unexpected option prompt.
  - Others: `walk_to`, `travel(*room_hops)` (asserts the room after each hop), `enter`, `talk`, `open_chest`, `push`,
    `lift_throw`, `dig`, `use`, `play_harp`, `fight` (until wNumEnemies==0), `ride_cart`, `side_walk`/`side_jump`.
  - `equip` = logged RAM swap of wInventoryA/B with the storage slot. The saved bytes are the same as equipping via
    the menu; we fall back to a menu driver if a glitch shows up.
- **menus.py:**
  - `new_file` / `enter_name`: cursor driven by the name-entry grid. Fallback: a logged poke of the name buffer
    before confirming.
  - `save_game`: Start+Select, then "Save & continue".
- **cheats.py:** applied only when a file is loaded, gameplay is normal, and no menu or text is showing. A value is
  written only when it differs.
  - Health = max; max hearts are never touched.
  - Ammo = capacity (BCD) only for items that are both in inventory and flagged as owned. This keeps the Tokay theft
    and Ambi taking the mystery seeds behaving.
  - Rupees are off by default. `ensure_rupees(n)` tops up right before purchases or the donation, so exported saves
    have organic rupee counts.
  - Steps can suspend cheats: Ambi's soldier, the Crescent Island theft sequence, Wild Tokay.
  - `sanity()` runs before every release save.
- **runner.py:**
  - Route = flat decorated steps `@step(done=…, timeout_s, retries, human, cheats, note)` and `mark(name, release,
    expect)`.
  - A step is skipped if `done` is already true. On failure: stuck bundle (state, png, inspect.txt with summary,
    ASCII map, recent ops) → retry → LLM if enabled → human takeover if interactive, otherwise abort.
  - `human=True` steps (bosses) hand control back automatically once `done` is true.
  - A dev state is saved after every step.
  - A release `mark`:
    1. If needed, a logged `respawn` poke of wDeathRespawnBuffer to the dungeon-entrance screen. Loading a `.sav`
       resumes at the last door/stair warp, not at Link's exact position.
    2. In-game save.
    3. Validate the `.sav` (signature `Z21216-0` + checksum, primary and backup).
    4. Write state/sav/png/meta.json.
- **viewer.py:** PySDL2 window (already a PyBoy dependency), opened on demand even during headless runs.
  - F1 take over / give back, F5 dev checkpoint, F6 toggle cheats, Space pause, Tab fast-forward, Esc save log + quit.
  - Arrows / X / Z / Enter / RShift for the game buttons.
  - Real-time pacing at 59.73 fps.
- **llm.py (last milestone, optional):** Claude API, default `claude-opus-5-5` (switch to `claude-sonnet-5-5` /
  `claude-haiku-5-5` in config to save money).
  - Cached system prompt (mechanics, action API, relevant walkthrough section).
  - User turn: step goal, summary, ASCII map, 3x screenshot.
  - Tools: the primitives plus `press` / `done` / `give_up`, with `tool_choice` auto.
  - At most 12 turns per episode, append-only history.
  - Budget: ledger file with per-run and monthly caps. Estimate ≈ $0.3–0.8 per episode on Opus.
  - Fixes that work get baked back into the route offline.

Route authoring loop (Claude Code during implementation): run to the frontier → `obot inspect` the stuck bundle or
dev state (summary + ASCII map + PNG) → write the next steps → re-run from the last dev state.

Release checkpoints: `01_before_maku_path`, `02_after_maku_path`, `03_before_d1`, `04_after_d1`, `05_before_d2`,
`06_after_d2`, `07_before_d3`. Each has `expect` assertions, e.g. `07`: 2 essences, file name "Link", child stage 1
with the configured donation, D3-entered room flag `$C966 & $10` clear.

## Milestones (each ends verifiable)
- **M0 Probe:** uv project, minimal emu, `tools/probe.py`.
  - Prints headless fps; runs continuous-replay ×2, render-on/off invariance, and save→load-in-fresh-instance resume
    (full memory hash per frame); saves a title PNG.
  - If state resume isn't exact: states become dev-only caches, and canonical runs replay from power-on (`--exact`,
    one continuous process).
- **M1 Human play with recording** (useful on its own):
  - Build: viewer, record, cheats, gen_symbols, config, cli.
  - `uv run obot play --run m1`: create "Link", play a bit, save in game, F5, Esc.
  - `obot verify runs/m1` (and `--states`) passes.
  - `obot boot-sav <cp>/game.sav` boots the exported save in a fresh PyBoy and prints name/room. The user also loads
    it in their own emulator.
  - `obot watch` plays the log back.
- **M2 Inspection/calibration:** full ram, nav grid, `inspect` / `trace` / `step`.
  - The ASCII map matches the screenshot in an overworld room, a house and a dungeon room.
  - `controllable()` is true on ≥99% of frames where the d-pad moved Link, and false during text, scroll and fades.
  - Enemy offsets checked live.
- **M3 Primitives + runner + takeover:**
  - `uv run pytest` passes.
  - Smoke route: travel 5 screens, enter a house, talk with a choice, equip+use an item, save.
  - Mid-route F1 → manual walk → F1 → the bot resumes; verify still passes.
- **M4** Route to `02_after_maku_path` (headless run exits 0, verify passes, `boot-sav` OK).
- **M5** Satchel → graveyard → D1 (boss human-or-scripted) + child naming → `04_after_d1`.
- **M6** Fairies → harp → bombs → D2 + doctor donation → `06_after_d2`.
- **M7** Flippers/rope/Ricky/Tingle → raft → Crescent Island recovery → Wild Tokay → `07_before_d3`.
  - One canonical run from power-on, verify, `obot promote`.
  - The user loads `07_before_d3/game.sav` in their emulator.
- **M8 (optional)** LLM stuck-fallback, tested on a deliberately broken step; the ledger stays under the cap.

## Main risks → mitigations
| Risk | Mitigation |
|---|---|
| Text/cutscene/prompt detection | Calibrate from traces; unexpected prompt → `Stuck`; text index logged as notes |
| Screen transitions, warps, looping woods | Wait for scroll done + room change + controllable; assert the room after every hop |
| Knockback/enemies | Closed-loop re-plan per node, enemy cells cost extra, infinite health, `fight()` for shutter rooms |
| Push blocks | Align within 1px; hold until the `$CF00` tile changes; reset by leaving and re-entering the room |
| D2 sidescroll, minecarts, Wild Tokay, fairy hide-and-seek | Dedicated macros where cheap; otherwise `human=True` steps (recorded) |
| PyBoy accuracy on Ages (double-speed CGB) | Play through intro, portal and a dungeon room in M1 before any route work |
| Cheats breaking logic | Ownership gating, per-step suspension, `sanity()` before release saves, rupees off by default |
| .sav portability | Checksum validation + boot test; raw 8192 bytes; rename per emulator (`.sav` / `.SaveRAM`) |
| Wrong symbols/offsets | Generated from a pinned disasm commit; checked live in M2 |

## Verification (end to end)
1. `uv run pytest`.
2. `uv run obot verify checkpoints/replay.log`: a power-on re-simulation matches the memory hash at every checkpoint.
3. `uv run obot boot-sav checkpoints/07_before_d3/game.sav`: valid slot, name "Link", 2 essences, outside D3.
4. The user loads that `.sav` in their emulator; `obot watch checkpoints/replay.log` shows the full run.

## Findings log
- M0: PyBoy must run with `sound_emulated=True`: the game's audio engine busy-waits on NR30 bit 7, which reads 0
  when sound isn't emulated (white screen after the Capcom logo). Headless ≈ 11k fps, rendered ≈ 5k fps.
  Continuous replay, render on/off and save→load-in-fresh-instance resume are all bit-exact, so states are
  usable for both dev and canonical runs.

## Status (2026-10-18)
- The route runs headless from power-on to the Moonlit Grotto entrance (`uv run obot run`), with release
  checkpoints 01_before_maku_path, 02_after_maku_path, 03_before_d1, 04_after_d1, 05_before_d2, 06_after_d2 and
  07_before_d3 (each .sav boot-checked). `uv run obot verify` re-simulates the whole log (~293k frames) in ~100 s.
- The route stops at 07_before_d3: the user never entered the Moonlit Grotto.
- Extras the user asked for: every heart piece reachable before D3 (Black Tower 1:86, Maku Path 4:06, Yoll
  Graveyard 0:8b, Deku Forest cave 5:b1; 3:af needs the Switch Hook, the rest the Tune of Currents or Mermaid Suit)
  and the trading sequence as far as it goes before D3 (Poe Clock -> Stationery -> Stink Bag -> Tasty Meat; the
  mask salesman is on the mainland, and Crescent Island's raft back only appears with Dimitri).
- s07 (D2 -> D3): Cheval, the doctor donation, Moosh and Cheval's grave (flippers, rope), Rafton, Ricky's gloves,
  Tingle's chart (riding Ricky), the raft and storm, then Crescent Island: the Tokay item hunt (trading hut swaps,
  the dive under 5:cc, the side-view passage 7:06/7:07 to the harp plateau), vine sprouts, the Wild Tokay game
  (closed-loop meat throwing), the Scent Tree, bracelet and shield bought back, and the 1:d9 portal to the grotto.
- Navigation knows animals' and the raft's collision boxes, swimming drift, feather hops over pits/water, Ricky's
  punch, one-way ledges in a room (not across screen edges: those are scripted), and falls back to a covering
  survey tier when items are traded away.

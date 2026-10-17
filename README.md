# oracle_bot

A PyBoy bot that plays The Legend of Zelda: Oracle of Ages (US) from a new game, keeping a deterministic replay
log and release checkpoints (a PyBoy state plus a battery `.sav` for any emulator) before and after each dungeon.
Design and status: [docs/PLAN.md](docs/PLAN.md).

Needs the ROM at `roms/oracle_of_ages.gbc` and the disassembly at `vendor/oracles-disasm` (only to regenerate
symbols and for the dev tools).

## Running

```
uv run obot run                      # the whole route from power-on, into runs/main/
uv run obot run --from name_child    # resume from the snapshot before a step (see `uv run obot steps`)
uv run obot verify runs/main/replay.log
uv run obot promote                  # copy runs/main's checkpoints to checkpoints/
```

Checkpoints land in `runs/main/checkpoints/<NN_name>/` (`game.sav`, `state.pyboy`, `screen.png`, `meta.json`).

## Names and choices

`config.toml` holds everything that has to match your own save: the file name, the name of Bipin & Blossom's
child, the doctor donation (150/50/10/1), which way the intro's stone is pushed, and the message speed.

Changing one only affects the game from the step that uses it, so re-run from there; everything after it
(including later checkpoints) is regenerated:

| Setting | Re-run with |
|---|---|
| `child_name` | `uv run obot run --from name_child` |
| `donation` | from the donation step (after D2) |
| `file_name`, `stone_push`, `message_speed` | `uv run obot run` (from power-on) |

## Watching

Runs are deterministic, so any part of one can be re-rendered as a video afterwards (MP4 with ffmpeg on PATH,
otherwise GIF):

```
uv run obot video --step d2_swoop            # what one step did -> runs/main/clips/
uv run obot video --from 150000 --to 152000  # a frame range
```

When a step gets stuck, its bundle in `runs/main/stuck/` includes `clip.mp4`, the last 15 seconds before it.

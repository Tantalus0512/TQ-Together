# TQ Together

Your heroes as companions for each other in **Titan Quest Anniversary Edition** (Steam and GOG).

Every hero in your saves can fight at the side of your other heroes. Each time you start the game through
TQ Together, the companion is rebuilt from that hero's **current** save — level, attributes, masteries and skills,
worn gear with its affixes. Companions are summoned with **Eidolons**, two-shard ring relics that drop from
Legendary electrum orbs.

- Download and player instructions: [Nexus Mods page](https://www.nexusmods.com/titanquestanniversaryedition/mods/127)
- Player readme: [docs/README_EN.txt](docs/README_EN.txt) · [docs/README_RU.txt](docs/README_RU.txt)

## Why a program and not a plain data mod

The mod has to be generated from each player's own saves, on every start, so it ships as a small Windows program
(`TQTogether.exe`, Python packed with PyInstaller). It:

- reads the saves in `Documents\My Games\Titan Quest - Immortal Throne\SaveData\Main` (read-only);
- writes a modified copy of the game's `Database\database.arz` and adds text lines to `Text\Text_*.arc`
  (via the game's own `ArchiveTool.exe`), keeping the originals next to them as `*.tqtogether-base`;
- keeps its state in `Documents\My Games\Titan Quest - Immortal Throne\TQ Together`;
- starts the game (`steam://rungameid/475150` for Steam, `TQ.exe` otherwise);
- uses the Python standard library only and contains **no network code** (networking/crypto modules are excluded
  from the build, see `build_exe.py`).

`TQTogether.exe --uninstall` restores the original game files.

## Build

Windows, Python 3.14:

```
py -3 -m pip install -r requirements-build.txt
py -3 build_exe.py
```

The result is `dist/TQ Together <version>/` and `dist/TQ_Together_<version>.zip` — exactly the archive published on
Nexus Mods. `_internal/base_library.zip` inside it is PyInstaller's standard bundle of the Python standard library.

Run from source without building: `py -3 src/tq_together.py [--uninstall | --rebuild | --no-launch]`.

## Source overview

| file | purpose |
|---|---|
| `src/tq_together.py` | entry point: finds the game, rebuilds when a hero changed, installs, launches |
| `src/paths.py` | game detection (TQTogether.ini, Steam libraries, GOG registry), Documents folder |
| `src/installer.py` | originals (`*.tqtogether-base`), game-update detection, text archives, uninstall |
| `src/build_companions.py` | reads each `Player.chr` and builds the companion, summon skill and eidolon records |
| `src/verify_companions.py` | self-check of every build; nothing is installed unless it passes |
| `src/arz_lazy.py`, `src/arz.py` | reader/writer of the game's `.arz` database |
| `src/chr_reader.py` | reader of `Player.chr` save files |
| `src/orb_odds.py` | exact drop odds of the electrum orbs (used by the self-check) |

## License

MIT — see [LICENSE](LICENSE).

# Pick & Shiny

A mod for **Eslabong** (Steam, Godot 4.6) for offline single-player.

- **Better shiny odds for your own fighters.** Starters, market, scouting office and reward chests use 1 in 2 by default, and you can choose the number. AI teams, league fighters and enemies keep the game's 1 in 5000. The staff Shiny Catcher bonus still stacks.
- **Starter picker.** On the new-club screen, in Random Mode and Champion Mode, every starting fighter gets **◀ Reroll ▶** underneath it:
  - **◀ / ▶** picks that fighter's class. Hold the button to scroll.
  - **Reroll** keeps the class and rolls new stats and a new shiny chance. The other fighters stay as they are.
  - Keys **1 / 2 / 3** reroll a slot, and **Shift+1/2/3** step to the next class. **R** rerolls everything, as in the base game.
  - The fighters on screen are exactly the ones you get, shinies included.
- **Champion Mode with three champions.** Champion Mode starts with 3 different champions instead of 1 champion and 2 fighters.

## Install (players)

1. Download `PickAndShiny-<version>.zip` from **Releases** and unzip it anywhere.
2. Close Eslabong, then run `PickAndShiny.exe`. Windows may show "Windows protected your PC" because the program is unsigned; click **More info → Run anyway**.
3. The program finds the game through Steam. Choose your options and click **Install / Update**. It takes about a minute, because it builds the mod for your copy of the game and tests it by starting the game invisibly.
4. Start Eslabong from Steam as usual. Your saves are never modified by installing or uninstalling.

**Game updates.** The mod rebuilds itself when the game updates. For the smoothest experience, paste the launch option shown in the program into Steam: Eslabong → Properties → General → Launch Options. Without it, the first start after an update shows a note and you restart the game once.

**Uninstall.** Open `PickAndShiny.exe` and click **Uninstall**. It is also at `%LOCALAPPDATA%\PickAndShiny\app`.

## How it works

Nothing from the game is in this repository or in the release. Everything is built on the player's PC from their own installation:

1. **Key.** The pack's encryption key is recovered from the player's own `eslabong.exe` (`tools/keyfind.py`).
2. **Decompile.** The four scripts the mod changes are decompiled with [GDRE Tools](https://github.com/GDRETools/gdsdecomp): `MercenaryInstance`, `StaffService`, `TeamFoundingScreen` and `CampaignService`.
3. **Patch.** The edits in `mod/edits.py` are applied. Each edit is anchored on exact game code, and the edits are grouped into independent features. If a game update changes the code at an anchor, only that feature turns off.
4. **Compile.** The patched scripts are compiled back to the game's own bytecode (`.gdc`) and packed into `patch-<hash>.pck`. Every build gets a new file name, so a running game never has its mounted pack changed underneath it.
5. **Load.** A small block in `override.cfg` makes `boot.gd` the first autoload. Before any game script loads, it checks fingerprints of the original scripts and mounts the pack. If the game updated those scripts, the patch is skipped, the game runs normally, and the mod rebuilds itself.
6. **Self-test.** Before anything is kept, the real game engine runs headless. It checks the patched logic (shiny rates and the champion rules), then compiles all ~730 game scripts and compares the result with the unmodified game. The engine kills itself inside the loader, before Steam or any save is touched. If anything fails, the previous install is restored.

## Development

Requirements are Python 3.14 (`pip install -r requirements.txt`) and GDRE Tools 2.6.4 for Windows. Put GDRE in `gdre/` or set `PICKSHINY_GDRE`.

```
python build.py install      # build, install, self-test on the real engine
python build.py auto         # rebuild only if the game or the mod changed
python build.py uninstall
python app.py                # the installer window, from source
python installer/make_installer.py   # PickAndShiny.exe + GDRE -> installer/PickAndShiny-<version>.zip
python export_repo.py <git checkout>  # copy only publishable files, scan for secrets
```

Tests live in `tools/test_*.py`. `test_degradation.py` needs one `python build.py` first, because it reads the locally decompiled scripts in `work/`. Those scripts are never committed.

## Notes

- **Offline single-player only.** Please don't take modded teams into online modes.
- **EULA.** Eslabong's EULA does not allow decompiling or modifying the game. Use at your own risk.
- **Not affiliated.** This project is not made by or affiliated with the developers of Eslabong.
- **Licenses.** GDRE Tools is MIT licensed, © bruvzg; see `installer/THIRD-PARTY-NOTICES.txt`. This project is MIT licensed; see `LICENSE`.

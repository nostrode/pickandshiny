"""Simulates game updates that break edit anchors and checks features degrade independently."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "mod"))
import edits  # noqa: E402

SRC = os.path.join(ROOT, "work", "decompiled")
sources = {}
for res_path in edits.TARGETS:
    with open(os.path.join(SRC, os.path.basename(res_path)), encoding="utf-8") as f:
        sources[res_path] = f.read()


def run(label, mutate):
    mutated = dict(sources)
    mutate(mutated)
    patched, report = edits.apply_all(mutated)
    summary = {fid: ("ON" if f["active"] else "OFF") + (f" skipped={len(f.get('skipped', []))}" if f.get("skipped") else "")
               for fid, f in report["features"].items()}
    print(f"{label:55} {summary}  scripts={sorted(os.path.basename(p) for p in patched)}")
    return patched, report


# 1. unchanged game
patched, report = run("unchanged game", lambda s: None)
assert report["active"] == ["player_shiny", "slot_picker", "champion_trio"] and len(patched) == 4
assert not any(f.get("skipped") for f in report["features"].values()), report

# 1b. starter commit rewritten -> trio off, CampaignService untouched, champion slots 2-3 stay troops
def break_commit(s):
    s[edits.CAMPAIGN_SERVICE] = s[edits.CAMPAIGN_SERVICE].replace(
        "elif is_named_champion or not _is_renown_free_standard_starter_metadata(meta):", "elif not is_named_champion:")
patched, report = run("starter commit changed", break_commit)
assert report["active"] == ["player_shiny", "slot_picker"] and edits.CAMPAIGN_SERVICE not in patched
assert "func _ps_champion_trio_enabled" not in patched[edits.TEAM_FOUNDING_SCREEN]
assert "func _ps_roll_champion_trio" not in patched[edits.TEAM_FOUNDING_SCREEN]

# 2. founding screen rewritten around the slot hook -> slot picker off, shiny stays (incl. starter odds)
def break_wrap(s):
    s[edits.TEAM_FOUNDING_SCREEN] = s[edits.TEAM_FOUNDING_SCREEN].replace("_wrap_champion_chip_with_arrows(chip)", "_wrap_champion(chip)")
patched, report = run("founding screen changed at the slot hook", break_wrap)
assert report["active"] == ["player_shiny"]  # the trio needs the slot picker, so it is off too
assert "needs feature" in report["features"]["champion_trio"]["error"]
tfs = patched[edits.TEAM_FOUNDING_SCREEN]
assert "roll_player_shiny_flag" in tfs and "_ps_wrap_slot_chip" not in tfs

# 3. shiny constant renamed -> shiny off; slot picker stays and uses vanilla odds
def break_const(s):
    s[edits.MERCENARY_INSTANCE] = s[edits.MERCENARY_INSTANCE].replace("const SHINY_ROLL_DENOMINATOR: int = 5000", "const SHINY_ODDS: int = 5000")
patched, report = run("shiny constant renamed", break_const)
assert report["active"] == ["slot_picker", "champion_trio"] and edits.MERCENARY_INSTANCE not in patched
tfs = patched[edits.TEAM_FOUNDING_SCREEN]
assert "roll_player_shiny_flag" not in tfs and "_ps_wrap_slot_chip" in tfs

# 4. staff code changed -> recruits keep vanilla odds, everything else on
def break_staff(s):
    s[edits.STAFF_SERVICE] = s[edits.STAFF_SERVICE].replace("var denominator: int = MercenaryInstance.SHINY_ROLL_DENOMINATOR * precision", "var denominator := 5000")
patched, report = run("staff shiny roll changed", break_staff)
assert report["active"] == ["player_shiny", "slot_picker", "champion_trio"] and edits.STAFF_SERVICE not in patched

# 5. class check anchor gone -> 'keep previews on refresh' must not be applied alone
def break_reuse(s):
    s[edits.TEAM_FOUNDING_SCREEN] = s[edits.TEAM_FOUNDING_SCREEN].replace("var reused_preview: bool = merc != null", "var reused: bool = merc != null")
patched, report = run("preview reuse code changed", break_reuse)
assert "\t\t\t_rebuild_skipped_intro_preview_row(_editing_founding_setup)\n" in patched[edits.TEAM_FOUNDING_SCREEN]
assert any("needs" in s for s in report["features"]["slot_picker"]["skipped"])
print("degradation tests passed")

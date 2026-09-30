"""Pick & Shiny source edits, applied to freshly decompiled game scripts by build.py.

Edits are anchored on exact vanilla code (each anchor must match exactly once) and
grouped into independent features. After a game update:
  - a failed REQUIRED edit switches only its own feature off (the other still ships);
  - a failed OPTIONAL edit is skipped and reported, its feature stays on.
"""

# Player-owned fighters only; AI clubs, enemies and league fighters keep the vanilla
# MercenaryInstance.SHINY_ROLL_DENOMINATOR (5000).
PLAYER_SHINY_DENOMINATOR = 2
ENABLED_FEATURES = {"player_shiny": True, "slot_picker": True, "champion_trio": True}


def configure(options):
    """Applies the installer options: {"shiny_denominator": int, "features": {id: bool}}."""
    global PLAYER_SHINY_DENOMINATOR, ENABLED_FEATURES
    PLAYER_SHINY_DENOMINATOR = max(1, int(options.get("shiny_denominator", PLAYER_SHINY_DENOMINATOR)))
    ENABLED_FEATURES = dict(ENABLED_FEATURES, **options.get("features", {}))

MERCENARY_INSTANCE = "Scripts/Campaign/MercenaryInstance.gd"
STAFF_SERVICE = "Scripts/Staff/StaffService.gd"
TEAM_FOUNDING_SCREEN = "Scenes/Campaign/TeamFoundingScreen.gd"
CAMPAIGN_SERVICE = "Scripts/Campaign/CampaignService.gd"
TARGETS = [MERCENARY_INSTANCE, STAFF_SERVICE, TEAM_FOUNDING_SCREEN, CAMPAIGN_SERVICE]

SELFTEST_CONFIG = "res://Data/Mercenaries/Merc_Warrior_Fighter.tres"
SELFTEST_CHAMPIONS = [
    "res://Data/Mercenaries/Champions/Named_Champion_AboBro.tres",
    "res://Data/Mercenaries/Champions/Named_Champion_Aloextreme.tres",
    "res://Data/Mercenaries/Champions/Named_Champion_Angelitus.tres",
]
PLAYER_NEW_FIGHTER = 'MercenaryInstance.new(config_path, "", 1, MercenaryInstance.roll_player_shiny_flag())'
VANILLA_NEW_FIGHTER = "MercenaryInstance.new(config_path)"


class Edit:
    def __init__(self, script, label, old, new, required, append=False):
        self.script, self.label, self.old, self.new = script, label, old, new
        self.required, self.append = required, append

    def apply(self, text, tokens):
        new = self.new
        for token, value in tokens.items():
            new = new.replace(token, value)
        if self.append:
            return text.rstrip("\n") + new
        count = text.count(self.old)
        if count != 1:
            raise LookupError(f"anchor found {count} times (expected 1)")
        return text.replace(self.old, new)


TFS_APPENDIX = '''


# ---- Pick & Shiny mod: pick each starter's class and reroll slots one at a time ----
const PS_SLOT_WRAP_PREFIX: String = "PSSlotWrap_"
const PS_SLOT_CHIP_NAME: String = "PSSlotChip"
const PS_NAV_REPEAT_MIN_INTERVAL: float = 0.06

var _ps_troop_pool: Array[String] = []
var _ps_random_pool: Array[String] = []
var _ps_nav_timer: Timer = null
var _ps_nav_slot: int = -1
var _ps_nav_direction: int = 0
var _ps_nav_interval: float = 0.0
var _ps_nav_ticks: int = 0
var _ps_nav_fired: bool = false


func _ps_choice_id() -> String:
	return str(_selected_starter_choice_id).strip_edges().to_lower()


func _ps_is_slot_mode() -> bool:
	var choice: String = _ps_choice_id()
	return choice == "full_random" or choice == "champion_start"


## Classes a slot can cycle through. Built with the same rules the starter commit
## validates against (CampaignService._sanitize_skipped_intro_starter_configs_with_variants),
## so a picked lineup can never be rejected on confirm.
func _ps_get_slot_pool(slot: int) -> Array[String]:
	if _ps_slot_uses_champion_pool(slot):
		return _get_champion_cycle_pool()  # cached array: never modify it
	if _ps_choice_id() == "champion_start":
		if _ps_troop_pool.is_empty() and campaign_service != null and campaign_service.has_method("get_newbie_mercenary_pool"):
			for config_path_var in campaign_service.get_newbie_mercenary_pool():
				var troop_path: String = str(config_path_var).strip_edges()
				if not _ps_troop_pool.has(troop_path) and _is_valid_champion_support_preview_config_path(troop_path):
					_ps_troop_pool.append(troop_path)
			_ps_troop_pool.sort()
		return _ps_troop_pool
	if _ps_random_pool.is_empty():
		if _cached_valid_newbie_pool.is_empty():
			_build_valid_newbie_pool_cache()
		for random_path in _cached_valid_newbie_pool:
			if not _ps_random_pool.has(random_path) and _is_valid_preview_config_path(random_path):
				_ps_random_pool.append(random_path)
		_ps_random_pool.sort()
	return _ps_random_pool


## Champion Mode slot 0 always cycles champions; with the champion-trio feature built in
## (it adds _ps_champion_trio_enabled), every slot does.
func _ps_slot_uses_champion_pool(slot: int) -> bool:
	return _ps_choice_id() == "champion_start" and (slot == 0 or has_method("_ps_champion_trio_enabled"))


func _ps_ensure_slot_arrays(slot: int) -> bool:
	if slot < 0 or slot >= _skipped_intro_preview_configs.size():
		return false
	while _skipped_intro_preview_visual_variants.size() < _skipped_intro_preview_configs.size():
		_skipped_intro_preview_visual_variants.append("")
	if _skipped_intro_preview_mercs.size() < _skipped_intro_preview_configs.size():
		_skipped_intro_preview_mercs.resize(_skipped_intro_preview_configs.size())
	return true


func _ps_store_slots_in_save() -> void:
	if campaign_service != null and campaign_service.current_save != null:
		campaign_service.current_save.skipped_intro_starter_configs = _skipped_intro_preview_configs.duplicate()
		campaign_service.current_save.skipped_intro_starter_visual_variants = _skipped_intro_preview_visual_variants.duplicate()


func _ps_cycle_slot(slot: int, direction: int, animate: bool = true) -> void:
	if not _ps_ensure_slot_arrays(slot):
		return
	var pool: Array[String] = _ps_get_slot_pool(slot)
	if pool.is_empty():
		return
	var current_index: int = pool.find(_skipped_intro_preview_configs[slot])
	if pool.size() == 1 and current_index == 0:
		return
	var next_index: int = wrapi(current_index + direction, 0, pool.size())
	if current_index < 0:
		next_index = 0 if direction > 0 else pool.size() - 1
	if _ps_slot_uses_champion_pool(slot):
		# Champions are unique: skip the ones already standing in another slot.
		var taken: Array[String] = []
		for other in range(_skipped_intro_preview_configs.size()):
			if other != slot:
				taken.append(_skipped_intro_preview_configs[other])
		var step: int = 1 if direction >= 0 else -1
		var tries: int = pool.size()
		while tries > 0 and taken.has(pool[next_index]):
			next_index = wrapi(next_index + step, 0, pool.size())
			tries -= 1
		if taken.has(pool[next_index]) or next_index == current_index:
			return
	if animate and GlobalSFX and GlobalSFX.has_method("play_ui_logo_cycle"):
		GlobalSFX.play_ui_logo_cycle()
	var config_path: String = pool[next_index]
	_skipped_intro_preview_configs[slot] = config_path
	_skipped_intro_preview_visual_variants[slot] = _roll_visual_variant_for_config(config_path)
	if slot == 0 and _ps_choice_id() == "champion_start":
		_champion_cycle_index = next_index
	_ps_store_slots_in_save()
	_ps_refresh_slot(slot, animate)


## Same class, brand-new fighter: new stats, new look variant and a new shiny roll.
func _ps_reroll_slot(slot: int) -> void:
	if not _ps_ensure_slot_arrays(slot):
		return
	var config_path: String = _skipped_intro_preview_configs[slot]
	if config_path == "" or not ResourceLoader.exists(config_path):
		return
	if GlobalSFX and GlobalSFX.has_method("play_ui_randomize"):
		GlobalSFX.play_ui_randomize()
	_skipped_intro_preview_visual_variants[slot] = _roll_visual_variant_for_config(config_path)
	_ps_store_slots_in_save()
	_ps_refresh_slot(slot, true)


func _ps_refresh_slot(slot: int, animate: bool) -> void:
	if not _ps_replace_slot_chip(slot):
		_ps_stop_nav_repeat()
		_skipped_intro_preview_mercs[slot] = null
		_rebuild_skipped_intro_preview_row(true)
	if animate:
		call_deferred("_ps_play_slot_reveal", slot)


func _ps_replace_slot_chip(slot: int) -> bool:
	if starter_roster_row == null or not is_instance_valid(starter_roster_row):
		return false
	var wrap: Node = starter_roster_row.get_node_or_null(PS_SLOT_WRAP_PREFIX + str(slot))
	if wrap == null:
		return false
	var old_chip: Control = wrap.find_child(PS_SLOT_CHIP_NAME, true, false) as Control
	if old_chip == null:
		return false
	var config_path: String = _skipped_intro_preview_configs[slot]
	if config_path == "" or not ResourceLoader.exists(config_path):
		return false
	var merc: = @NEW_FIGHTER@
	if merc == null:
		return false
	var variant_path: String = str(_skipped_intro_preview_visual_variants[slot]).strip_edges()
	if variant_path != "":
		merc.visual_variant_path = variant_path
	if _ps_choice_id() == "champion_start":
		_apply_champion_start_preview_loadout(merc)
	_skipped_intro_preview_mercs[slot] = merc
	var chip_parent: Node = old_chip.get_parent()
	var chip_position: int = old_chip.get_index()
	chip_parent.remove_child(old_chip)
	old_chip.queue_free()
	MercenaryConfig.clear_icon_cache(true)
	MercenaryInstance.clear_shared_config_cache()
	var new_chip: Control = _create_skipped_intro_preview_chip(merc, slot)
	new_chip.name = PS_SLOT_CHIP_NAME
	chip_parent.add_child(new_chip)
	chip_parent.move_child(new_chip, chip_position)
	return true


func _ps_play_slot_reveal(slot: int) -> void:
	if starter_roster_row == null or not is_instance_valid(starter_roster_row):
		return
	var wrap: Node = starter_roster_row.get_node_or_null(PS_SLOT_WRAP_PREFIX + str(slot))
	if wrap == null:
		return
	var chip: Control = wrap.find_child(PS_SLOT_CHIP_NAME, true, false) as Control
	if chip != null:
		_play_starter_card_reroll_reveal(chip, 0.0)


## Fighter card on top, [<] [Reroll] [>] underneath (keeps three slots inside the panel width).
func _ps_wrap_slot_chip(chip: Control, slot: int) -> Control:
	var wrap: = VBoxContainer.new()
	wrap.name = PS_SLOT_WRAP_PREFIX + str(slot)
	wrap.alignment = BoxContainer.ALIGNMENT_CENTER
	wrap.add_theme_constant_override("separation", 2)
	wrap.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	chip.name = PS_SLOT_CHIP_NAME
	wrap.add_child(chip)

	var controls: = HBoxContainer.new()
	controls.alignment = BoxContainer.ALIGNMENT_CENTER
	controls.add_theme_constant_override("separation", 4)
	wrap.add_child(controls)

	var can_cycle: bool = _ps_get_slot_pool(slot).size() > 1
	controls.add_child(_ps_make_nav_button(slot, -1, can_cycle))

	var reroll_btn: = Button.new()
	reroll_btn.text = "Reroll"
	_style_button(reroll_btn, true)
	reroll_btn.custom_minimum_size = Vector2(64, 28)
	reroll_btn.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	EslabongTheme.attach_premium_tooltip(
		reroll_btn,
		"Reroll this fighter",
		"Same class, new stats and a new shiny roll. The other fighters stay as they are.",
		"Key %d" % (slot + 1)
	)
	reroll_btn.pressed.connect(_ps_reroll_slot.bind(slot))
	controls.add_child(reroll_btn)

	controls.add_child(_ps_make_nav_button(slot, 1, can_cycle))
	return wrap


func _ps_make_nav_button(slot: int, direction: int, enabled: bool) -> Button:
	var btn: = Button.new()
	_style_logo_nav_button(btn, direction)
	btn.custom_minimum_size = Vector2(30, 30)
	btn.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	btn.disabled = not enabled
	if not enabled:
		btn.modulate.a = 0.35
	btn.tooltip_text = "Previous fighter class" if direction < 0 else "Next fighter class (Shift+%d)" % (slot + 1)
	btn.pressed.connect( func() -> void :
		if _ps_consume_nav_repeat_click():
			return
		_ps_cycle_slot(slot, direction)
	)
	btn.button_down.connect(_ps_start_nav_repeat.bind(slot, direction))
	btn.button_up.connect(_ps_stop_nav_repeat)
	return btn


func _ps_start_nav_repeat(slot: int, direction: int) -> void:
	_ps_nav_fired = false
	if _ps_get_slot_pool(slot).size() <= 1:
		return
	if _ps_nav_timer == null or not is_instance_valid(_ps_nav_timer):
		_ps_nav_timer = Timer.new()
		_ps_nav_timer.name = "PSSlotNavRepeatTimer"
		_ps_nav_timer.one_shot = true
		_ps_nav_timer.timeout.connect(_ps_on_nav_repeat_timeout)
		add_child(_ps_nav_timer)
	_ps_nav_slot = slot
	_ps_nav_direction = direction
	_ps_nav_interval = CREST_NAV_REPEAT_START_INTERVAL
	_ps_nav_ticks = 0
	_ps_nav_timer.start(CREST_NAV_REPEAT_DELAY)


func _ps_stop_nav_repeat() -> void:
	_ps_nav_direction = 0
	if _ps_nav_timer != null and is_instance_valid(_ps_nav_timer):
		_ps_nav_timer.stop()


func _ps_on_nav_repeat_timeout() -> void:
	var still_held: bool = Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT) or Input.is_action_pressed("ui_accept")
	if _ps_nav_direction == 0 or not still_held or not _ps_is_slot_mode():
		_ps_stop_nav_repeat()
		return
	_ps_nav_fired = true
	_ps_nav_ticks += 1
	if _ps_nav_ticks % 3 == 1 and GlobalSFX and GlobalSFX.has_method("play_ui_logo_cycle"):
		GlobalSFX.play_ui_logo_cycle()
	_ps_cycle_slot(_ps_nav_slot, _ps_nav_direction, false)
	if _ps_nav_direction == 0:
		return
	_ps_nav_interval = maxf(PS_NAV_REPEAT_MIN_INTERVAL, _ps_nav_interval * CREST_NAV_REPEAT_ACCEL)
	_ps_nav_timer.start(_ps_nav_interval)


func _ps_consume_nav_repeat_click() -> bool:
	if not _ps_nav_fired:
		return false
	_ps_nav_fired = false
	return true


## 1/2/3 reroll that slot; Shift+1/2/3 steps that slot to the next class.
func _ps_handle_slot_shortcut(key: InputEventKey) -> bool:
	if key.ctrl_pressed or key.alt_pressed or key.meta_pressed:
		return false
	var slot: int = -1
	match key.keycode:
		KEY_1, KEY_KP_1:
			slot = 0
		KEY_2, KEY_KP_2:
			slot = 1
		KEY_3, KEY_KP_3:
			slot = 2
	if slot < 0 or slot >= _skipped_intro_preview_configs.size():
		return false
	var focus_owner: Control = get_viewport().gui_get_focus_owner()
	if focus_owner is LineEdit or focus_owner is TextEdit:
		return false
	if not (_is_setup_mode() and _should_use_intro_starter_setup() and _ps_is_slot_mode() and not _is_any_founding_popup_open()):
		return false
	if _ps_details_panel_open() or (_crest_album_layer != null and is_instance_valid(_crest_album_layer)):
		return false
	if key.shift_pressed:
		_ps_cycle_slot(slot, 1)
	else:
		_ps_reroll_slot(slot)
	get_viewport().set_input_as_handled()
	return true


## The fighter-details panel (_open_merc_details) sits on its own CanvasLayer under root and is
## not one of the tracked founding popups; slot keys must not swap the fighter it is showing.
func _ps_details_panel_open() -> bool:
	for overlay in get_tree().root.get_children():
		if overlay is CanvasLayer and not overlay.is_queued_for_deletion() and overlay.get_child_count() > 0:
			var panel: Node = overlay.get_child(0)
			if panel.has_method("show_mercenary") and panel.has_signal("close_requested"):
				return true
	return false


## Vanilla restores looks through a class-keyed lookup, so two slots of the same class would
## both get the last one's look after a screen refresh. Restore by slot when the list matches.
func _ps_restore_saved_variants(configs: Array[String], save: CampaignSave) -> Array[String]:
	var saved_configs: Array = save.skipped_intro_starter_configs
	var saved_variants: Array = save.skipped_intro_starter_visual_variants
	var by_slot: bool = configs.size() <= saved_configs.size() and configs.size() <= saved_variants.size()
	if by_slot:
		for i in range(configs.size()):
			if str(saved_configs[i]).strip_edges() != configs[i]:
				by_slot = false
				break
	if not by_slot:
		return _apply_visual_variant_lookup(configs, _build_visual_variant_lookup(saved_configs, saved_variants))
	var result: Array[String] = []
	for i in range(configs.size()):
		result.append(str(saved_variants[i]).strip_edges())
	return result
'''

TRIO_APPENDIX = '''


# ---- Pick & Shiny mod: Champion Mode starts with three champions ----
func _ps_champion_trio_enabled() -> bool:
	return true


## Three distinct champions (Champion Mode card, global R, fallback when a saved lineup is short).
func _ps_roll_champion_trio() -> bool:
	if campaign_service == null or campaign_service.current_save == null:
		return false
	var pool: Array[String] = _get_champion_cycle_pool().duplicate()  # never shuffle the cached pool
	if pool.size() < 3:
		return false
	pool.shuffle()
	_skipped_intro_preview_configs.clear()
	_skipped_intro_preview_visual_variants.clear()
	_skipped_intro_preview_mercs.clear()  # a full reroll must not reuse the old slot-0 fighter
	for i in range(3):
		_skipped_intro_preview_configs.append(pool[i])
		_skipped_intro_preview_visual_variants.append(_roll_visual_variant_for_config(pool[i]))
	_champion_cycle_index = _get_champion_cycle_pool().find(pool[0])
	campaign_service.current_save.skipped_intro_starter_choice = "champion_start"
	_ps_store_slots_in_save()
	_refresh_founder_panel_watermarks()
	return true


## Restores a saved Champion Mode lineup in slot order with the same rule as the patched starter
## commit: slot 1 is a champion; later slots take a champion not already listed or a regular
## fighter. So trios, mixed lineups and old 1 champion + 2 fighter saves all survive a refresh.
func _ps_sanitize_champion_trio(config_paths: Array) -> Array[String]:
	var lineup: Array[String] = []
	for config_path_var in config_paths:
		var config_path: String = str(config_path_var).strip_edges()
		if _is_valid_champion_preview_config_path(config_path):
			if lineup.has(config_path):
				continue
		elif lineup.is_empty() or not _is_valid_champion_support_preview_config_path(config_path):
			continue
		lineup.append(config_path)
		if lineup.size() >= 3:
			break
	return lineup
'''

CS_APPENDIX = '''


# ---- Pick & Shiny mod: all Champion Mode starters get the season-1 founder protection ----
# Same rule as _migrate_founding_champion_instance_id. The save keeps vanilla's single id, so a
# session without the mod still protects one champion.
func _ps_is_founding_champion(instance_id: String) -> bool:
	var merc: MercenaryInstance = current_save.get_mercenary_by_id(instance_id)
	if merc == null:
		return false
	var cfg: MercenaryConfig = merc.get_config() as MercenaryConfig
	return cfg != null and cfg.is_named_auction_champion() and current_save.skipped_intro_starter_configs.has(cfg.resource_path)
'''

MI_APPENDIX = '''


# Pick & Shiny: shiny roll for fighters the player receives (passed as p_shiny to _init;
# can_roll_shiny still vetoes bosses, summons and squad leaders).
static func roll_player_shiny_flag() -> bool:
	return randi_range(1, PLAYER_SHINY_ROLL_DENOMINATOR) == 1
'''

# Order matters: player_shiny is resolved first because slot_picker's code uses its helper
# (@NEW_FIGHTER@) only when player_shiny is active.
FEATURES = [
    {
        "id": "player_shiny",
        "title": "better shiny odds for your own fighters",
        "selftest_methods": {
            "res://" + MERCENARY_INSTANCE: ["roll_shiny", "roll_player_shiny_flag"],
            "res://" + STAFF_SERVICE: ["roll_fighter_shiny"],
        },
        "edits": [
            Edit(MERCENARY_INSTANCE, "player shiny constant",
                 "const SHINY_ROLL_DENOMINATOR: int = 5000\n",
                 "const SHINY_ROLL_DENOMINATOR: int = 5000\n"
                 "const PLAYER_SHINY_ROLL_DENOMINATOR: int = @PLAYER_DEN@\n", required=True),
            Edit(MERCENARY_INSTANCE, "player shiny roll helper", "", MI_APPENDIX, required=True, append=True),
            # Every player recruit (market, scouting office, reward chests, recruitable champions,
            # tutorial market) is created by CampaignService._create_staff_eligible_recruit -> here.
            Edit(STAFF_SERVICE, "recruit odds (market/scouting/rewards)",
                 "\tvar denominator: int = MercenaryInstance.SHINY_ROLL_DENOMINATOR * precision\n",
                 "\tvar denominator: int = MercenaryInstance.PLAYER_SHINY_ROLL_DENOMINATOR * precision\n",
                 required=False),
            # Starter previews are the player's fighters (the commit keeps these exact instances).
            Edit(TEAM_FOUNDING_SCREEN, "starter odds (preview row)",
                 f"\t\t\tmerc = {VANILLA_NEW_FIGHTER}\n",
                 f"\t\t\tmerc = {PLAYER_NEW_FIGHTER}\n", required=False),
            Edit(TEAM_FOUNDING_SCREEN, "starter odds (champion arrows)",
                 f"\n\tvar merc: = {VANILLA_NEW_FIGHTER}\n",
                 f"\n\tvar merc: = {PLAYER_NEW_FIGHTER}\n", required=False),
        ],
    },
    {
        "id": "slot_picker",
        "title": "[<] Reroll [>] on every starter slot",
        "selftest_methods": {
            "res://" + TEAM_FOUNDING_SCREEN: [
                "_ps_get_slot_pool", "_ps_cycle_slot", "_ps_reroll_slot", "_ps_replace_slot_chip",
                "_ps_wrap_slot_chip", "_ps_handle_slot_shortcut", "_ps_on_nav_repeat_timeout",
            ],
        },
        "edits": [
            Edit(TEAM_FOUNDING_SCREEN, "wrap every slot",
                 "\t\tif is_champion_mode and i == 0:\n"
                 "\t\t\tstarter_roster_row.add_child(_wrap_champion_chip_with_arrows(chip))\n",
                 "\t\tif _ps_is_slot_mode():\n"
                 "\t\t\tstarter_roster_row.add_child(_ps_wrap_slot_chip(chip, i))\n"
                 "\t\telif is_champion_mode and i == 0:\n"
                 "\t\t\tstarter_roster_row.add_child(_wrap_champion_chip_with_arrows(chip))\n", required=True),
            Edit(TEAM_FOUNDING_SCREEN, "slot picker code", "", TFS_APPENDIX, required=True, append=True),
            # Only reuse a kept preview when it is still the same class (vanilla reused by index only).
            # Anchored on the reuse decision itself, so it survives changes to how the game picks
            # which previews to keep (the 2026-09-26 update added preserve_champion before it).
            Edit(TEAM_FOUNDING_SCREEN, "preview reuse by class",
                 "\n\t\tvar reused_preview: bool = merc != null\n",
                 "\n\t\tif merc != null and str(merc.config_id).strip_edges() != config_path.strip_edges():\n"
                 "\t\t\tmerc = null\n"
                 "\t\tvar reused_preview: bool = merc != null\n", required=False),
            # Screen refreshes (language change, returning from popups) keep the rolled fighters.
            # Only safe together with "preview reuse by class", so it is applied after it.
            Edit(TEAM_FOUNDING_SCREEN, "keep previews on refresh",
                 "\t\t\t_rebuild_skipped_intro_preview_row(_editing_founding_setup)\n",
                 "\t\t\t_rebuild_skipped_intro_preview_row(true)\n", required=False),
            Edit(TEAM_FOUNDING_SCREEN, "same-class looks kept on refresh (champion)",
                 "\n\t\t\t_skipped_intro_preview_visual_variants = _apply_visual_variant_lookup(_skipped_intro_preview_configs, lookup)\n",
                 "\n\t\t\t_skipped_intro_preview_visual_variants = _ps_restore_saved_variants(_skipped_intro_preview_configs, save)\n",
                 required=False),
            Edit(TEAM_FOUNDING_SCREEN, "same-class looks kept on refresh (random)",
                 "\n\t\t_skipped_intro_preview_visual_variants = _apply_visual_variant_lookup(_skipped_intro_preview_configs, lookup2)\n",
                 "\n\t\t_skipped_intro_preview_visual_variants = _ps_restore_saved_variants(_skipped_intro_preview_configs, save)\n",
                 required=False),
            Edit(TEAM_FOUNDING_SCREEN, "slot keys 1/2/3",
                 "\tif key.keycode != KEY_LEFT and key.keycode != KEY_RIGHT and key.keycode != KEY_R:\n\t\treturn\n",
                 "\tif _ps_handle_slot_shortcut(key):\n\t\treturn\n"
                 "\tif key.keycode != KEY_LEFT and key.keycode != KEY_RIGHT and key.keycode != KEY_R:\n\t\treturn\n",
                 required=False),
        ],
    },
]
FEATURES.append({
    "id": "champion_trio",
    "title": "Champion Mode starts with three champions",
    # Needs the slot picker: its arrows are what keep the three champions distinct.
    "requires": ["slot_picker"],
    "selftest_methods": {
        "res://" + TEAM_FOUNDING_SCREEN: ["_ps_roll_champion_trio", "_ps_sanitize_champion_trio"],
        "res://" + CAMPAIGN_SERVICE: ["_sanitize_skipped_intro_starter_configs_with_variants", "_is_champion_start_protected_founder"],
    },
    "edits": [
        # The starter commit accepted a champion only in slot 1; now any slot, but never twice.
        # Old 1 champion + 2 fighter lineups still pass.
        Edit(CAMPAIGN_SERVICE, "commit accepts champions in every slot",
             "\t\t\telif is_named_champion or not _is_renown_free_standard_starter_metadata(meta):\n",
             "\t\t\telif (is_named_champion and sanitized_configs.has(config_path)) or "
             "(not is_named_champion and not _is_renown_free_standard_starter_metadata(meta)):\n", required=True),
        Edit(TEAM_FOUNDING_SCREEN, "roll three champions",
             "func _roll_champion_start_preview_configs(keep_champion: bool = false) -> void :\n",
             "func _roll_champion_start_preview_configs(keep_champion: bool = false) -> void :\n"
             "\tif _ps_roll_champion_trio():\n\t\treturn\n", required=True),
        Edit(TEAM_FOUNDING_SCREEN, "restore a saved trio",
             "func _sanitize_champion_start_preview_config_paths(config_paths: Array) -> Array[String]:\n",
             "func _sanitize_champion_start_preview_config_paths(config_paths: Array) -> Array[String]:\n"
             "\tvar ps_trio: Array[String] = _ps_sanitize_champion_trio(config_paths)\n"
             "\tif ps_trio.size() >= 3:\n\t\treturn ps_trio\n", required=True),
        Edit(TEAM_FOUNDING_SCREEN, "trio code", "", TRIO_APPENDIX, required=True, append=True),
        # Season-1 founder protection (no selling/trading/loaning) for all three, not just one.
        # Additive: vanilla's single-id check stays, so failing this edit never protects less.
        Edit(CAMPAIGN_SERVICE, "founder protection for all three",
             "\treturn instance_id == str(current_save.founding_champion_instance_id)\n",
             "\treturn instance_id == str(current_save.founding_champion_instance_id) or _ps_is_founding_champion(instance_id)\n",
             required=False),
        Edit(CAMPAIGN_SERVICE, "founder protection code", "", CS_APPENDIX, required=True, append=True),
        Edit(TEAM_FOUNDING_SCREEN, "Champion Mode description",
             "\tdescription.text = _loc(\"ui.team_founding.starter_choice.\" + _selected_starter_choice_id + \".description\", "
             "str(descriptions.get(_selected_starter_choice_id, \"\")))\n",
             "\tdescription.text = _loc(\"ui.team_founding.starter_choice.\" + _selected_starter_choice_id + \".description\", "
             "str(descriptions.get(_selected_starter_choice_id, \"\")))\n"
             "\tif _selected_starter_choice_id == \"champion_start\":\n"
             "\t\tdescription.text = \"Start with three Champions: pick each one with the arrows. "
             "Rival teams will also get a champion.\"\n", required=False),
    ],
})

# "keep previews on refresh" without the class check could show one class and commit another.
DEPENDS_ON = {"keep previews on refresh": "preview reuse by class"}


def apply_all(sources):
    """Returns (patched {script: text} for scripts with at least one applied edit, report)."""
    texts = dict(sources)
    touched = set()
    report = {"features": {}, "active": []}
    for feature in FEATURES:
        tokens = {"@NEW_FIGHTER@": PLAYER_NEW_FIGHTER if "player_shiny" in report["active"] else VANILLA_NEW_FIGHTER,
                  "@PLAYER_DEN@": str(PLAYER_SHINY_DENOMINATOR)}
        if not ENABLED_FEATURES.get(feature["id"], True):
            report["features"][feature["id"]] = {"title": feature["title"], "active": False,
                                                 "error": "turned off in the options", "optional_off": True}
            continue
        if feature.get("disabled"):
            report["features"][feature["id"]] = {"title": feature["title"], "active": False,
                                                 "error": "disabled: " + feature["disabled"]}
            continue
        missing = [r for r in feature.get("requires", []) if r not in report["active"]]
        if missing:
            report["features"][feature["id"]] = {"title": feature["title"], "active": False,
                                                 "error": "needs feature " + ", ".join(missing)}
            continue
        trial = dict(texts)
        applied, skipped, error = [], [], ""
        for edit in feature["edits"]:
            needed = DEPENDS_ON.get(edit.label)
            if needed and needed not in applied:
                skipped.append(f"{edit.label} (needs '{needed}')")
                continue
            try:
                trial[edit.script] = edit.apply(trial[edit.script], tokens)
                applied.append(edit.label)
            except LookupError as exc:
                if edit.required:
                    error = f"{edit.label}: {exc}"
                    break
                skipped.append(f"{edit.label}: {exc}")
        if error:
            report["features"][feature["id"]] = {"title": feature["title"], "active": False, "error": error}
            continue
        texts = trial
        touched.update(e.script for e in feature["edits"] if e.label in applied)
        report["active"].append(feature["id"])
        report["features"][feature["id"]] = {"title": feature["title"], "active": True, "applied": applied, "skipped": skipped}
    patched = {path: texts[path] for path in TARGETS if path in touched}
    return patched, report


def selftest_methods(report):
    methods = {}
    for feature in FEATURES:
        if feature["id"] in report["active"]:
            for script, names in feature["selftest_methods"].items():
                methods.setdefault(script, []).extend(names)
    return methods


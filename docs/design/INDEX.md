# SW_MUSH Design Document Index

Migrated from the claude.ai Project knowledge base on 2026-06-12. This folder is now the **single source of truth** for design documentation.

## Authority order (when documents conflict)

1. `TODO.json` and `CHANGELOG.md` at the repo root — always authoritative for current state.
2. The most recent `HANDOFF_*` document covering the subsystem.
3. The most recent versioned design doc for the subsystem (`*_v2` beats `*_v1`).
4. `sw_d6_mush_architecture_v51.md` — **known stale**; pending v52 reconciliation. Trust CHANGELOG/TODO over it.

**Excluded from this folder:** `WEG40092.pdf` and `WEG40120.pdf` (West End Games sourcebook PDFs). Keep sourcebook PDFs out of the git repo (size + copyright). If Claude Code needs sourcebook content, the per-book `*_extraction_v1.md` files in this folder are the working references.

## Player-Facing Guides (Guide_01–Guide_26)

- `Guide_01_WEG_D6_Core_Mechanics.md`
- `Guide_02_Character_Creation.md`
- `Guide_03_Ground_Combat.md`
- `Guide_04_Security_Zones.md`
- `Guide_05_Space_Systems.md`
- `Guide_06_Economy.md`
- `Guide_07_Crafting.md`
- `Guide_08_Force_Powers.md`
- `Guide_09_CP_Progression.md`
- `Guide_10_Organizations_Factions.md`
- `Guide_11_Territory_Control.md`
- `Guide_12_Player_Cities.md`
- `Guide_14_Padawan_Master.md`
- `Guide_16_Tutorial_Chains.md`
- `Guide_17_Player_Shops.md`
- `Guide_18_Jedi_Village.md`
- `Guide_19_Medical_Death.md`
- `Guide_20_Scenes_Plots_Places.md`
- `Guide_21_Channels_Mail_News.md`
- `Guide_22_Espionage.md`
- `Guide_23_Sabacc_Entertainer.md`
- `Guide_24_Encounters_Hazards.md`
- `Guide_25_Spacer_Quest.md`
- `Guide_26_Director_AI.md`

## Session Handoffs (chronological record of shipped drops)

- `HANDOFF_ANOMALY_POI_AND_RELAYOUT_TESTS_20260530.md`
- `HANDOFF_MAP_ENV_BEARING_POI_20260530.md`
- `HANDOFF_MAY22_CITIES_PHASE5.md`
- `HANDOFF_OBJECTIVE_AND_VENDOR_POI_20260530.md`
- `HANDOFF_craft_remediation_gundark_dropA_2026-06-10.md`
- `HANDOFF_drop_0a1_smuggling_space_destinations_2026-06-01.md`
- `HANDOFF_drop_1b3_ledger_migration_complete_2026-06-01.md`
- `HANDOFF_drop_1c_finances_throttle_2026-06-02.md`
- `HANDOFF_drop_2_death_reconciliation_2026-06-01.md`
- `HANDOFF_drop_a_realbug_fixes_2026-06-06.md`
- `HANDOFF_drop_cw_era_compliance_space_missions_2026-06-01.md`
- `HANDOFF_drop_vanity_titles_and_commissary_2026-06-03.md`
- `HANDOFF_e3_red_board_remediation_2026-06-04.md`
- `HANDOFF_gcw_reconciliation_and_lane_e1_2026-06-06.md`
- `HANDOFF_gcw_retirement_2026-06-06.md`
- `HANDOFF_lane_d_geonosis_arc_2026-06-07.md`
- `HANDOFF_lane_e2_e3_rollup_2026-06-07.md`
- `HANDOFF_launch_answers_2026-05-31.md`
- `HANDOFF_npc_buyback_crafted_2026-06-02.md`
- `HANDOFF_special_attacks_and_ui_pivot_2026-06-06.md`
- `HANDOFF_suite_triage_fixes_2026-06-05.md`
- `HANDOFF_webify_UI1_thru_UI4b_2026-06-07.md`
- `HANDOFF_webify_UI5_UI6_UI7_2026-06-10.md`
- `HANDOFF_webify_ui_implementation_2026-06-07.md`

## Sourcebook Extractions (WEG → lore/stat mining, re-stat to D6 before use)

- `crackens_rebel_field_guide_extraction_v1.md`
- `creatures_of_the_galaxy_extraction_v1.md`
- `cwcg_extraction_v1.md`
- `geonosis_outer_rim_extraction_v1.md`
- `gg10_bounty_hunters_extraction_v1.md`
- `gg11_criminal_organizations_extraction_v1.md`
- `gg6_tramp_freighters_extraction_v1.md`
- `gg7_mos_eisley_extraction_v1.md`
- `gundarks_personal_gear_extraction_v1.md`
- `hideouts_and_strongholds_extraction_v1.md`
- `jas_extraction_v1.md`
- `jas_extraction_v1_1_appendix.md`
- `platt_smugglers_guide_extraction_v1.md`
- `secrets_of_tatooine_extraction_v1.md`
- `sourcebook_extraction_roadmap_v1.md`
- `totj_extraction_v1.md`
- `world_data_extraction_design_v1.md`
- `wretched_hive_extraction_v1.md`

## Economy (design, audits, hardening, tuning)

- `SW_MUSH_Economy_Audit_FINAL.md`
- `economy_audit_implementation_scorecard_v1.md`
- `economy_audit_v2.md`
- `economy_bulk_premium_design_v1.md`
- `economy_design_v02-1.md`
- `economy_hardening_design_v1.md`
- `economy_tuning_open_questions_v1.md`

## Web Client / UI / UX

- `MAP_NAV_OVERLAY_DROP_20260529.md`
- `Map_Redesign_v2.html`
- `ground_ux_overhaul_design_v1.md`
- `sheet_redesign_design_v1.md`
- `sourcebook_enrichment_roadmap_v1.md`
- `tinymux_comparison_design_v1.md`
- `ui_bugfix_sprint_design_v1.md`
- `web_chargen_design_v1.md`
- `web_client_ux_overhaul_v1.md`
- `web_client_vision_and_protocol_v1_2.md`
- `web_client_vision_and_protocol_v1_3.md`
- `web_client_vision_and_protocol_v1_4.md`
- `web_onboarding_design_v1.md`
- `web_portal_design_v1.md`
- `web_ux_competitive_analysis.md`

## World & Content Design (eras, planets, wilderness, landmarks)

- `clone_wars_director_lore_pivot_design_v1.md`
- `clone_wars_era_design_v3.md`
- `contestable_wilderness_design_v2.md`
- `coruscant_underworld.md`
- `coruscant_underworld_landmarks_design_v1.md`
- `force_resonant_landmarks_design_v1.md`
- `from_dust_to_stars_design_v2_clone_wars.md`
- `hspace_ares_integration_design_v1.md`
- `mos_eisley_tight_seed_RELAYOUT.png`
- `painted_wilderness_and_coruscant_underworld_design_v1.md`
- `space_overhaul_v3_design.md`
- `space_wildspace_design_v1.md`
- `sw_mush_space_guide.md`
- `wilderness_colocation_audit_v1.md`
- `wilderness_design_addendum_evennia_review.md`
- `wilderness_system_design_v1.md`

## Systems Design (combat, factions, housing, crafting, Force, tutorials, etc.)

- `SW_MUSH_Integrated_Game_Design_Report_Phases_1-4_FINAL.md`
- `combat_mechanics_display_design_v1_1.md`
- `combat_posing_narrative_design.md`
- `command_syntax_help_design.md`
- `crafting_integration_design_pass_v1.md`
- `cw_content_gap_design_v1.md`
- `cw_content_gap_design_v1_1_decisions.md`
- `cw_housing_design_v1.md`
- `cw_preflight_checklist_v1_1_update.md`
- `cw_tutorial_chains_design_v1.md`
- `director_ai_design_v1.md`
- `faction_reputation_design_v1.md`
- `field_kit_design_decomposition_v2.md`
- `field_kit_open_questions_v1_1.md`
- `gundark_crafting_integration_design_v1.md`
- `help_rename_design_v1.md`
- `jedi_village_dialogue_authoring_design_v1.md`
- `jedi_village_quest_design_v1.md`
- `ollama_idle_queue_design_v1.md`
- `organizations_factions_design_v1.md`
- `padawan_master_system_design_v1.md`
- `pc_narrative_memory_design_v1.md`
- `player_cities_design_v1_2.md`
- `player_housing_design_v1.md`
- `player_shops_design_v1.md`
- `progression_gates_and_consequences_design_v1.md`
- `security_drop6_territory_control_design_v1.md`
- `security_zones_design_v1.md`
- `sourcebook_mining_crafting_exp_design_v1.md`
- `support_role_buffs_design_v1.md`
- `sw_mush_dual_platform_guide.md`
- `sw_mush_remediation_and_fun_additions_design_v1.md`
- `tutorial_bugfix_design_v1.md`
- `tutorial_factions_addendum_v2.md`
- `tutorial_system_design.md`
- `v7_small_additions_design_v1.md`
- `weight_of_war_design_v1.md`

## Architecture, Protocol & Engineering Standards

- `SMOKE_CI_INTEGRATION_GUIDE.md`
- `db_proxy_design_v1.md`
- `engineering_standards_v1.md`
- `security_model_design_v1.md`
- `smoke_test_harness_design_v1.md`
- `sw_d6_mush_architecture_v50.md`
- `sw_d6_mush_architecture_v51.md`

## Roadmaps, Scorecards & Strategy

- `CLAUDE_DESIGN_BRIEF.md`
- `PROJECT_FILE_PRUNE_LIST_20260530.md`
- `competitive_analysis_feature_designs_v1.md`
- `competitive_analysis_feature_mining_v1.md`
- `comprehensive_design_doc_scorecard_v1.md`
- `field_kit_audit_and_remediation_v1.md`
- `launch_strategy_v1.md`

## Assets & Reference Files

- `SW_MUSH_Systems_Reference.docx`

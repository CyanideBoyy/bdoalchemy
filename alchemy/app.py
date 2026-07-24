"""Alchemy module - main Streamlit entry point.

Two-level model: Harmony → 5 Draughts → 4 Elixirs each → Base ingredients.
Additionally: 4 standalone elixirs tracked separately (not part of Harmony).
Stock is tracked at the elixir level, per blood tier, and per craftable intermediate.
"""

from __future__ import annotations

import streamlit as st

from core.database.database import init_alchemy_db
from core.database.repositories.alchemy_repository import AlchemyRepository
from alchemy.models import (
    ALL_SWAP_GROUPS,
    BLOOD_TYPE_BY_KEY,
    BLOOD_TYPES,
    CRAFTABLES,
    DRAUGHTS,
    STANDALONE_ELIXIRS,
    WEEDS_GROUP,
    Ingredient,
    all_blood_member_keys,
    calculate_materials_needed,
    calculate_standalone_materials_needed,
    explode_to_raw,
)

_alchemy_repo = AlchemyRepository()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_db() -> None:
    if not st.session_state.get("alchemy_db_initialized", False):
        init_alchemy_db()
        st.session_state.alchemy_db_initialized = True


def _load_stock() -> tuple[dict[str, int], dict[str, int], dict[str, int], dict[str, int]]:
    green, blue = _alchemy_repo.get_elixir_stock()
    return (
        green,
        blue,
        _alchemy_repo.get_material_stock(),
        _alchemy_repo.get_draught_stock(),
    )


def _all_non_swap_ingredients() -> list[Ingredient]:
    """Deduplicated non-swap-group, non-craftable ingredients across all elixirs."""
    seen: set[str] = set()
    result: list[Ingredient] = []
    # Harmony draught elixirs
    for draught in DRAUGHTS:
        for elixir in draught.elixirs:
            for ing in elixir.ingredients:
                if (
                    not ing.is_swap_group
                    and ing.key not in CRAFTABLES
                    and ing.key not in seen
                ):
                    seen.add(ing.key)
                    result.append(ing)
    # Standalone elixirs (may have unique ingredients like griffon_claw, fir_sap)
    for elixir in STANDALONE_ELIXIRS:
        for ing in elixir.ingredients:
            if (
                not ing.is_swap_group
                and ing.key not in CRAFTABLES
                and ing.key not in seen
            ):
                seen.add(ing.key)
                result.append(ing)
    return result


def _resolve_display(key: str) -> str:
    """Resolve a display name for any ingredient key."""
    if key in ALL_SWAP_GROUPS:
        return ALL_SWAP_GROUPS[key].display_name
    if key in CRAFTABLES:
        return CRAFTABLES[key].name
    for draught in DRAUGHTS:
        for elixir in draught.elixirs:
            for ing in elixir.ingredients:
                if ing.key == key:
                    return ing.name
    for elixir in STANDALONE_ELIXIRS:
        for ing in elixir.ingredients:
            if ing.key == key:
                return ing.name
    for craftable in CRAFTABLES.values():
        for ing in craftable.ingredients:
            if ing.key == key:
                return ing.name
    return key


def _swap_group_stock(key: str, material_stock: dict[str, int]) -> int:
    """Return stock for a swap group or blood tier key."""
    return material_stock.get(key, 0)


_GROUP_ORDER = {"Mushroom": 0, "Sap": 1, "Powder": 2, "Others": 3}


def _material_group(key: str) -> str:
    """Classify a raw material key into a display group."""
    if key.endswith(("_mushroom", "_mush")):
        return "Mushroom"
    if key.endswith("_sap"):
        return "Sap"
    if key.endswith("_powder") or key == "rifts_dust":
        return "Powder"
    return "Others"


# ---------------------------------------------------------------------------
# Shared number-input stock row
# ---------------------------------------------------------------------------


def _stock_row(
    label: str,
    qty: int,
    widget_key: str,
    max_val: int = 99999,
) -> int | None:
    """Render a name + number_input row. Returns new value if changed, else None."""
    col_name, col_set = st.columns([1, 1])
    col_name.write(label)
    new_val = col_set.number_input(
        "qty",
        min_value=0,
        max_value=max_val,
        value=qty,
        step=1,
        key=widget_key,
        label_visibility="collapsed",
    )
    return int(new_val) if new_val != qty else None


# ---------------------------------------------------------------------------
# UI sections
# ---------------------------------------------------------------------------


def _render_harmony_header() -> int:
    col_title, col_input = st.columns([3, 1])
    with col_title:
        st.title("Alchemy Lab")
        st.caption(
            "Track elixir stock and calculate base materials for Harmony crafting.  \n"
            "1 Harmony = 5 Draughts × 4 Elixirs each (20 elixirs total)."
        )
    with col_input:
        new_count = st.number_input(
            "Harmony Target",
            min_value=0,
            max_value=9999,
            value=st.session_state.harmony_target,
            step=1,
            key="harmony_target_input",
            help="How many Harmonies you want to produce.",
        )
    return int(new_count)

def _render_elixir_stock_editor(
    elixir_stock_green: dict[str, int],
    elixir_stock_blue: dict[str, int],
    harmony_count: int,
) -> None:
    from alchemy.models import ELIXIRS_PER_DRAUGHT

    elixir_target = harmony_count * ELIXIRS_PER_DRAUGHT
    st.subheader("Elixir Stock")
    st.caption(
        f"Set how many of each elixir you currently have.  \n"
        f"Target: **{elixir_target} green** per elixir "
        f"({harmony_count} × {ELIXIRS_PER_DRAUGHT}). "
        "1 blue = 3 green."
    )
    for draught in DRAUGHTS:
        with st.expander(draught.name, expanded=False):
            for elixir in draught.elixirs:
                g = elixir_stock_green.get(elixir.key, 0)
                b = elixir_stock_blue.get(elixir.key, 0)
                total_equiv = g + b * 3
                missing = max(0, elixir_target - total_equiv)
                done = missing == 0
                label = (
                    f"{elixir.name} — **{missing} missing**"
                    if not done
                    else f"{elixir.name} — Done"
                )
                col_name, col_g, col_b = st.columns([2, 1, 1])
                col_name.markdown(
                    f"<span style='font-size:0.9em'>{label}</span>",
                    unsafe_allow_html=True,
                )
                new_g = col_g.number_input(
                    "Green",
                    min_value=0,
                    max_value=9999,
                    value=g,
                    step=1,
                    key=f"elixir_set_{elixir.key}_g",
                    label_visibility="collapsed",
                )
                new_b = col_b.number_input(
                    "Blue",
                    min_value=0,
                    max_value=9999,
                    value=b,
                    step=1,
                    key=f"elixir_set_{elixir.key}_b",
                    label_visibility="collapsed",
                )
                if int(new_g) != g:
                    _alchemy_repo.set_elixir_quantity(elixir.key, int(new_g))
                    st.rerun()
                if int(new_b) != b:
                    _alchemy_repo.set_elixir_blue_quantity(elixir.key, int(new_b))
                    st.rerun()


def _render_standalone_elixir_stock_editor(
    elixir_stock_green: dict[str, int],
    elixir_stock_blue: dict[str, int],
    harmony_count: int,
) -> None:
    """Stock editor for standalone elixirs (not part of any Draught)."""
    from alchemy.models import ELIXIRS_PER_DRAUGHT

    target = harmony_count * ELIXIRS_PER_DRAUGHT
    st.subheader("Other Elixirs")
    st.caption(
        f"Target: **{target} green** per elixir. "
        "1 blue = 3 green."
    )
    for elixir in STANDALONE_ELIXIRS:
        g = elixir_stock_green.get(elixir.key, 0)
        b = elixir_stock_blue.get(elixir.key, 0)
        total_equiv = g + b * 3
        missing = max(0, target - total_equiv)
        done = missing == 0
        label = (
            f"{elixir.name} — **{missing} missing**"
            if not done
            else f"{elixir.name} — Done"
        )
        col_name, col_g, col_b = st.columns([2, 1, 1])
        col_name.markdown(
            f"<span style='font-size:0.9em'>{label}</span>",
            unsafe_allow_html=True,
        )
        new_g = col_g.number_input(
            "G",
            min_value=0,
            max_value=9999,
            value=g,
            step=1,
            key=f"aelixir_set_{elixir.key}_g",
            label_visibility="collapsed",
        )
        new_b = col_b.number_input(
            "B",
            min_value=0,
            max_value=9999,
            value=b,
            step=1,
            key=f"aelixir_set_{elixir.key}_b",
            label_visibility="collapsed",
        )
        if int(new_g) != g:
            _alchemy_repo.set_elixir_quantity(elixir.key, int(new_g))
            st.rerun()
        if int(new_b) != b:
            _alchemy_repo.set_elixir_blue_quantity(elixir.key, int(new_b))
            st.rerun()


def _render_material_stock_editor(material_stock: dict[str, int]) -> None:
    """Stock editor sections: raw ingredients, craftable intermediates, blood tiers, weeds."""
    st.subheader("Material Stock")
    st.caption("Set how much of each ingredient you have on hand.")

    # --- 1-3. All raw + craftable + sub-material ingredients grouped by category ---
    all_ings = _all_non_swap_ingredients()
    all_ing_keys: set[str] = {ing.key for ing in all_ings}

    # Collect sub-ingredients of craftables that aren't already in all_ings
    sub_seen: set[str] = set()
    for craftable in CRAFTABLES.values():
        for ing in craftable.ingredients:
            if (
                not ing.is_swap_group
                and ing.key not in CRAFTABLES
                and ing.key not in sub_seen
                and ing.key not in all_ing_keys
            ):
                sub_seen.add(ing.key)
                all_ings.append(ing)
                all_ing_keys.add(ing.key)

    # Blood craftable keys — excluded from Craftables group, handled in Blood section.
    _blood_craftable_keys = {
        "clown_blood",
        "sinners_blood",
        "tyrant_blood",
        "divine_beast_blood",
        "wise_man_blood",
    }

    grouped: dict[str, list] = {
        "Mushroom": [],
        "Sap": [],
        "Powder": [],
        "Craftables": [],
        "Others": [],
    }
    for ing in all_ings:
        grouped[_material_group(ing.key)].append(ing)
    for craftable in CRAFTABLES.values():
        if craftable.key not in _blood_craftable_keys:
            grouped["Craftables"].append(craftable)

    for group_name in ("Mushroom", "Sap", "Powder", "Craftables", "Others"):
        members = grouped[group_name]
        if not members:
            continue
        with st.expander(f"{group_name} ({len(members)})", expanded=False):
            for item in members:
                qty = material_stock.get(item.key, 0)
                new_val = _stock_row(item.name, qty, f"mat_set_{item.key}")
                if new_val is not None:
                    _alchemy_repo.set_material_quantity(item.key, new_val)
                    st.rerun()

    # --- 4. Blood (all groups in one expander) ---
    used_blood_keys: set[str] = set()
    for draught in DRAUGHTS:
        for elixir in draught.elixirs:
            for ing in elixir.ingredients:
                if ing.is_blood_type:
                    used_blood_keys.add(ing.blood_type_key)
    for craftable in CRAFTABLES.values():
        for ing in craftable.ingredients:
            if ing.is_blood_type:
                used_blood_keys.add(ing.blood_type_key)
    for elixir in STANDALONE_ELIXIRS:
        for ing in elixir.ingredients:
            if ing.is_blood_type:
                used_blood_keys.add(ing.blood_type_key)

    blood_craftables = [CRAFTABLES[k] for k in _blood_craftable_keys if k in CRAFTABLES]
    blood_raw = [bt for bt in BLOOD_TYPES if bt.key in used_blood_keys]
    total_blood = len(blood_craftables) + len(blood_raw)

    with st.expander(f"Blood ({total_blood})", expanded=False):
        if blood_craftables:
            st.caption("Craftable")
            for item in blood_craftables:
                qty = material_stock.get(item.key, 0)
                new_val = _stock_row(item.name, qty, f"mat_set_{item.key}")
                if new_val is not None:
                    _alchemy_repo.set_material_quantity(item.key, new_val)
                    st.rerun()
        for bt in blood_raw:
            tier_num = bt.key.replace("blood_t", "")
            st.caption(f"Group {tier_num}")
            qty = material_stock.get(bt.key, 0)
            col_name, col_set = st.columns([1, 1])
            col_name.write(bt.display_name)
            col_name.caption(bt.tooltip, help=None)
            new_val = col_set.number_input(
                "qty",
                min_value=0,
                max_value=99999,
                value=qty,
                step=1,
                key=f"mat_set_{bt.key}",
                label_visibility="collapsed",
            )
            if int(new_val) != qty:
                _alchemy_repo.set_material_quantity(bt.key, int(new_val))
                st.rerun()

    # --- 5. Weeds ---
    with st.expander(f"Weeds (1)", expanded=False):
        wg_qty = material_stock.get(WEEDS_GROUP.key, 0)
        new_val = _stock_row(
            WEEDS_GROUP.display_name,
            wg_qty,
            f"mat_set_{WEEDS_GROUP.key}",
        )
        if new_val is not None:
            _alchemy_repo.set_material_quantity(WEEDS_GROUP.key, new_val)
            st.rerun()


def _render_draught_stock_editor(draught_stock: dict[str, int]) -> None:
    """One stock row per draught showing current inventory on hand."""
    st.subheader("Draught Stock")
    st.caption("Set how many of each draught you currently have on hand.")
    for draught in DRAUGHTS:
        qty = draught_stock.get(draught.key, 0)
        new_val = _stock_row(
            draught.name, qty, f"draught_set_{draught.key}", max_val=9999
        )
        if new_val is not None:
            _alchemy_repo.set_draught_quantity(draught.key, new_val)
            st.rerun()


def _render_recipe_cards(
    harmony_count: int,
    elixir_stock: dict[str, int],
    elixir_stock_blue: dict[str, int],
    material_stock: dict[str, int],
    draught_stock: dict[str, int],
) -> None:
    st.divider()

    per_elixir, totals = calculate_materials_needed(
        harmony_count, elixir_stock, elixir_stock_blue, material_stock, draught_stock
    )

    # --- Intermediate recipe cards (priority: show before elixir cards) ---
    _per_elixir_raw, all_totals = calculate_materials_needed(
        harmony_count, elixir_stock, elixir_stock_blue, material_stock, draught_stock
    )
    _raw, crafted_totals = explode_to_raw(all_totals, material_stock)

    # Also gather standalone totals for intermediate calculation
    standalone_info = calculate_standalone_materials_needed(
        harmony_count, elixir_stock, elixir_stock_blue
    )
    standalone_totals: dict[str, int] = {}
    for info in standalone_info.values():
        for k, v in info["materials"].items():
            standalone_totals[k] = standalone_totals.get(k, 0) + v
    _raw_sa, crafted_totals_sa = explode_to_raw(standalone_totals, material_stock)
    for k, v in crafted_totals_sa.items():
        crafted_totals[k] = crafted_totals.get(k, 0) + v

    if crafted_totals:
        st.subheader("Intermediates to Craft")
        int_cols = st.columns(min(len(crafted_totals), 4))
        col_idx = 0
        for craftable_key, to_craft in sorted(
            crafted_totals.items(), key=lambda x: -x[1]
        ):
            craftable = CRAFTABLES.get(craftable_key)
            if craftable is None:
                continue
            have = material_stock.get(craftable_key, 0)
            with int_cols[col_idx % len(int_cols)]:
                with st.container(border=True):
                    st.markdown(f"**{craftable.name}**")
                    st.markdown(f"**{to_craft} to craft** (have {have})")
                    st.divider()
                    for ing in craftable.ingredients:
                        need = ing.quantity * to_craft
                        if ing.is_swap_group:
                            have_ing = _swap_group_stock(ing.key, material_stock)
                            label = ing.name
                            help_text = ALL_SWAP_GROUPS[ing.swap_group_key].tooltip
                        else:
                            have_ing = material_stock.get(ing.key, 0)
                            label = ing.name
                            help_text = None
                        short = max(0, need - have_ing)
                        icon = "🔴" if short > 0 else "🟢"
                        qty = ing.quantity
                        st.markdown(
                            f"{icon} {label} x{qty}  \nNeed {need} / Have {have_ing}"
                            + (f" / **Short {short}**" if short > 0 else ""),
                            help=help_text,
                        )
            col_idx += 1

    # --- Elixir recipe cards (skip Done elixirs) ---
    st.subheader("Recipes")

    for draught in DRAUGHTS:
        draught_done = all(
            per_elixir[e.key]["elixir_missing"] == 0 for e in draught.elixirs
        )
        if draught_done:
            continue

        st.markdown(f"**{draught.name}**")

        pending_elixirs = [
            e for e in draught.elixirs if per_elixir[e.key]["elixir_missing"] > 0
        ]
        cols = st.columns(min(len(pending_elixirs), 4))
        for col, elixir in zip(cols, pending_elixirs):
            info = per_elixir[elixir.key]
            elixir_missing = info["elixir_missing"]
            elixir_target = info["elixir_target"]
            mat_needs = info["materials"]
            stock_g = info.get("stock_green", elixir_stock.get(elixir.key, 0))
            stock_b = info.get("stock_blue", elixir_stock_blue.get(elixir.key, 0))

            with col:
                with st.container(border=True):
                    st.markdown(f"**{elixir.name}**")
                    st.markdown(f"**{elixir_missing} missing**")
                    st.caption(f"Stock: {stock_g}g + {stock_b}b / {elixir_target}g")

                    st.divider()

                    for ing in elixir.ingredients:
                        need = mat_needs.get(ing.key, 0)
                        if need == 0:
                            continue

                        if ing.is_swap_group:
                            sg = ALL_SWAP_GROUPS[ing.swap_group_key]
                            have = _swap_group_stock(ing.key, material_stock)
                            label = ing.name
                            help_text = sg.tooltip if ing.is_blood_type else None
                        else:
                            have = material_stock.get(ing.key, 0)
                            label = ing.name
                            help_text = None

                        short = max(0, need - have)
                        icon = "🔴" if short > 0 else "🟢"
                        qty = ing.quantity
                        st.markdown(
                            f"{icon} {label} x{qty}  \nNeed {need} / Have {have}"
                            + (f" / **Short {short}**" if short > 0 else ""),
                            help=help_text,
                        )

        st.write("")

    # --- Standalone elixir cards ---
    standalone_pending = [
        e for e in STANDALONE_ELIXIRS if standalone_info[e.key]["elixir_missing"] > 0
    ]
    if standalone_pending:
        st.markdown("**Other Elixirs**")
        cols = st.columns(min(len(standalone_pending), 4))
        for col, elixir in zip(cols, standalone_pending):
            info = standalone_info[elixir.key]
            missing = info["elixir_missing"]
            target = info["elixir_target"]
            mat_needs = info["materials"]
            stock_g = info.get("stock_green", elixir_stock.get(elixir.key, 0))
            stock_b = info.get("stock_blue", elixir_stock_blue.get(elixir.key, 0))

            with col:
                with st.container(border=True):
                    st.markdown(f"**{elixir.name}**")
                    st.markdown(f"**{missing} missing**")
                    st.caption(f"Stock: {stock_g}g + {stock_b}b / {target}g")
                    st.divider()

                    for ing in elixir.ingredients:
                        need = mat_needs.get(ing.key, 0)
                        if need == 0:
                            continue
                        if ing.is_swap_group:
                            sg = ALL_SWAP_GROUPS[ing.swap_group_key]
                            have = _swap_group_stock(ing.key, material_stock)
                            label = ing.name
                            help_text = sg.tooltip if ing.is_blood_type else None
                        else:
                            have = material_stock.get(ing.key, 0)
                            label = ing.name
                            help_text = None
                        short = max(0, need - have)
                        icon = "🔴" if short > 0 else "🟢"
                        qty = ing.quantity
                        st.markdown(
                            f"{icon} {label} x{qty}  \nNeed {need} / Have {have}"
                            + (f" / **Short {short}**" if short > 0 else ""),
                            help=help_text,
                        )


def _render_totals(
    harmony_count: int,
    elixir_stock: dict[str, int],
    elixir_stock_blue: dict[str, int],
    material_stock: dict[str, int],
    draught_stock: dict[str, int],
) -> None:
    """Two tables: direct ingredient needs, then fully-exploded raw material needs."""
    _per_elixir, totals = calculate_materials_needed(
        harmony_count, elixir_stock, elixir_stock_blue, material_stock, draught_stock
    )

    # Merge standalone elixir totals
    standalone_info = calculate_standalone_materials_needed(
        harmony_count, elixir_stock, elixir_stock_blue
    )
    for info in standalone_info.values():
        for k, v in info["materials"].items():
            totals[k] = totals.get(k, 0) + v

    if not any(v > 0 for v in totals.values()):
        st.success("All elixirs are fully stocked for the target Harmony count.")
        return

    import pandas as pd

    # --- Table 1: direct ingredient needs ---
    st.subheader("Ingredients Needed")
    rows = []
    for key, need in totals.items():
        if need == 0:
            continue
        have = _swap_group_stock(key, material_stock)
        short = max(0, need - have)
        rows.append(
            {
                "Group": _material_group(key),
                "Ingredient": _resolve_display(key),
                "Need": need,
                "Have": have,
                "Short": short,
            }
        )
    if rows:
        df = pd.DataFrame(rows)
        df["_order"] = df["Group"].map(_GROUP_ORDER)
        df = df.sort_values(["_order", "Short"], ascending=[True, False]).drop(
            columns="_order"
        )
        st.dataframe(df, hide_index=True, width="stretch")

    # --- Table 2: exploded raw materials ---
    raw_totals, crafted_totals = explode_to_raw(totals, material_stock)

    if crafted_totals:
        st.subheader("Intermediates to Craft")
        craft_rows = [
            {"Item": _resolve_display(k), "To Craft": v}
            for k, v in sorted(crafted_totals.items(), key=lambda x: -x[1])
        ]
        st.dataframe(pd.DataFrame(craft_rows), hide_index=True, width="stretch")

    if raw_totals:
        st.subheader("Raw Materials Needed")
        raw_rows = []
        for key, need in raw_totals.items():
            have = _swap_group_stock(key, material_stock)
            short = max(0, need - have)
            if short == 0:
                continue
            raw_rows.append(
                {
                    "Group": _material_group(key),
                    "Material": _resolve_display(key),
                    "Need": need,
                    "Have": have,
                    "Short": short,
                }
            )
        if raw_rows:
            df_raw = pd.DataFrame(raw_rows)
            df_raw["_order"] = df_raw["Group"].map(_GROUP_ORDER)
            df_raw = df_raw.sort_values(
                ["_order", "Short"], ascending=[True, False]
            ).drop(columns="_order")
            st.dataframe(df_raw, hide_index=True, width="stretch")
        else:
            st.success("All raw materials are covered by current stock.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_alchemy() -> None:
    _init_db()

    if "harmony_target" not in st.session_state:
        st.session_state.harmony_target = 10

    (
        elixir_stock_green,
        elixir_stock_blue,
        material_stock,
        draught_stock,
    ) = _load_stock()

    harmony_count = _render_harmony_header()
    if harmony_count != st.session_state.harmony_target:
        st.session_state.harmony_target = harmony_count

    st.divider()

    left, right = st.columns([2, 2], gap="large")
    with left:
        tab_elixirs, tab_standalone, tab_draughts, tab_materials = st.tabs(
            ["Elixir Stock", "Other Elixirs", "Draught Stock", "Material Stock"]
        )
        with tab_elixirs:
            _render_elixir_stock_editor(elixir_stock_green, elixir_stock_blue, harmony_count)
        with tab_standalone:
            _render_standalone_elixir_stock_editor(elixir_stock_green, elixir_stock_blue, harmony_count)
        with tab_draughts:
            _render_draught_stock_editor(draught_stock)
        with tab_materials:
            _render_material_stock_editor(material_stock)

    with right:
        _render_totals(harmony_count, elixir_stock_green, elixir_stock_blue, material_stock, draught_stock)

    _render_recipe_cards(harmony_count, elixir_stock_green, elixir_stock_blue, material_stock, draught_stock)

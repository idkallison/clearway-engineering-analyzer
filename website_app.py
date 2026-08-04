from pathlib import Path

import pandas as pd
import streamlit as st

import breakdown_helpers as break_h
import csv_reading_helpers as csv_h
import labor_types as lt_h
import pipeline_helpers as pipe_h
import project_grouping_helpers as proj_h
import task_map_helpers as task_h


# =========================================================
# Website
# =========================================================
#
# This file is UI-only: file uploaders, buttons, tables, and the
# chart. The actual analysis (reading CSVs, matching Labor Types,
# building the summary table, building the PDF) lives in
# pipeline_helpers.run_analysis so it can be tested/reused without
# Streamlit.


st.set_page_config(
    page_title="Clearway Labor Analyzer",
    page_icon="📊",
    layout="wide",
)


st.title("📊 Clearway Labor Analyzer")


# ---------------------------------------------------------
# Master task map (optional, applies to both modes below)
# ---------------------------------------------------------

st.subheader("🗂️ Master Task Map (optional)")

st.caption(
    "Upload a CSV that lists every task/service name and the Labor "
    "Type it should map to (columns like 'Task' or "
    "'Product/Service Name' plus a 'Labor Type' column). Use one of "
    "the built-in categories -- Engineering, Programming, Assembly - "
    "Electrical, Assembly - Mechanical, Admin, Installation, "
    "Pre-Sale, Non-Project -- or type your own new category name to "
    "track something separately. If provided, exact matches here "
    "override the built-in matching rules. If left empty, the app "
    "uses its existing built-in rules only."
)

task_map_file = st.file_uploader(
    "Master Task Map CSV",
    type="csv",
    key="task_map_upload",
)

task_map = {}

if task_map_file:
    try:
        # load_task_map also reports back any Labor Type values that
        # weren't one of the 9 built-ins, so the user can confirm a
        # new category was picked up rather than a typo.
        task_map, new_categories = task_h.load_task_map(task_map_file)

        success_message = (
            f"Loaded {len(task_map)} task mappings from the master "
            "task map."
        )

        if new_categories:
            success_message += (
                " New categories added: " + ", ".join(new_categories)
            )

        st.success(success_message)
    except Exception as error:
        st.error(f"Could not read the master task map: {error}")
        task_map = {}

st.divider()


# ---------------------------------------------------------
# Mode selection
# ---------------------------------------------------------

mode = st.radio(
    "How do you want to upload files?",
    [
        "Single project — drop the Labor CSV and Estimate CSV",
        "Multiple projects — drop a whole folder of CSVs at once",
    ],
)

st.divider()


# ---------------------------------------------------------
# Results rendering (shared by both modes below)
# ---------------------------------------------------------

def render_results(result, project_name):
    st.divider()
    st.subheader(f"📋 Project Summary — {project_name}")

    c1, c2, c3 = st.columns(3)

    c1.metric("Quoted Hours", f"{result['total_quote']:.2f}")
    c2.metric("Actual Hours", f"{result['total_actual']:.2f}")
    c3.metric(
        "Remaining Hours",
        f"{result['total_quote'] - result['total_actual']:.2f}",
    )

    st.caption("Remaining Hours = Quoted Hours - Actual Hours")

    st.divider()
    st.subheader("📊 Quote vs Actual")
    st.caption(
        "Click a row to see the individual tasks behind its numbers."
    )

    column_widths = [0.6, 3, 2, 2, 2]

    header_cols = st.columns(column_widths)
    header_cols[1].markdown("**Labor Type**")
    header_cols[2].markdown("**Quoted Hours**")
    header_cols[3].markdown("**Actual Hours**")
    header_cols[4].markdown("**Remaining Hours**")

    # results_df is already sorted (built-ins in a fixed order, then
    # any custom categories, then Other/Unmapped last) by
    # pipeline_helpers.run_analysis, so rows just render top-to-bottom
    # as-is.
    for _, row in result["results_df"].iterrows():
        labor_type = row["Labor Type"]
        display_label = lt_h.display_label(labor_type)
        toggle_key = f"row_open_{project_name}_{labor_type}"

        if toggle_key not in st.session_state:
            st.session_state[toggle_key] = False

        with st.container(border=True):
            row_cols = st.columns(column_widths)

            icon = "▾" if st.session_state[toggle_key] else "▸"

            if row_cols[0].button(icon, key=f"btn_{toggle_key}"):
                st.session_state[toggle_key] = (
                    not st.session_state[toggle_key]
                )

            row_cols[1].markdown(f"**{display_label}**")
            row_cols[2].write(f"{row['Quoted Hours']:.2f}")
            row_cols[3].write(f"{row['Actual Hours']:.2f}")
            row_cols[4].write(f"{row['Remaining Hours']:.2f}")

            # Expanded row: show the individual tasks behind this
            # Labor Type's numbers.
            if st.session_state[toggle_key]:
                breakdown_df, quoted_row_count = (
                    break_h.build_task_breakdown(
                        result["labor_df"],
                        result["estimate_rows"],
                        labor_type,
                    )
                )

                if breakdown_df.empty:
                    st.caption(
                        "No individual task data found for this "
                        "labor type."
                    )
                elif (
                    0 < quoted_row_count < len(breakdown_df)
                ):
                    # Split into a "has a quote" table and an
                    # "actual-only" table, with a clear line between
                    # them, instead of one table where the two groups
                    # are only distinguishable by scanning values.
                    st.dataframe(
                        breakdown_df.iloc[:quoted_row_count],
                        hide_index=True,
                        use_container_width=True,
                    )
                    st.markdown(
                        "<hr style='margin:2px 0 8px 0; "
                        "border:none; border-top:3px solid "
                        "#555;'>",
                        unsafe_allow_html=True,
                    )
                    st.dataframe(
                        breakdown_df.iloc[quoted_row_count:],
                        hide_index=True,
                        use_container_width=True,
                    )
                else:
                    st.dataframe(
                        breakdown_df,
                        hide_index=True,
                        use_container_width=True,
                    )

    st.divider()
    st.subheader("📈 Labor Comparison")

    # Same row order and "Other/Unmapped" label as the table above and
    # the PDF's chart, so all three surfaces always agree.
    chart_df = result["results_df"][
        ["Labor Type", "Quoted Hours", "Actual Hours"]
    ].copy()

    chart_df["Labor Type"] = chart_df["Labor Type"].apply(
        lt_h.display_label
    )

    chart_height = max(400, 70 * len(chart_df) + 150)

    st.bar_chart(
        chart_df,
        x="Labor Type",
        y=["Quoted Hours", "Actual Hours"],
        horizontal=True,
        height=chart_height,
    )

    st.divider()
    st.subheader("🔍 File Diagnostics")

    st.write(
        "Labor header detected on CSV row "
        f"{result['labor_header_row'] + 1}."
    )

    st.write(
        "Estimate header detected on CSV row "
        f"{result['estimate_header_row'] + 1}."
    )

    st.write(
        "Estimate format detected:",
        (
            "Old template with Labor Type"
            if "Labor Type" in result["estimate_df"].columns
            else "New template with sections and Level of experience"
        ),
    )

    st.divider()
    st.subheader("📄 Export Report")

    st.download_button(
        label="📥 Download PDF Report",
        data=result["pdf_data"],
        file_name=f"{project_name} - Labor Report.pdf",
        mime="application/pdf",
        use_container_width=True,
        key=f"download_{project_name}",
    )


# ---------------------------------------------------------
# Mode 1: single project, one combined uploader
# ---------------------------------------------------------

if mode.startswith("Single"):
    st.write(
        "Drag and drop both the Labor CSV and the Estimate CSV below, "
        "in any order."
    )

    uploaded_files = st.file_uploader(
        "📄 Labor + Estimate CSVs",
        type="csv",
        accept_multiple_files=True,
        key="single_mode_upload",
    )

    if uploaded_files:
        if len(uploaded_files) != 2:
            st.warning(
                "Drop exactly two files here: one Labor CSV and one "
                "Estimate CSV."
            )
        else:
            labor_file = None
            estimate_file = None
            unrecognized = []

            # Auto-detect which of the two files is which by checking
            # for each format's required header columns.
            for uploaded_file in uploaded_files:
                file_type, _, _ = csv_h.detect_uploaded_file_type(
                    uploaded_file
                )

                if file_type == "labor":
                    labor_file = uploaded_file
                elif file_type == "estimate":
                    estimate_file = uploaded_file
                else:
                    unrecognized.append(uploaded_file.name)

            if unrecognized:
                st.error(
                    "Could not identify these as a Labor or Estimate "
                    "CSV: " + ", ".join(unrecognized)
                )
            elif not labor_file or not estimate_file:
                st.error(
                    "Need one Labor CSV and one Estimate CSV. Found: "
                    f"Labor {'✅' if labor_file else '❌'}, "
                    f"Estimate {'✅' if estimate_file else '❌'}"
                )
            else:
                if st.button(
                    "🚀 Analyze Project",
                    use_container_width=True,
                    type="primary",
                ):
                    try:
                        project_name = Path(labor_file.name).stem
                        result = pipe_h.run_analysis(
                            labor_file,
                            estimate_file,
                            task_map,
                            project_name,
                        )
                        st.session_state["single_result"] = (
                            project_name,
                            result,
                        )
                    except Exception as error:
                        st.error(
                            f"Could not analyze the files: {error}"
                        )

    if "single_result" in st.session_state:
        project_name, result = st.session_state["single_result"]
        render_results(result, project_name)


# ---------------------------------------------------------
# Mode 2: multiple projects, bulk uploader + grouping
# ---------------------------------------------------------

else:
    st.write(
        "Drag and drop every CSV from your project folders — Labor "
        "and Estimate files for multiple projects, in any order. The "
        "app will group them into projects automatically."
    )

    uploaded_files = st.file_uploader(
        "📁 All project CSVs",
        type="csv",
        accept_multiple_files=True,
        key="multi_mode_upload",
    )

    if uploaded_files:
        file_lookup = {
            uploaded_file.name: uploaded_file
            for uploaded_file in uploaded_files
        }

        # Best-effort grouping by filename -- the editable table below
        # lets the user fix any mis-grouping by hand.
        suggested_groups = proj_h.group_files_into_projects(
            list(file_lookup.keys())
        )

        filename_to_project = {}
        for project_name, filenames in suggested_groups.items():
            for filename in filenames:
                filename_to_project[filename] = project_name

        review_rows = []

        for filename, uploaded_file in file_lookup.items():
            file_type, _, _ = csv_h.detect_uploaded_file_type(
                uploaded_file
            )

            review_rows.append(
                {
                    "File": filename,
                    "Detected Type": file_type or "Unrecognized",
                    "Project": filename_to_project.get(
                        filename, "Project"
                    ),
                }
            )

        review_df = pd.DataFrame(review_rows)

        st.write(
            "Review the detected type and project grouping below, "
            "and correct anything that looks wrong before generating "
            "reports."
        )

        edited_df = st.data_editor(
            review_df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Detected Type": st.column_config.SelectboxColumn(
                    options=["labor", "estimate", "Unrecognized"],
                ),
                "Project": st.column_config.TextColumn(),
            },
            key="file_review_editor",
        )

        st.divider()
        st.subheader("📁 Projects Found")

        # Re-derive project -> {labor file, estimate file} from the
        # (possibly user-edited) review table.
        projects = {}

        for _, row in edited_df.iterrows():
            project_name = str(row["Project"]).strip() or "Project"
            projects.setdefault(
                project_name, {"labor": None, "estimate": None}
            )

            if row["Detected Type"] == "labor":
                projects[project_name]["labor"] = row["File"]
            elif row["Detected Type"] == "estimate":
                projects[project_name]["estimate"] = row["File"]

        if not projects:
            st.info("No files uploaded yet.")

        for project_name, files in sorted(projects.items()):
            has_labor = files["labor"] is not None
            has_estimate = files["estimate"] is not None

            with st.container(border=True):
                st.markdown(f"**{project_name}**")

                status_cols = st.columns(2)

                status_cols[0].write(
                    "Labor CSV: "
                    + (
                        f"✅ {files['labor']}"
                        if has_labor
                        else "❌ Missing"
                    )
                )

                status_cols[1].write(
                    "Estimate CSV: "
                    + (
                        f"✅ {files['estimate']}"
                        if has_estimate
                        else "❌ Missing"
                    )
                )

                if has_labor and has_estimate:
                    if st.button(
                        f"🚀 Generate Report — {project_name}",
                        key=f"generate_{project_name}",
                    ):
                        try:
                            result = pipe_h.run_analysis(
                                file_lookup[files["labor"]],
                                file_lookup[files["estimate"]],
                                task_map,
                                project_name,
                            )
                            st.session_state[
                                f"result_{project_name}"
                            ] = result
                        except Exception as error:
                            st.error(
                                f"Could not analyze {project_name}: "
                                f"{error}"
                            )
                else:
                    st.info(
                        "Both a Labor CSV and an Estimate CSV are "
                        "needed before a report can be generated for "
                        "this project."
                    )

                if f"result_{project_name}" in st.session_state:
                    render_results(
                        st.session_state[f"result_{project_name}"],
                        project_name,
                    )

from pathlib import Path

import pandas as pd
import streamlit as st

import csv_reading_helpers as csv_h
import estimate_helpers as est_h
import labor_helpers as lab_h
import pdf_helper as pdf_h
import project_grouping_helpers as proj_h
import task_map_helpers as task_h



# =========================================================
# Website
# =========================================================


st.set_page_config(
    page_title="Clearway Labor Analyzer",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Clearway Labor Analyzer")


# Master task map (optional, applies to both modes below)

st.subheader("🗂️ Master Task Map (optional)")
st.caption(
    "Upload CSV file that lists every task/service name and the labor "
    "type it should map to"
)

task_map_file = st.file_uploader(
    "Master Task Map CSV",
    type="csv",
    key="task_map_upload",
)

task_map = {}

if task_map_file:
    try:
        task_map = task_h.load_task_map(task_map_file)
        st.success(
            f"Loaded {len(task_map)} task mappings from the master "
            "task map."
        )
    except Exception as error:
        st.error(f"Could not read the master task map: {error}")
        task_map = {}

st.divider()


# Mode selection
mode = st.radio(
    "How do you want to upload files?",
    [
        "Single project — drag and drop the Labor CSV and Estimate CSV for a single project",
        "Multiple projects — drag and drop a the CSV files of mutiple projects at once",
    ],
)

st.divider()

# Shared analysis logic

def run_analysis(labor_file, estimate_file, task_map, project_name):
    """
    Runs the full Labor-vs-Estimate analysis pipeline for one project
    and returns a dict of everything needed to render the results and
    build the PDF report.
    """
    labor_df, labor_header_row = csv_h.read_csv_with_detected_header(
        labor_file,
        csv_h.LABOR_REQUIRED_COLUMNS,
    )

    estimate_df, estimate_header_row = (
        csv_h.read_csv_with_detected_header(
            estimate_file,
            csv_h.ESTIMATE_REQUIRED_COLUMNS,
        )
    )

    missing_labor = (
        csv_h.LABOR_REQUIRED_COLUMNS - set(labor_df.columns)
    )

    if missing_labor:
        raise ValueError(
            "Labor CSV is missing: " + ", ".join(sorted(missing_labor))
        )

    labor_df = labor_df[
        labor_df["Activity date"].notna()
        & labor_df["Activity date"].astype(str).str.strip().ne("")
    ].copy()

    labor_df["Service"] = (
        labor_df["Product/Service full name"]
        .apply(lab_h.clean_service_name)
    )

    labor_df["Hours"] = (
        labor_df["Duration"].apply(lab_h.duration_to_hours)
    )

    labor_df["Labor Type"] = (
        labor_df["Service"]
        .apply(lambda service: lab_h.map_service(service, task_map))
    )

    actual_hours = labor_df.groupby("Labor Type")["Hours"].sum()

    estimate_rows = est_h.prepare_estimate_dataframe(
        estimate_df,
        task_map=task_map,
    )

    estimated_hours = (
        estimate_rows
        .groupby("Normalized Labor Type")["Required Hrs"]
        .sum()
    )

    labor_types = sorted(
        set(actual_hours.index).union(set(estimated_hours.index))
    )

    results = []
    total_quote = 0.0
    total_actual = 0.0

    for labor_type in labor_types:
        quoted = float(estimated_hours.get(labor_type, 0))
        actual = float(actual_hours.get(labor_type, 0))

        total_quote += quoted
        total_actual += actual

        results.append(
            {
                "Labor Type": labor_type,
                "Quoted Hours": round(quoted, 2),
                "Actual Hours": round(actual, 2),
                "Remaining Hours": round(quoted - actual, 2),
            }
        )

    results_df = pd.DataFrame(results)

    unmapped_services = (
        labor_df[labor_df["Labor Type"] == "Other"]["Service"]
        .value_counts()
        .rename_axis("Service")
        .reset_index(name="Occurrences")
    )

    review_rows = estimate_rows[
        estimate_rows["Normalized Labor Type"].eq("Other")
    ].copy()

    pdf_data = pdf_h.make_pdf(
        results_df=results_df,
        total_quote=total_quote,
        total_actual=total_actual,
        unmapped_services=unmapped_services,
        review_rows=review_rows,
        project_name=project_name,
    )

    return {
        "results_df": results_df,
        "unmapped_services": unmapped_services,
        "review_rows": review_rows,
        "total_quote": total_quote,
        "total_actual": total_actual,
        "pdf_data": pdf_data,
        "labor_header_row": labor_header_row,
        "estimate_header_row": estimate_header_row,
        "estimate_df": estimate_df,
    }


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

    st.dataframe(
        result["results_df"],
        hide_index=True,
        use_container_width=True,
    )

    st.divider()
    st.subheader("📈 Labor Comparison")

    chart_df = result["results_df"].set_index("Labor Type")[
        ["Quoted Hours", "Actual Hours"]
    ]

    st.bar_chart(chart_df)

    diagnostics_tab, review_tab = st.tabs(
        ["File Diagnostics", "Mapping Review"]
    )

    with diagnostics_tab:
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
                else (
                    "New template with sections and Level of "
                    "experience"
                )
            ),
        )

    with review_tab:
        st.subheader("Unmapped Actual Services")

        if result["unmapped_services"].empty:
            st.success("No unmapped actual services found.")
        else:
            st.dataframe(
                result["unmapped_services"],
                hide_index=True,
                use_container_width=True,
            )

        st.subheader("Estimate Rows Needing Review")

        if result["review_rows"].empty:
            st.success("No estimate rows need review.")
        else:
            visible_columns = [
                column
                for column in [
                    "Task",
                    "Required Hrs",
                    "Labor Type",
                    "Section",
                    "Notes",
                    "Normalized Labor Type",
                ]
                if column in result["review_rows"].columns
            ]

            st.dataframe(
                result["review_rows"][visible_columns],
                hide_index=True,
                use_container_width=True,
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
                        result = run_analysis(
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
                            result = run_analysis(
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



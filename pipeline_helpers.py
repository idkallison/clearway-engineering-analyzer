import pandas as pd

import csv_reading_helpers as csv_h
import estimate_helpers as est_h
import labor_helpers as lab_h
import labor_types as lt_h
import pdf_helper as pdf_h


# =========================================================
# Analysis pipeline
# =========================================================
#
# The actual Labor-vs-Estimate analysis, kept separate from
# website_app.py so the pipeline itself has no Streamlit dependency --
# it just takes two file-like objects and returns plain data
# (DataFrames, dicts, PDF bytes). website_app.py is only responsible
# for the UI around calling this.


def run_analysis(labor_file, estimate_file, task_map, project_name):
    """
    Runs the full Labor-vs-Estimate analysis for one project and
    returns a dict of everything needed to render the results and
    build the PDF report.
    """
    # ---- Read both CSVs, auto-detecting where their header row is.
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

    # ---- Labor CSV: drop subtotal/blank rows, then clean and
    # classify each remaining row.
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

    # ---- Estimate CSV: same idea, but the row-shape differs by
    # template (old vs new), which prepare_estimate_dataframe handles.
    estimate_rows = est_h.prepare_estimate_dataframe(
        estimate_df,
        task_map=task_map,
    )

    estimated_hours = (
        estimate_rows
        .groupby("Normalized Labor Type")["Required Hrs"]
        .sum()
    )

    # ---- Combine both sides into one summary table, one row per
    # Labor Type. sort_labor_types keeps the display order consistent
    # (built-ins in a fixed order, custom categories alphabetically,
    # Other always last) everywhere this results_df is used.
    labor_types = lt_h.sort_labor_types(
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

    # Estimate rows that fell all the way through to the unmapped
    # "Other" bucket -- worth a human double-checking them.
    review_rows = estimate_rows[
        estimate_rows["Normalized Labor Type"].eq("Other")
    ].copy()

    # Build the PDF now so it's ready the moment the user wants to
    # download it, using the exact same results_df the website shows.
    pdf_data = pdf_h.make_pdf(
        results_df=results_df,
        total_quote=total_quote,
        total_actual=total_actual,
        review_rows=review_rows,
        labor_df=labor_df,
        estimate_rows=estimate_rows,
        project_name=project_name,
    )

    return {
        "results_df": results_df,
        "labor_df": labor_df,
        "estimate_rows": estimate_rows,
        "review_rows": review_rows,
        "total_quote": total_quote,
        "total_actual": total_actual,
        "pdf_data": pdf_data,
        "labor_header_row": labor_header_row,
        "estimate_header_row": estimate_header_row,
        "estimate_df": estimate_df,
    }

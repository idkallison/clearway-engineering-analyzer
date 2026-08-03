import csv_reading_helpers as csv_h
import estimate_helpers as est_h
import labor_helpers as lab_h
import pdf_helper as pdf_h

import re
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# =========================================================
# Website
# =========================================================


st.set_page_config(
    page_title="Clearway Labor Analyzer",
    page_icon="📊",
    layout="wide",
)


st.title("📊 Clearway Labor Analyzer")

st.write(
    "Upload the normal Labor CSV and Estimate CSV exported "
    "from Excel as CSV UTF-8."
)

labor_file = st.file_uploader(
    "📄 Labor CSV",
    type="csv",
)

estimate_file = st.file_uploader(
    "📋 Estimate CSV",
    type="csv",
)

if labor_file and estimate_file:
    if st.button(
        "🚀 Analyze Project",
        use_container_width=True,
        type="primary",
    ):
        try:
            labor_df, labor_header_row = (
                csv_h.read_csv_with_detected_header(
                    labor_file,
                    {
                        "Activity date",
                        "Product/Service full name",
                        "Duration",
                    },
                )
            )

            estimate_df, estimate_header_row = (
                csv_h.read_csv_with_detected_header(
                    estimate_file,
                    {
                        "Task",
                        "Required Hrs",
                    },
                )
            )

            required_labor_columns = {
                "Activity date",
                "Product/Service full name",
                "Duration",
            }

            missing_labor = (
                required_labor_columns
                - set(labor_df.columns)
            )

            if missing_labor:
                raise ValueError(
                    "Labor CSV is missing: "
                    + ", ".join(
                        sorted(missing_labor)
                    )
                )

            labor_df = labor_df[
                labor_df["Activity date"].notna()
                & labor_df["Activity date"]
                .astype(str)
                .str.strip()
                .ne("")
            ].copy()

            labor_df["Service"] = (
                labor_df[
                    "Product/Service full name"
                ]
                .apply(clean_service_name)
            )

            labor_df["Hours"] = (
                labor_df["Duration"]
                .apply(duration_to_hours)
            )

            labor_df["Labor Type"] = (
                labor_df["Service"]
                .apply(map_service)
            )

            actual_hours = (
                labor_df
                .groupby("Labor Type")["Hours"]
                .sum()
            )

            estimate_rows = (
                est_h.prepare_estimate_dataframe(
                    estimate_df
                )
            )

            estimated_hours = (
                estimate_rows
                .groupby(
                    "Normalized Labor Type"
                )["Required Hrs"]
                .sum()
            )

            labor_types = sorted(
                set(actual_hours.index).union(
                    set(estimated_hours.index)
                )
            )

            results = []
            total_quote = 0.0
            total_actual = 0.0

            for labor_type in labor_types:
                quoted = float(
                    estimated_hours.get(
                        labor_type,
                        0,
                    )
                )

                actual = float(
                    actual_hours.get(
                        labor_type,
                        0,
                    )
                )

                total_quote += quoted
                total_actual += actual

                results.append(
                    {
                        "Labor Type": labor_type,
                        "Quoted Hours": round(
                            quoted,
                            2,
                        ),
                        "Actual Hours": round(
                            actual,
                            2,
                        ),
                        "Remaining Hours": round(
                            quoted - actual,
                            2,
                        ),
                    }
                )

            results_df = pd.DataFrame(results)

            unmapped_services = (
                labor_df[
                    labor_df["Labor Type"]
                    == "Other"
                ]["Service"]
                .value_counts()
                .rename_axis("Service")
                .reset_index(
                    name="Occurrences"
                )
            )

            review_rows = estimate_rows[
                estimate_rows[
                    "Normalized Labor Type"
                ]
                .eq("Other")
            ].copy()

            st.divider()
            st.subheader("📋 Project Summary")

            c1, c2, c3 = st.columns(3)

            c1.metric(
                "Quoted Hours",
                f"{total_quote:.2f}",
            )

            c2.metric(
                "Actual Hours",
                f"{total_actual:.2f}",
            )

            c3.metric(
                "Remaining Hours",
                (
                    f"{total_quote - total_actual:.2f}"
                ),
            )

            st.caption(
                "Remaining Hours = Quoted Hours - Actual Hours"
            )

            st.divider()
            st.subheader("📊 Quote vs Actual")

            st.dataframe(
                results_df,
                hide_index=True,
                use_container_width=True,
            )

            st.divider()
            st.subheader("📈 Labor Comparison")

            chart_df = (
                results_df
                .set_index("Labor Type")[
                    [
                        "Quoted Hours",
                        "Actual Hours",
                    ]
                ]
            )

            st.bar_chart(chart_df)

            diagnostics_tab, review_tab = st.tabs(
                [
                    "File Diagnostics",
                    "Mapping Review",
                ]
            )

            with diagnostics_tab:
                st.write(
                    f"Labor header detected on CSV row "
                    f"{labor_header_row + 1}."
                )

                st.write(
                    f"Estimate header detected on CSV row "
                    f"{estimate_header_row + 1}."
                )

                st.write(
                    "Estimate format detected:",
                    (
                        "Old template with Labor Type"
                        if "Labor Type"
                        in estimate_df.columns
                        else (
                            "New template with sections "
                            "and Level of experience"
                        )
                    ),
                )

            with review_tab:
                st.subheader(
                    "Unmapped Actual Services"
                )

                if unmapped_services.empty:
                    st.success(
                        "No unmapped actual services found."
                    )
                else:
                    st.dataframe(
                        unmapped_services,
                        hide_index=True,
                        use_container_width=True,
                    )

                st.subheader(
                    "Estimate Rows Needing Review"
                )

                if review_rows.empty:
                    st.success(
                        "No estimate rows need review."
                    )
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
                        if column
                        in review_rows.columns
                    ]

                    st.dataframe(
                        review_rows[
                            visible_columns
                        ],
                        hide_index=True,
                        use_container_width=True,
                    )

            st.divider()
            st.subheader("📄 Export Report")

            pdf_data = pdf_h.make_pdf(
                results_df=results_df,
                total_quote=total_quote,
                total_actual=total_actual,
                unmapped_services=(
                    unmapped_services
                ),
                review_rows=review_rows,
            )

            project_name = Path(
                labor_file.name
            ).stem

            st.download_button(
                label="📥 Download PDF Report",
                data=pdf_data,
                file_name=(
                    f"{project_name} - Labor Report.pdf"
                ),
                mime="application/pdf",
                use_container_width=True,
            )

        except Exception as error:
            st.error(
                f"Could not analyze the files: {error}"
            )

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
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


st.set_page_config(
    page_title="Clearway Labor Analyzer",
    page_icon="📊",
    layout="wide",
)


SUMMARY_NAMES = {
    "T.B": "Build",
    "T.E": "Engineering",
    "T.F": "FAT",
    "T.I": "Installation",
    "T.M": "Misc.",
    "T.N": "Non-Project",
    "T.P": "Pre-Sale",
    "T.S": "Service",
}


def duration_to_hours(value):
    if pd.isna(value):
        return 0.0

    text = str(value).strip()

    if ":" not in text:
        number = pd.to_numeric(text, errors="coerce")
        return 0.0 if pd.isna(number) else float(number)

    parts = text.split(":")

    try:
        hours = float(parts[0])
        minutes = float(parts[1])
        seconds = float(parts[2]) if len(parts) > 2 else 0.0
        return hours + minutes / 60 + seconds / 3600
    except (ValueError, IndexError):
        return 0.0


def normalize_service(value):
    text = str(value)
    text = text.replace("Hourly:", "")
    text = text.replace("(deleted)", "")
    return text.strip()


def detailed_type_from_service(service):
    # Combine experience levels:
    # T.B.Testing.1 -> T.B.Testing
    return re.sub(
        r"\.\d+$",
        "",
        normalize_service(service),
    )


def summary_type_from_detail(detailed_type):
    match = re.match(
        r"^(T\.[A-Z])(?:\.|$)",
        str(detailed_type),
    )
    return match.group(1) if match else "Unmapped"


def build_comparison(
    quoted_series,
    actual_series,
    category_column,
):
    categories = sorted(
        set(quoted_series.index).union(
            set(actual_series.index)
        )
    )

    rows = []

    for category in categories:
        quoted = float(quoted_series.get(category, 0))
        actual = float(actual_series.get(category, 0))

        rows.append(
            {
                category_column: category,
                "Quoted Hours": round(quoted, 2),
                "Actual Hours": round(actual, 2),
                "Remaining": round(quoted - actual, 2),
            }
        )

    return pd.DataFrame(rows)


def load_report(labor_file, estimate_file):
    labor_file.seek(0)
    estimate_file.seek(0)

    # -----------------------------
    # Labor CSV
    # -----------------------------
    labor_df = pd.read_csv(
        labor_file,
        header=4,
    )

    if len(labor_df.columns) > 0:
        first_column = str(labor_df.columns[0])

        if (
            first_column.startswith("Unnamed:")
            or first_column.strip() == ""
        ):
            labor_df = labor_df.drop(
                columns=labor_df.columns[0]
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
            + ", ".join(sorted(missing_labor))
        )

    labor_df = labor_df[
        labor_df["Activity date"].notna()
    ].copy()

    labor_df["Service"] = (
        labor_df["Product/Service full name"]
        .apply(normalize_service)
    )

    labor_df["Hours"] = (
        labor_df["Duration"]
        .apply(duration_to_hours)
    )

    labor_df["Detailed Type"] = (
        labor_df["Service"]
        .apply(detailed_type_from_service)
    )

    labor_df["Summary Type"] = (
        labor_df["Detailed Type"]
        .apply(summary_type_from_detail)
    )

    actual_summary = (
        labor_df[
            labor_df["Summary Type"] != "Unmapped"
        ]
        .groupby("Summary Type")["Hours"]
        .sum()
    )

    actual_detail = (
        labor_df[
            labor_df["Summary Type"] != "Unmapped"
        ]
        .groupby("Detailed Type")["Hours"]
        .sum()
    )

    # -----------------------------
    # Estimate CSV
    # -----------------------------
    estimate_df = pd.read_csv(
        estimate_file,
        header=4,
    )

    required_estimate_columns = {
        "Required Hrs",
        "Summary Type",
        "Detailed Type",
    }

    missing_estimate = (
        required_estimate_columns
        - set(estimate_df.columns)
    )

    if missing_estimate:
        raise ValueError(
            "Estimate CSV is missing: "
            + ", ".join(sorted(missing_estimate))
            + ". Run the updated two-level converter first."
        )

    estimate_df["Required Hrs"] = pd.to_numeric(
        estimate_df["Required Hrs"],
        errors="coerce",
    ).fillna(0)

    estimate_df = estimate_df[
        estimate_df["Required Hrs"] > 0
    ].copy()

    quoted_summary = (
        estimate_df[
            estimate_df["Summary Type"] != "Unmapped"
        ]
        .groupby("Summary Type")["Required Hrs"]
        .sum()
    )

    quoted_detail = (
        estimate_df[
            estimate_df["Detailed Type"] != "Unmapped"
        ]
        .groupby("Detailed Type")["Required Hrs"]
        .sum()
    )

    summary_results = build_comparison(
        quoted_summary,
        actual_summary,
        "Summary Type",
    )

    summary_results["Category"] = (
        summary_results["Summary Type"]
        .map(SUMMARY_NAMES)
        .fillna("Other")
    )

    summary_results = summary_results[
        [
            "Summary Type",
            "Category",
            "Quoted Hours",
            "Actual Hours",
            "Remaining",
        ]
    ]

    detail_results = build_comparison(
        quoted_detail,
        actual_detail,
        "Detailed Type",
    )

    unmapped_actual = (
        labor_df[
            labor_df["Summary Type"] == "Unmapped"
        ]["Service"]
        .value_counts()
        .rename_axis("Service")
        .reset_index(name="Occurrences")
    )

    if "Mapping Status" in estimate_df.columns:
        mapping_review = estimate_df[
            estimate_df["Mapping Status"]
            .astype(str)
            .str.contains(
                "review",
                case=False,
                na=False,
            )
        ].copy()
    else:
        mapping_review = pd.DataFrame()

    project_name = Path(labor_file.name).stem

    if project_name.endswith(" - Labor"):
        project_name = project_name.removesuffix(
            " - Labor"
        )

    return {
        "project_name": project_name,
        "summary_results": summary_results,
        "detail_results": detail_results,
        "total_quote": float(
            estimate_df["Required Hrs"].sum()
        ),
        "total_actual": float(
            labor_df["Hours"].sum()
        ),
        "mapping_review": mapping_review,
        "unmapped_actual": unmapped_actual,
    }


def style_pdf_table(table):
    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.lightgrey,
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    "Helvetica-Bold",
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey,
                ),
                (
                    "ALIGN",
                    (1, 1),
                    (-1, -1),
                    "CENTER",
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
            ]
        )
    )


def dataframe_to_pdf_table(
    dataframe,
    first_column,
    first_width,
):
    headers = list(dataframe.columns)
    data = [headers]

    for _, row in dataframe.iterrows():
        pdf_row = []

        for column in headers:
            value = row[column]

            if column == first_column:
                pdf_row.append(str(value))
            elif isinstance(value, (int, float)):
                pdf_row.append(f"{value:.2f}")
            else:
                pdf_row.append(str(value))

        data.append(pdf_row)

    widths = [
        first_width,
        1.25 * inch,
        1.25 * inch,
        1.25 * inch,
    ]

    table = Table(
        data,
        repeatRows=1,
        colWidths=widths,
    )

    style_pdf_table(table)
    return table


def create_pdf(report):
    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30,
    )

    styles = getSampleStyleSheet()
    elements = []

    elements.append(
        Paragraph(
            "Clearway Labor Analysis Report",
            styles["Title"],
        )
    )

    elements.append(Spacer(1, 10))

    elements.append(
        Paragraph(
            f"<b>Project:</b> {report['project_name']}",
            styles["Normal"],
        )
    )

    elements.append(Spacer(1, 12))

    totals_table = Table(
        [
            [
                "Quoted Hours",
                "Actual Hours",
                "Remaining",
            ],
            [
                f"{report['total_quote']:.2f}",
                f"{report['total_actual']:.2f}",
                (
                    f"{report['total_actual'] - report['total_quote']:.2f}"
                ),
            ],
        ],
        colWidths=[
            2 * inch,
            2 * inch,
            2 * inch,
        ],
    )

    style_pdf_table(totals_table)
    elements.append(totals_table)
    elements.append(Spacer(1, 18))

    elements.append(
        Paragraph(
            "Summary-Level Report",
            styles["Heading2"],
        )
    )

    summary_pdf = report["summary_results"][
        [
            "Summary Type",
            "Quoted Hours",
            "Actual Hours",
            "Remaining",
        ]
    ]

    elements.append(
        dataframe_to_pdf_table(
            summary_pdf,
            "Summary Type",
            3.2 * inch,
        )
    )

    elements.append(PageBreak())

    elements.append(
        Paragraph(
            "Detailed Report",
            styles["Heading2"],
        )
    )

    elements.append(
        dataframe_to_pdf_table(
            report["detail_results"],
            "Detailed Type",
            3.8 * inch,
        )
    )

    document.build(elements)
    buffer.seek(0)

    return buffer.getvalue()


def show_mapping_review(report):
    st.subheader("Estimate Mapping Review")

    mapping_review = report["mapping_review"]

    if mapping_review.empty:
        st.success(
            "No estimate mappings need review."
        )
    else:
        st.warning(
            "These estimate rows were inferred and "
            "should be checked."
        )

        visible_columns = [
            column
            for column in [
                "Task",
                "Required Hrs",
                "Summary Type",
                "Detailed Type",
                "Mapping Status",
                "Original Labor Type",
                "Notes",
            ]
            if column in mapping_review.columns
        ]

        st.dataframe(
            mapping_review[visible_columns],
            hide_index=True,
            use_container_width=True,
        )

    st.divider()
    st.subheader("Unmapped Actual Services")

    unmapped_actual = report["unmapped_actual"]

    if unmapped_actual.empty:
        st.success(
            "No unmapped actual services found."
        )
    else:
        st.dataframe(
            unmapped_actual,
            hide_index=True,
            use_container_width=True,
        )


# =========================================
# Website
# =========================================
st.title("📊 Clearway Labor Analyzer")

st.write(
    "Upload the Labor and Estimate CSV files created by "
    "the updated two-level converter."
)

upload_left, upload_right = st.columns(2)

with upload_left:
    labor_file = st.file_uploader(
        "📄 Labor CSV",
        type="csv",
    )

with upload_right:
    estimate_file = st.file_uploader(
        "📋 Estimate CSV",
        type="csv",
    )

if labor_file and estimate_file:
    signature = (
        labor_file.name,
        labor_file.size,
        estimate_file.name,
        estimate_file.size,
    )

    if st.session_state.get("signature") != signature:
        st.session_state["signature"] = signature
        st.session_state.pop("report", None)
        st.session_state.pop(
            "selected_summary",
            None,
        )

    if st.button(
        "🚀 Analyze Project",
        type="primary",
        use_container_width=True,
    ):
        try:
            st.session_state["report"] = load_report(
                labor_file,
                estimate_file,
            )
        except Exception as error:
            st.session_state.pop("report", None)
            st.error(
                f"Could not analyze the files: {error}"
            )

report = st.session_state.get("report")

if report is not None:
    st.divider()
    st.caption("PROJECT")
    st.subheader(report["project_name"])

    total_quote = report["total_quote"]
    total_actual = report["total_actual"]

    metric_1, metric_2, metric_3 = st.columns(3)

    metric_1.metric(
        "Quoted Hours",
        f"{total_quote:.2f}",
    )

    metric_2.metric(
        "Actual Hours",
        f"{total_actual:.2f}",
    )

    metric_3.metric(
        "Remaining",
        f"{total_quote - total_actual:.2f}",
    )

    st.caption(
        "Remaining hours = Quoted hours - Actual hours. "
        "A negative value means the project is over the quoted hours."
    )

    report_tab, review_tab = st.tabs(
        [
            "Labor Report",
            "Mapping Review",
        ]
    )

    with report_tab:
        st.subheader("Summary Categories")

        st.caption(
            "Click a category to show its detailed report."
        )

        summary_results = report["summary_results"]

        # Clickable summary-category cards
        category_columns = st.columns(
            min(4, max(1, len(summary_results)))
        )

        for index, row in summary_results.iterrows():
            column = category_columns[
                index % len(category_columns)
            ]

            code = row["Summary Type"]
            category = row["Category"]

            with column:
                if st.button(
                    f"{code} · {category}",
                    key=f"category_{code}",
                    use_container_width=True,
                ):
                    st.session_state[
                        "selected_summary"
                    ] = code

                st.caption(
                    f"Quoted {row['Quoted Hours']:.2f} | "
                    f"Actual {row['Actual Hours']:.2f}"
                )

        selected_summary = st.session_state.get(
            "selected_summary"
        )

        st.divider()

        if selected_summary is None:
            st.info(
                "Click T.B, T.E, or another category "
                "above to open its details."
            )
        else:
            selected_row = summary_results[
                summary_results["Summary Type"]
                == selected_summary
            ].iloc[0]

            st.subheader(
                f"{selected_summary} · "
                f"{selected_row['Category']}"
            )

            detail_metric_1, (
                detail_metric_2
            ), detail_metric_3 = st.columns(3)

            detail_metric_1.metric(
                "Quoted",
                f"{selected_row['Quoted Hours']:.2f}",
            )

            detail_metric_2.metric(
                "Actual",
                f"{selected_row['Actual Hours']:.2f}",
            )

            detail_metric_3.metric(
                "Remaining",
                f"{selected_row['Remaining']:.2f}",
            )

            selected_details = (
                report["detail_results"][
                    report["detail_results"][
                        "Detailed Type"
                    ]
                    .astype(str)
                    .str.startswith(
                        f"{selected_summary}."
                    )
                ]
                .copy()
                .reset_index(drop=True)
            )

            if selected_details.empty:
                st.info(
                    "No detailed categories were found "
                    "for this summary category."
                )
            else:
                st.dataframe(
                    selected_details,
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Detailed Type":
                            st.column_config.TextColumn(
                                "Detailed Category",
                            ),
                        "Quoted Hours":
                            st.column_config.NumberColumn(
                                "Quoted",
                                format="%.2f",
                            ),
                        "Actual Hours":
                            st.column_config.NumberColumn(
                                "Actual",
                                format="%.2f",
                            ),
                        "Remaining":
                            st.column_config.NumberColumn(
                                "Remaining",
                                format="%.2f",
                            ),
                    },
                )

                detail_chart = (
                    selected_details
                    .set_index("Detailed Type")[
                        [
                            "Quoted Hours",
                            "Actual Hours",
                        ]
                    ]
                )

                st.bar_chart(detail_chart)

        st.divider()
        st.subheader("Overall Summary Comparison")

        summary_chart = (
            summary_results
            .set_index("Summary Type")[
                [
                    "Quoted Hours",
                    "Actual Hours",
                ]
            ]
        )

        st.bar_chart(summary_chart)

    with review_tab:
        show_mapping_review(report)

    st.divider()
    st.subheader("📄 Export Report")

    pdf_data = create_pdf(report)

    safe_name = "".join(
        character
        if character.isalnum()
        or character in " -_"
        else "_"
        for character in report["project_name"]
    )

    st.download_button(
        label="📥 Download Two-Level PDF Report",
        data=pdf_data,
        file_name=(
            f"{safe_name} - Labor Report.pdf"
        ),
        mime="application/pdf",
        use_container_width=True,
    )

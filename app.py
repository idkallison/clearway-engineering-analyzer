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


st.set_page_config(
    page_title="Clearway Labor Analyzer",
    page_icon="📊",
    layout="wide",
)


# =========================================================
# CSV reading helpers
# =========================================================
def uploaded_file_bytes(uploaded_file):
    uploaded_file.seek(0)
    return uploaded_file.read()


def decode_csv_bytes(file_bytes):
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise ValueError(
        "The CSV encoding could not be read. "
        "Save the file as CSV UTF-8 and try again."
    )


def find_header_row(raw_df, required_columns, search_limit=30):
    """
    Find the row containing the requested headers instead of assuming
    that the header is always exactly row 5.
    """
    required = {
        str(column).strip().lower()
        for column in required_columns
    }

    rows_to_check = min(search_limit, len(raw_df))

    for row_number in range(rows_to_check):
        values = {
            str(value).strip().lower()
            for value in raw_df.iloc[row_number].tolist()
            if pd.notna(value) and str(value).strip()
        }

        if required.issubset(values):
            return row_number

    raise ValueError(
        "Could not find a header row containing: "
        + ", ".join(sorted(required_columns))
    )


def read_csv_with_detected_header(
    uploaded_file,
    required_columns,
):
    """
    Read an Excel-exported CSV even when metadata rows appear above
    the real table header.
    """
    file_bytes = uploaded_file_bytes(uploaded_file)
    csv_text = decode_csv_bytes(file_bytes)

    raw_df = pd.read_csv(
        BytesIO(csv_text.encode("utf-8")),
        header=None,
        dtype=str,
        keep_default_na=False,
    )

    header_row = find_header_row(
        raw_df,
        required_columns,
    )

    dataframe = pd.read_csv(
        BytesIO(csv_text.encode("utf-8")),
        header=header_row,
    )

    dataframe.columns = [
        str(column).strip()
        for column in dataframe.columns
    ]

    # Remove columns that are completely empty.
    dataframe = dataframe.dropna(
        axis=1,
        how="all",
    )

    return dataframe, header_row


# =========================================================
# Labor helpers
# =========================================================
def duration_to_hours(duration):
    if pd.isna(duration):
        return 0.0

    text = str(duration).strip()

    if not text:
        return 0.0

    # Handles HH:MM and HH:MM:SS.
    if ":" in text:
        parts = text.split(":")

        try:
            hours = float(parts[0])
            minutes = float(parts[1])
            seconds = (
                float(parts[2])
                if len(parts) > 2
                else 0.0
            )

            return (
                hours
                + minutes / 60
                + seconds / 3600
            )
        except (ValueError, IndexError):
            return 0.0

    # Handles a plain numeric number of hours.
    numeric_value = pd.to_numeric(
        text,
        errors="coerce",
    )

    if pd.isna(numeric_value):
        return 0.0

    return float(numeric_value)


def clean_service_name(service):
    return (
        str(service)
        .replace("Hourly:", "")
        .replace("(deleted)", "")
        .strip()
    )


def map_service(service):
    """
    Normalize actual QuickBooks services to the broad labor categories
    used by this version of the report.
    """
    text = clean_service_name(service)
    lower = text.lower()

    # New T.B hierarchy
    if lower.startswith("t.b.electrical assembly"):
        return "Assembly - Electrical"

    if lower.startswith("t.b.mechanical assembly"):
        return "Assembly - Mechanical"

    if lower.startswith("t.b.machine shop"):
        return "Assembly - Mechanical"

    if lower.startswith("t.b.programming"):
        return "Programming"

    if lower.startswith("t.b.procurement"):
        return "Admin"

    if lower.startswith("t.b.testing"):
        return "Engineering"

    if lower.startswith("t.b.other"):
        return "Assembly - Mechanical"

    # New T.E hierarchy
    if lower.startswith("t.e.programming"):
        return "Programming"

    if lower.startswith("t.e."):
        return "Engineering"

    # FAT
    if lower.startswith("t.f."):
        return "Engineering"

    # Installation
    if lower.startswith("t.i."):
        return "Installation"

    # Miscellaneous
    if lower.startswith("t.m.r&d"):
        return "Engineering"

    if lower.startswith("t.m."):
        return "Admin"

    # Non-project
    if lower.startswith("t.n."):
        return "Non-Project"

    # Pre-sale
    if lower.startswith("t.p."):
        return "Pre-Sale"

    # Service
    if lower.startswith(
        "t.s.engineering/programming"
    ):
        return "Programming"

    if lower.startswith("t.s."):
        return "Installation"

    # Legacy QuickBooks service names
    legacy_exact = {
        "t.ee-engineering/design": "Engineering",
        "t.ed-cad drafting": "Engineering",
        "t.er-process testing": "Engineering",
        "t.ft-testing": "Engineering",
        "t.et-startup/debug/testing": "Engineering",
        "programming - plc/hmi": "Programming",
        "t.ev-vision system programming": "Programming",
        "t.fb-build/assemble/wire": "Assembly - Electrical",
        "t.mb-build/assemble": "Assembly - Mechanical",
        "t.ab-procurement": "Admin",
        "t.fi-installation": "Installation",
    }

    if lower in legacy_exact:
        return legacy_exact[lower]

    return "Other"


# =========================================================
# Estimate helpers
# =========================================================
def normalize_original_labor_type(value):
    """
    Normalize labor-type names found in older Estimate CSV files.
    """
    text = str(value).strip().lower()

    aliases = {
        "engineering": "Engineering",
        "engineering tech": "Engineering",
        "engineer": "Engineering",
        "programming": "Programming",
        "assembly - electrical": "Assembly - Electrical",
        "electrical assembly": "Assembly - Electrical",
        "assembly - mechanical": "Assembly - Mechanical",
        "mechanical assembly": "Assembly - Mechanical",
        "admin": "Admin",
        "administration": "Admin",
        "installation": "Installation",
        "install": "Installation",
        "pre-sale": "Pre-Sale",
        "non-project": "Non-Project",
    }

    return aliases.get(text)


def infer_estimate_labor_type(
    task,
    original_labor_type="",
    section="",
    notes="",
):
    """
    Use the task first because several Estimate sheets have incorrect
    or overly broad values in the Labor Type column.
    """
    task_text = str(task).strip().lower()
    section_text = str(section).strip().lower()
    notes_text = str(notes).strip().lower()

    combined = " ".join(
        [
            task_text,
            section_text,
            notes_text,
        ]
    )

    # Installation must be checked before Engineering because some
    # older estimates label installation as Engineering.
    if any(
        phrase in combined
        for phrase in (
            "installation",
            "install",
            "ship/install",
            "packaging/delivery",
            "packaging",
            "delivery",
            "start-up",
            "startup",
            "documentation red lines",
        )
    ):
        return "Installation"

    if any(
        phrase in combined
        for phrase in (
            "mechanical assembly",
            "mechanical build",
            "build - eoat",
            "assembly frame",
            "assembly docking",
        )
    ):
        return "Assembly - Mechanical"

    if any(
        phrase in combined
        for phrase in (
            "electrical assembly",
            "electrical build",
            "build/wire",
            "wiring",
            "wire panel",
        )
    ):
        return "Assembly - Electrical"

    if any(
        phrase in combined
        for phrase in (
            "programming",
            "program ",
            "program robot",
            "program camera",
            "program plc",
            "plc",
            "hmi",
            "vision programming",
        )
    ):
        return "Programming"

    if any(
        phrase in combined
        for phrase in (
            "procurement",
            "sales call",
            "project concept",
            "research/quoting",
            "quoting",
        )
    ):
        # New template pre-sale rows should compare with actual T.P.
        if (
            "pre-sale" in section_text
            or "sales call" in combined
            or "project concept" in combined
            or "research/quoting" in combined
        ):
            return "Pre-Sale"

        return "Admin"

    if "fat" in section_text:
        return "Engineering"

    if any(
        phrase in combined
        for phrase in (
            "testing",
            "test",
            "debug",
            "design",
            "research/testing",
        )
    ):
        return "Engineering"

    normalized_original = (
        normalize_original_labor_type(
            original_labor_type
        )
    )

    if normalized_original is not None:
        return normalized_original

    if "engineering" in section_text:
        return "Engineering"

    if "build/program/debug" in section_text:
        return "Engineering"

    return "Other"


def find_section_column(estimate_df):
    """
    The newer Estimate template stores section names such as
    Engineering and Build/Program/Debug in the first unnamed column.
    """
    unnamed_columns = [
        column
        for column in estimate_df.columns
        if str(column).startswith("Unnamed:")
    ]

    if unnamed_columns:
        return unnamed_columns[0]

    # Fall back to the first column when it is not one of the known
    # data columns.
    if len(estimate_df.columns) > 0:
        first_column = estimate_df.columns[0]

        known_columns = {
            "Task",
            "Required Hrs",
            "Labor Type",
            "Level of experience",
            "Notes",
        }

        if first_column not in known_columns:
            return first_column

    return None


def prepare_estimate_dataframe(estimate_df):
    """
    Supports both normal Estimate CSV templates:

    Old:
      Task, Required Hrs, Labor Type, ...

    New:
      [Section column], Task, Level of experience, Required Hrs, ...
    """
    if "Required Hrs" not in estimate_df.columns:
        raise ValueError(
            "Estimate CSV is missing 'Required Hrs'. "
            f"Columns found: {estimate_df.columns.tolist()}"
        )

    if "Task" not in estimate_df.columns:
        raise ValueError(
            "Estimate CSV is missing 'Task'. "
            f"Columns found: {estimate_df.columns.tolist()}"
        )

    estimate_df = estimate_df.copy()

    estimate_df["Required Hrs"] = pd.to_numeric(
        estimate_df["Required Hrs"],
        errors="coerce",
    ).fillna(0)

    if "Notes" not in estimate_df.columns:
        estimate_df["Notes"] = ""

    section_column = find_section_column(
        estimate_df
    )

    if section_column is not None:
        estimate_df["Section"] = (
            estimate_df[section_column]
            .where(
                estimate_df[section_column]
                .astype(str)
                .str.strip()
                .ne("")
            )
            .ffill()
            .fillna("")
            .astype(str)
            .str.strip()
        )
    else:
        estimate_df["Section"] = ""

    if "Labor Type" not in estimate_df.columns:
        estimate_df["Labor Type"] = ""

    estimate_rows = estimate_df[
        estimate_df["Task"].notna()
        & estimate_df["Task"]
        .astype(str)
        .str.strip()
        .ne("")
        & (estimate_df["Required Hrs"] > 0)
    ].copy()

    estimate_rows["Normalized Labor Type"] = (
        estimate_rows.apply(
            lambda row: infer_estimate_labor_type(
                task=row["Task"],
                original_labor_type=row[
                    "Labor Type"
                ],
                section=row["Section"],
                notes=row["Notes"],
            ),
            axis=1,
        )
    )

    return estimate_rows


# =========================================================
# PDF
# =========================================================
def make_pdf(
    results_df,
    total_quote,
    total_actual,
    unmapped_services,
    review_rows,
):
    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=30,
        rightMargin=30,
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

    elements.append(Spacer(1, 12))

    elements.append(
        Paragraph(
            (
                f"<b>Quoted Hours:</b> "
                f"{total_quote:.2f}<br/>"
                f"<b>Actual Hours:</b> "
                f"{total_actual:.2f}<br/>"
                f"<b>Remaining Hours:</b> "
                f"{total_quote - total_actual:.2f}"
            ),
            styles["BodyText"],
        )
    )

    elements.append(Spacer(1, 18))

    table_data = [
        results_df.columns.tolist()
    ] + results_df.values.tolist()

    main_table = Table(
        table_data,
        repeatRows=1,
        colWidths=[
            2.5 * inch,
            1.5 * inch,
            1.5 * inch,
            1.5 * inch,
        ],
    )

    main_table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.grey,
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.whitesmoke,
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
                    colors.black,
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
            ]
        )
    )

    elements.append(main_table)

    if not unmapped_services.empty:
        elements.append(Spacer(1, 18))
        elements.append(
            Paragraph(
                "Unmapped Actual Services",
                styles["Heading2"],
            )
        )

        unmapped_data = [
            ["Service", "Occurrences"]
        ] + unmapped_services.values.tolist()

        unmapped_table = Table(
            unmapped_data,
            repeatRows=1,
            colWidths=[
                6.5 * inch,
                1.2 * inch,
            ],
        )

        unmapped_table.setStyle(
            TableStyle(
                [
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        colors.grey,
                    ),
                    (
                        "TEXTCOLOR",
                        (0, 0),
                        (-1, 0),
                        colors.whitesmoke,
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
                        colors.black,
                    ),
                ]
            )
        )

        elements.append(unmapped_table)

    if not review_rows.empty:
        elements.append(Spacer(1, 18))
        elements.append(
            Paragraph(
                "Estimate Rows Needing Review",
                styles["Heading2"],
            )
        )

        review_data = [
            [
                "Task",
                "Required Hrs",
                "Original Labor Type",
                "Normalized Labor Type",
            ]
        ]

        for _, row in review_rows.iterrows():
            review_data.append(
                [
                    str(row["Task"]),
                    str(row["Required Hrs"]),
                    str(row["Labor Type"]),
                    str(
                        row[
                            "Normalized Labor Type"
                        ]
                    ),
                ]
            )

        review_table = Table(
            review_data,
            repeatRows=1,
            colWidths=[
                3.5 * inch,
                1.2 * inch,
                1.8 * inch,
                1.8 * inch,
            ],
        )

        review_table.setStyle(
            TableStyle(
                [
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        colors.grey,
                    ),
                    (
                        "TEXTCOLOR",
                        (0, 0),
                        (-1, 0),
                        colors.whitesmoke,
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
                        colors.black,
                    ),
                ]
            )
        )

        elements.append(review_table)

    document.build(elements)
    buffer.seek(0)

    return buffer.getvalue()


# =========================================================
# Website
# =========================================================
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
                read_csv_with_detected_header(
                    labor_file,
                    {
                        "Activity date",
                        "Product/Service full name",
                        "Duration",
                    },
                )
            )

            estimate_df, estimate_header_row = (
                read_csv_with_detected_header(
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
                prepare_estimate_dataframe(
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

            pdf_data = make_pdf(
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

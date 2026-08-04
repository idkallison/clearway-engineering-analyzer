from io import BytesIO

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

import breakdown_helpers as break_h
import labor_types as lt_h


# =========================================================
# PDF
# =========================================================
#
# Mirrors what the website shows: the summary table, the Quoted vs
# Actual bar chart, and -- since a PDF can't have clickable dropdowns
# -- every Labor Type's task breakdown printed permanently "expanded"
# right below the summary table. Row order and labels (e.g.
# "Other/Unmapped") come straight from results_df/labor_types.py, so
# this never has to duplicate that logic -- it just renders whatever
# order it's given.

PAGE_WIDTH = landscape(letter)[0]
CONTENT_WIDTH = PAGE_WIDTH - 60  # 30pt margin on each side

# Colors used for the Quoted vs Actual bars, matched in both the
# chart and its legend so the two always agree with each other.
QUOTED_COLOR = "#4C78A8"  # blue
ACTUAL_COLOR = "#F58518"  # orange

HEADER_STYLE = TableStyle(
    [
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
)


def _grid_table(data, col_widths, extra_style=None):
    """
    A Table with the standard grey-header / gridlines look used
    throughout this report, so every section shares one style
    instead of redefining it inline.
    """
    table = Table(data, repeatRows=1, colWidths=col_widths)

    style_commands = list(HEADER_STYLE.getCommands())

    if extra_style:
        style_commands.extend(extra_style)

    table.setStyle(TableStyle(style_commands))

    return table


def _negative_remaining_style(data, remaining_col_index):
    """
    Colors "Remaining Hours" red for any row that's over budget
    (negative), so a skimmed PDF page surfaces problem areas the same
    way a person scanning the website's table would.
    """
    commands = []

    # Row 0 is the header, so the actual data starts at row 1.
    for row_index in range(1, len(data)):
        value = data[row_index][remaining_col_index]

        try:
            if float(value) < 0:
                commands.append(
                    (
                        "TEXTCOLOR",
                        (remaining_col_index, row_index),
                        (remaining_col_index, row_index),
                        colors.red,
                    )
                )
        except (TypeError, ValueError):
            continue

    return commands


def _make_comparison_chart_image(results_df, width_in, height_in):
    """
    Renders the same Quoted vs Actual horizontal bar comparison shown
    on the website (st.bar_chart) as a PNG, since reportlab can't
    embed an interactive Streamlit chart directly.
    """
    chart_df = results_df[
        ["Labor Type", "Quoted Hours", "Actual Hours"]
    ].copy()

    # Same display label used everywhere else (e.g. "Other/Unmapped").
    chart_df["Labor Type"] = chart_df["Labor Type"].apply(
        lt_h.display_label
    )

    labor_types = chart_df["Labor Type"].tolist()
    y_positions = list(range(len(labor_types)))
    bar_height = 0.35

    fig, ax = plt.subplots(figsize=(width_in, height_in))

    # Quoted goes at y - offset and Actual at y + offset. Combined
    # with invert_yaxis() below (which flips top/bottom), this puts
    # Quoted (blue) visually ABOVE Actual (orange) within each pair --
    # matching the legend order, where Quoted is listed first/top.
    ax.barh(
        [y - bar_height / 2 for y in y_positions],
        chart_df["Quoted Hours"],
        height=bar_height,
        label="Quoted Hours",
        color=QUOTED_COLOR,
    )

    ax.barh(
        [y + bar_height / 2 for y in y_positions],
        chart_df["Actual Hours"],
        height=bar_height,
        label="Actual Hours",
        color=ACTUAL_COLOR,
    )

    ax.set_yticks(y_positions)
    ax.set_yticklabels(labor_types)
    ax.invert_yaxis()
    ax.set_xlabel("Hours")
    ax.legend(loc="lower right")
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()

    image_buffer = BytesIO()
    fig.savefig(image_buffer, format="png", dpi=150)
    plt.close(fig)
    image_buffer.seek(0)

    return image_buffer


def make_pdf(
    results_df,
    total_quote,
    total_actual,
    review_rows,
    labor_df,
    estimate_rows,
    project_name=None,
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

    title_text = "Clearway Labor Analysis Report"

    if project_name:
        title_text += f" \u2014 {project_name}"

    elements.append(Paragraph(title_text, styles["Title"]))
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
    elements.append(
        Paragraph("Quote vs Actual by Labor Type", styles["Heading2"])
    )
    elements.append(Spacer(1, 6))

    # ---------------------------------------------------------
    # Main summary table (one row per Labor Type)
    # ---------------------------------------------------------
    # results_df already arrives pre-sorted (labor_types.
    # sort_labor_types, applied once in pipeline_helpers.run_analysis)
    # so the row order here always matches the website's table.

    summary_display_df = results_df.copy()
    summary_display_df["Labor Type"] = summary_display_df[
        "Labor Type"
    ].apply(lt_h.display_label)

    table_data = [
        summary_display_df.columns.tolist()
    ] + summary_display_df.values.tolist()

    remaining_col_index = summary_display_df.columns.get_loc(
        "Remaining Hours"
    )

    main_table = _grid_table(
        table_data,
        col_widths=[2.5 * inch, 1.5 * inch, 1.5 * inch, 1.5 * inch],
        extra_style=_negative_remaining_style(
            table_data, remaining_col_index
        ),
    )

    elements.append(main_table)

    # ---------------------------------------------------------
    # Bar chart (Quoted vs Actual), same comparison as the website
    # ---------------------------------------------------------

    if not results_df.empty:
        chart_width_in = CONTENT_WIDTH / inch
        chart_height_in = max(3.0, 0.6 * len(results_df) + 1.2)

        chart_image_buffer = _make_comparison_chart_image(
            results_df, chart_width_in, chart_height_in
        )

        elements.append(Spacer(1, 18))
        elements.append(
            Image(
                chart_image_buffer,
                width=CONTENT_WIDTH,
                height=chart_height_in * inch,
            )
        )

    # ---------------------------------------------------------
    # Per-Labor-Type task breakdown -- the PDF equivalent of the
    # website's expandable rows, except every row is always "open"
    # since a PDF has no click interaction.
    # ---------------------------------------------------------

    elements.append(Spacer(1, 24))
    elements.append(
        Paragraph("Task Breakdown by Labor Type", styles["Heading1"])
    )

    # Same row order as the summary table above (Programming, for
    # example, always appears before Other/Unmapped).
    for _, summary_row in results_df.iterrows():
        labor_type = summary_row["Labor Type"]
        display_label = lt_h.display_label(labor_type)

        breakdown_df, quoted_row_count = break_h.build_task_breakdown(
            labor_df, estimate_rows, labor_type
        )

        elements.append(Spacer(1, 14))
        elements.append(
            Paragraph(
                (
                    f"{display_label} &mdash; Quoted: "
                    f"{summary_row['Quoted Hours']:.2f} | Actual: "
                    f"{summary_row['Actual Hours']:.2f} | Remaining: "
                    f"{summary_row['Remaining Hours']:.2f}"
                ),
                styles["Heading3"],
            )
        )
        elements.append(Spacer(1, 4))

        if breakdown_df.empty:
            elements.append(
                Paragraph(
                    "No individual task data found for this labor "
                    "type.",
                    styles["BodyText"],
                )
            )
            continue

        breakdown_data = [
            breakdown_df.columns.tolist()
        ] + breakdown_df.values.tolist()

        breakdown_remaining_col_index = breakdown_df.columns.get_loc(
            "Remaining Hours"
        )

        divider_style = []

        # A bold rule between the "has a quote" rows and the
        # actual-only rows, so the two groups read as visually
        # distinct blocks rather than one long alphabetical list.
        if 0 < quoted_row_count < len(breakdown_df):
            divider_style.append(
                (
                    "LINEBELOW",
                    (0, quoted_row_count),
                    (-1, quoted_row_count),
                    1.75,
                    colors.black,
                )
            )

        breakdown_table = _grid_table(
            breakdown_data,
            col_widths=[
                4.0 * inch,
                1.5 * inch,
                1.5 * inch,
                1.5 * inch,
            ],
            extra_style=(
                _negative_remaining_style(
                    breakdown_data, breakdown_remaining_col_index
                )
                + divider_style
            ),
        )

        elements.append(breakdown_table)

    # ---------------------------------------------------------
    # Estimate rows needing review
    # ---------------------------------------------------------

    if not review_rows.empty:
        elements.append(Spacer(1, 18))
        elements.append(
            Paragraph(
                "Estimate Rows Needing Review", styles["Heading2"]
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
                    str(row["Normalized Labor Type"]),
                ]
            )

        review_table = _grid_table(
            review_data,
            col_widths=[
                3.5 * inch,
                1.2 * inch,
                1.8 * inch,
                1.8 * inch,
            ],
        )

        elements.append(review_table)

    document.build(elements)
    buffer.seek(0)

    return buffer.getvalue()

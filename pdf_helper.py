from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


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


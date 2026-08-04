import pandas as pd


# =========================================================
# Task breakdown helpers
# =========================================================
#
# Shared by website_app.py (the expandable row on the website) and
# pdf_helper.py (the always-expanded table in the PDF export), so the
# two surfaces can never drift apart on how a Labor Type's numbers are
# broken down by task.


def build_task_breakdown(labor_df, estimate_rows, labor_type):
    """
    Per-task Quoted / Actual / Remaining breakdown for one Labor Type.

    Task names come from two different vocabularies (Estimate CSV
    "Task" text vs Labor CSV "Product/Service" text), so most tasks
    will only have one side filled in -- that mirrors how the outer
    summary table already handles Labor Types that only appear on one
    side.

    Rows are grouped rather than interleaved alphabetically: every
    task with a quoted value comes first (sorted by name), followed by
    every actual-only task (also sorted by name). This keeps quoted
    tasks together instead of scattering them between actual-only
    tasks.

    Returns (breakdown_df, quoted_row_count) -- quoted_row_count is
    how many rows at the top of breakdown_df belong to the "has a
    quote" group, so a caller can draw a divider or split the table
    at that point.
    """
    # Actual hours logged against this Labor Type, per task/service.
    task_actual = (
        labor_df[labor_df["Labor Type"] == labor_type]
        .groupby("Service")["Hours"]
        .sum()
    )

    # Quoted hours for this Labor Type, per task.
    task_quoted = (
        estimate_rows[estimate_rows["Normalized Labor Type"] == labor_type]
        .groupby("Task")["Required Hrs"]
        .sum()
    )

    quoted_task_names = sorted(task_quoted.index)

    # Tasks with actual hours but no matching quoted task name.
    actual_only_task_names = sorted(
        set(task_actual.index) - set(task_quoted.index)
    )

    ordered_task_names = quoted_task_names + actual_only_task_names

    rows = []

    for task_name in ordered_task_names:
        quoted = float(task_quoted.get(task_name, 0))
        actual = float(task_actual.get(task_name, 0))

        rows.append(
            {
                "Task": task_name,
                "Quoted Hours": round(quoted, 2),
                "Actual Hours": round(actual, 2),
                "Remaining Hours": round(quoted - actual, 2),
            }
        )

    breakdown_df = pd.DataFrame(rows)
    quoted_row_count = len(quoted_task_names)

    return breakdown_df, quoted_row_count

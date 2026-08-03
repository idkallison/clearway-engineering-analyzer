from io import BytesIO

import pandas as pd

import csv_reading_helpers as csv_h
import labor_helpers as lab_h


# =========================================================
# Master task map helpers
# =========================================================
#
# The master task map is an OPTIONAL csv the user can upload that maps
# every known task / service name directly to a Labor Type, so that
# new tasks can be recognized without editing the if-statements in
# labor_helpers.map_service / estimate_helpers.infer_estimate_labor_type.
#
# It needs two columns:
#   - a task/service name column, e.g. "Task" or "Product/Service Name"
#   - a "Labor Type" column with one of the app's canonical categories:
#     Engineering, Programming, Assembly - Electrical,
#     Assembly - Mechanical, Admin, Installation, Pre-Sale, Non-Project
#
# NOTE: a raw QuickBooks "Products/Services List" export (Categories +
# Product/Service Name) does NOT include this Labor Type column on its
# own -- the Categories column only holds broad codes like "T.B" which
# don't map 1:1 to a single Labor Type. If the user uploads a file like
# that, load_task_map will raise a clear error asking them to add a
# Labor Type column.

TASK_NAME_COLUMNS = [
    "Task",
    "Product/Service Name",
    "Product/Service full name",
    "Service",
    "Service Name",
]

LABOR_TYPE_COLUMNS = [
    "Labor Type",
    "Normalized Labor Type",
    "Final Labor Type",
]


def _find_column(columns, candidates):
    lowered = {
        str(column).strip().lower(): column
        for column in columns
    }

    for candidate in candidates:
        key = candidate.strip().lower()
        if key in lowered:
            return lowered[key]

    return None


def load_task_map(uploaded_file):
    """
    Reads an optional master task map CSV and returns a dict mapping
    normalized task/service names to a Labor Type string.

    Blank cells in the Labor Type column are forward-filled, in case
    the CSV was exported from Excel with merged cells (same pattern
    used for the Estimate CSV's Section column).
    """
    file_bytes = csv_h.uploaded_file_bytes(uploaded_file)
    csv_text = csv_h.decode_csv_bytes(file_bytes)

    dataframe = pd.read_csv(BytesIO(csv_text.encode("utf-8")))
    dataframe.columns = [
        str(column).strip() for column in dataframe.columns
    ]

    task_column = _find_column(
        dataframe.columns, TASK_NAME_COLUMNS
    )

    labor_type_column = _find_column(
        dataframe.columns, LABOR_TYPE_COLUMNS
    )

    if task_column is None:
        raise ValueError(
            "Could not find a task-name column. Expected one of: "
            + ", ".join(TASK_NAME_COLUMNS)
        )

    if labor_type_column is None:
        raise ValueError(
            "Could not find a 'Labor Type' column. Add a column named "
            "'Labor Type' with one of: Engineering, Programming, "
            "Assembly - Electrical, Assembly - Mechanical, Admin, "
            "Installation, Pre-Sale, Non-Project (a plain 'Categories' "
            "code like T.B is not specific enough on its own)."
        )

    dataframe[labor_type_column] = (
        dataframe[labor_type_column]
        .where(
            dataframe[labor_type_column]
            .astype(str)
            .str.strip()
            .ne("")
        )
        .ffill()
    )

    task_map = {}

    for _, row in dataframe.iterrows():
        task_value = row[task_column]
        labor_value = row[labor_type_column]

        if pd.isna(task_value) or pd.isna(labor_value):
            continue

        normalized_task = (
            lab_h.clean_service_name(task_value)
            .lower()
            .strip()
        )

        labor_type = str(labor_value).strip()

        if normalized_task and labor_type:
            task_map[normalized_task] = labor_type

    if not task_map:
        raise ValueError(
            "No usable task -> Labor Type rows were found in this file."
        )

    return task_map

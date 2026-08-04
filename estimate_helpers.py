import pandas as pd


# =========================================================
# Estimate helpers
# =========================================================
#
# Cleaning and classifying rows from the Estimate CSV (quoted hours).
# Two Estimate templates exist in the wild (old and new -- see
# prepare_estimate_dataframe below) so most of this file is about
# normalizing both shapes into one consistent set of columns.


def normalize_original_labor_type(value):
    """
    Normalize labor-type names found in older Estimate CSV files.
    Returns None if the value doesn't match a known alias.
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
    task_map=None,
):
    """
    Use the task first because several Estimate sheets have incorrect
    or overly broad values in the Labor Type column.

    If task_map is provided (from an uploaded master task map CSV),
    an exact match there takes priority over everything below -- this
    is also how a custom category (not one of the 9 built-ins) can
    end up as a Labor Type here.
    """
    task_text = str(task).strip().lower()
    section_text = str(section).strip().lower()
    notes_text = str(notes).strip().lower()

    if task_map:
        mapped = task_map.get(task_text)
        if mapped:
            return mapped

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

    # None of the keyword rules matched -- fall back to whatever was
    # already in the Labor Type column, if it's a recognizable value.
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

    # Still nothing -- Other/Unmapped, and flagged for review since
    # this is an Estimate row (see pipeline_helpers.run_analysis).
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


def prepare_estimate_dataframe(estimate_df, task_map=None):
    """
    Supports both normal Estimate CSV templates:

    Old:
      Task, Required Hrs, Labor Type, ...

    New:
      [Section column], Task, Level of experience, Required Hrs, ...

    task_map, if provided, is an optional dict from an uploaded master
    task map CSV that overrides the built-in matching rules.
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

    # Non-numeric hours (blank rows, "-" separators) become 0 rather
    # than raising, since those rows get filtered out below anyway.
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
        # Forward-fill the section name down through the rows it
        # applies to, matching how merged Excel cells come through in
        # an exported CSV.
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

    # Keep only real task rows: a Task name and a positive hour count.
    # This drops blank spacer rows and the "-" totals rows seen in the
    # raw exports.
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
                task_map=task_map,
            ),
            axis=1,
        )
    )

    return estimate_rows

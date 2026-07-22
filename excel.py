import csv
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

import pandas as pd


SECTION_PREFIX_MAP = {
    "pre-sale": "T.P",
    "engineering": "T.E",
    "build/program/debug": "T.B",
    "fat": "T.F",
    "ship/install": "T.I",
    "misc.": "T.M",
    "misc": "T.M",
    "non-project": "T.N",
    "service": "T.S",
}

TASK_NAME_MAP = {
    "sales call": "Sales Call",
    "project concept": "Project Concept",
    "research/quoting": "Research/Quoting",
    "mechanical design": "Mechanical Design",
    "electrical design": "Electrical Design",
    "programming": "Programming",
    "research/testing": "Research/Testing",
    "mechanical assembly": "Mechanical Assembly",
    "electrical assembly": "Electrical Assembly",
    "testing": "Testing",
    "preparation": "Preparation",
    "customer run-off": "Customer Run-Off",
    "packaging/delivery": "Packaging/Delivery",
    "installation - mech/elect": "Installation - Mech/Elect",
    "installation - debug": "Installation - Debug",
    "documentation red lines": "Documentation Red Lines",
    "start-up": "Start-up",
    "other": "Other",
}


def find_sheet_name(workbook: pd.ExcelFile, requested_name: str) -> str:
    lookup = {
        str(sheet).strip().lower(): sheet
        for sheet in workbook.sheet_names
    }

    actual_name = lookup.get(requested_name.strip().lower())

    if actual_name is None:
        raise ValueError(
            f"Could not find the '{requested_name}' worksheet. "
            f"Worksheets found: {workbook.sheet_names}"
        )

    return actual_name


def clean_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_task_name(task: str) -> str:
    normalized = clean_text(task)
    return TASK_NAME_MAP.get(normalized.lower(), normalized)


def map_new_template_row(task, section):
    task_text = normalize_task_name(task)
    section_text = clean_text(section).lower()
    prefix = SECTION_PREFIX_MAP.get(section_text)

    if not prefix:
        return "Unmapped", "Unmapped", "Needs review"

    if not task_text:
        return "Unmapped", "Unmapped", "Needs review"

    detailed_type = f"{prefix}.{task_text}"
    return prefix, detailed_type, "Exact from section/task"


def map_old_template_row(task, labor_type, notes):
    task_text = clean_text(task)
    task_lower = task_text.lower()
    labor_lower = clean_text(labor_type).lower()
    notes_lower = clean_text(notes).lower()
    combined = f"{task_lower} {notes_lower}"

    # Pre-sale
    if "sales call" in combined:
        return "T.P", "T.P.Sales Call", "Inferred from task"
    if "project concept" in combined:
        return "T.P", "T.P.Project Concept", "Inferred from task"
    if "research/quoting" in combined or "quoting" in combined:
        return "T.P", "T.P.Research/Quoting", "Inferred from task"

    # Engineering design
    if "mechanical design" in combined:
        return "T.E", "T.E.Mechanical Design", "Inferred from task"
    if (
        "electrical design" in combined
        or "controls design" in combined
        or "control design" in combined
    ):
        return "T.E", "T.E.Electrical Design", "Inferred from task"
    if "design" in combined:
        mechanical_words = (
            "frame", "guard", "table", "eoat", "chute",
            "guide", "mount", "docking", "part separation"
        )
        electrical_words = (
            "electrical", "controls", "control", "interface"
        )

        if any(word in combined for word in electrical_words):
            return "T.E", "T.E.Electrical Design", "Inferred from task"
        if any(word in combined for word in mechanical_words):
            return "T.E", "T.E.Mechanical Design", "Inferred from task"
        return "T.E", "T.E.Other", "Needs review"

    # Build
    if "mechanical assembly" in combined or "mechanical build" in combined:
        return "T.B", "T.B.Mechanical Assembly", "Inferred from task"
    if (
        "electrical assembly" in combined
        or "electrical build" in combined
        or "build/wire" in combined
        or "wiring" in combined
    ):
        return "T.B", "T.B.Electrical Assembly", "Inferred from task"
    if "build - eoat" in combined or "assembly" in labor_lower:
        if "electrical" in labor_lower:
            return "T.B", "T.B.Electrical Assembly", "Inferred from labor type"
        return "T.B", "T.B.Mechanical Assembly", "Inferred from labor type"
    if "program" in combined or labor_lower == "programming":
        return "T.B", "T.B.Programming", "Inferred from task/labor type"
    if "testing" in combined or "debug" in combined:
        return "T.B", "T.B.Testing", "Inferred from task"
    if "procurement" in combined:
        return "T.B", "T.B.Procurement", "Inferred from task"

    # Installation
    if "documentation red" in combined:
        return "T.I", "T.I.Documentation Red Lines", "Inferred from task"
    if "packaging" in combined or "delivery" in combined:
        return "T.I", "T.I.Packaging/Delivery", "Inferred from task"
    if "start-up" in combined or "startup" in combined:
        return "T.I", "T.I.Start-up", "Inferred from task"
    if "install" in combined:
        if "debug" in combined:
            return "T.I", "T.I.Installation - Debug", "Inferred from task"
        return "T.I", "T.I.Installation - Mech/Elect", "Inferred from task"

    # Miscellaneous / fallback from old Labor Type
    if labor_lower == "admin":
        return "T.M", "T.M.Office/Admin/Accounting", "Needs review"
    if "engineering" in labor_lower:
        return "T.E", "T.E.Other", "Needs review"

    return "Unmapped", "Unmapped", "Needs review"


def create_estimate_export(
    workbook_path: Path,
    estimate_sheet: str,
) -> pd.DataFrame:
    estimate_df = pd.read_excel(
        workbook_path,
        sheet_name=estimate_sheet,
        header=4,
        engine="openpyxl",
    )

    estimate_df.columns = [
        str(column).strip()
        for column in estimate_df.columns
    ]

    if "Required Hrs" not in estimate_df.columns:
        raise ValueError(
            "The Estimate worksheet does not contain 'Required Hrs'. "
            f"Columns found: {estimate_df.columns.tolist()}"
        )

    estimate_df["Required Hrs"] = pd.to_numeric(
        estimate_df["Required Hrs"],
        errors="coerce",
    )

    if "Task" not in estimate_df.columns:
        estimate_df["Task"] = ""

    if "Notes" not in estimate_df.columns:
        estimate_df["Notes"] = ""

    output_rows = []

    # New template: first unnamed column contains sections.
    if "Level of experience" in estimate_df.columns:
        section_column = next(
            (
                column
                for column in estimate_df.columns
                if column.startswith("Unnamed:")
            ),
            None,
        )

        if section_column is None:
            estimate_df["Section"] = ""
        else:
            estimate_df["Section"] = (
                estimate_df[section_column]
                .ffill()
                .astype(str)
                .str.strip()
            )

        valid_rows = estimate_df[
            estimate_df["Task"].notna()
            & estimate_df["Required Hrs"].notna()
            & (estimate_df["Required Hrs"] > 0)
        ].copy()

        for _, row in valid_rows.iterrows():
            summary_type, detailed_type, mapping_status = map_new_template_row(
                row["Task"],
                row["Section"],
            )

            output_rows.append(
                {
                    "Task": clean_text(row["Task"]),
                    "Required Hrs": float(row["Required Hrs"]),
                    "Summary Type": summary_type,
                    "Detailed Type": detailed_type,
                    "Mapping Status": mapping_status,
                    "Original Labor Type": "",
                    "Notes": clean_text(row["Notes"]),
                }
            )

    # Old template: use task and broad Labor Type.
    elif "Labor Type" in estimate_df.columns:
        valid_rows = estimate_df[
            estimate_df["Task"].notna()
            & estimate_df["Required Hrs"].notna()
            & (estimate_df["Required Hrs"] > 0)
        ].copy()

        for _, row in valid_rows.iterrows():
            summary_type, detailed_type, mapping_status = map_old_template_row(
                row["Task"],
                row["Labor Type"],
                row["Notes"],
            )

            output_rows.append(
                {
                    "Task": clean_text(row["Task"]),
                    "Required Hrs": float(row["Required Hrs"]),
                    "Summary Type": summary_type,
                    "Detailed Type": detailed_type,
                    "Mapping Status": mapping_status,
                    "Original Labor Type": clean_text(row["Labor Type"]),
                    "Notes": clean_text(row["Notes"]),
                }
            )

    else:
        raise ValueError(
            "The Estimate worksheet must contain either "
            "'Level of experience' or 'Labor Type'. "
            f"Columns found: {estimate_df.columns.tolist()}"
        )

    return pd.DataFrame(output_rows)


def write_estimate_csv(
    estimate_df: pd.DataFrame,
    output_path: Path,
    source_file_name: str,
) -> None:
    columns = [
        "Task",
        "Required Hrs",
        "Summary Type",
        "Detailed Type",
        "Mapping Status",
        "Original Labor Type",
        "Notes",
    ]

    with output_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as csv_file:
        writer = csv.writer(csv_file)

        # Keep four metadata rows so app.py can use header=4.
        writer.writerow(["Estimate Export"])
        writer.writerow(["Generated from Excel"])
        writer.writerow([source_file_name])
        writer.writerow(["---"])
        writer.writerow(columns)

        for _, row in estimate_df.iterrows():
            writer.writerow([
                row.get(column, "")
                for column in columns
            ])


def convert_workbook(workbook_path: Path):
    workbook = pd.ExcelFile(
        workbook_path,
        engine="openpyxl",
    )

    labor_sheet = find_sheet_name(workbook, "Labor")
    estimate_sheet = find_sheet_name(workbook, "Estimate")

    output_folder = workbook_path.parent / "Converted CSV"
    output_folder.mkdir(exist_ok=True)

    labor_output = output_folder / (
        f"{workbook_path.stem} - Labor.csv"
    )
    estimate_output = output_folder / (
        f"{workbook_path.stem} - Estimate.csv"
    )

    # Preserve the Labor worksheet exactly, including the first four rows.
    labor_raw = pd.read_excel(
        workbook_path,
        sheet_name=labor_sheet,
        header=None,
        engine="openpyxl",
    )

    labor_raw.to_csv(
        labor_output,
        index=False,
        header=False,
        encoding="utf-8-sig",
    )

    estimate_export = create_estimate_export(
        workbook_path,
        estimate_sheet,
    )

    write_estimate_csv(
        estimate_export,
        estimate_output,
        workbook_path.name,
    )

    return labor_output, estimate_output


def main():
    root = tk.Tk()
    root.withdraw()

    selected_files = filedialog.askopenfilenames(
        title="Select Clearway Excel workbook(s)",
        filetypes=[
            ("Excel workbooks", "*.xlsx *.xlsm"),
            ("All files", "*.*"),
        ],
    )

    if not selected_files:
        return

    successes = []
    errors = []

    for selected_file in selected_files:
        workbook_path = Path(selected_file)

        try:
            labor_csv, estimate_csv = convert_workbook(
                workbook_path
            )

            successes.append(
                f"{workbook_path.name}\n"
                f"  Labor: {labor_csv.name}\n"
                f"  Estimate: {estimate_csv.name}"
            )
        except Exception as error:
            errors.append(
                f"{workbook_path.name}: {error}"
            )

    messages = []

    if successes:
        output_folder = (
            Path(selected_files[0]).parent
            / "Converted CSV"
        )
        messages.append(
            "Conversion completed.\n\n"
            f"Saved in:\n{output_folder}\n\n"
            + "\n\n".join(successes)
        )

    if errors:
        messages.append(
            "\n\nErrors:\n"
            + "\n".join(errors)
        )

    final_message = "\n".join(messages)

    if errors and not successes:
        messagebox.showerror(
            "Excel to CSV Converter",
            final_message,
        )
    elif errors:
        messagebox.showwarning(
            "Excel to CSV Converter",
            final_message,
        )
    else:
        messagebox.showinfo(
            "Excel to CSV Converter",
            final_message,
        )


if __name__ == "__main__":
    main()

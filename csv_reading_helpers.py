

from io import BytesIO
import pandas as pd


# =========================================================
# CSV reading helpers
# =========================================================

def uploaded_file_bytes(uploaded_file):
    uploaded_file.seek(0)
    return uploaded_file.read()

#################

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

#################


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

#################


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

#################




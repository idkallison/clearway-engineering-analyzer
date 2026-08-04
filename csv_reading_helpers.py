from io import BytesIO

import pandas as pd


# =========================================================
# CSV reading helpers
# =========================================================
#
# Low-level file reading: decoding bytes, finding the real header row
# (QuickBooks exports have a few metadata rows above the table), and
# figuring out whether a given CSV is a Labor file or an Estimate
# file. Nothing here knows about Labor Types -- that classification
# happens in labor_helpers/estimate_helpers.

# The header sets that identify each file type. Used both by the
# original single-file flow and by auto-detection when files are
# dropped in bulk.
LABOR_REQUIRED_COLUMNS = {
    "Activity date",
    "Product/Service full name",
    "Duration",
}

ESTIMATE_REQUIRED_COLUMNS = {
    "Task",
    "Required Hrs",
}


def uploaded_file_bytes(uploaded_file):
    # Streamlit's UploadedFile is a stream, so rewind before every
    # read in case something upstream already consumed it.
    uploaded_file.seek(0)
    return uploaded_file.read()

#################

def decode_csv_bytes(file_bytes):
    # Try encodings in order of likelihood: modern UTF-8 exports
    # first, then legacy Windows/Excel CSVs.
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

    # Scan each candidate row's values (case/whitespace-insensitive)
    # for the full set of required column names.
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

    # First pass: read everything as raw strings with no header, just
    # to locate which row the real header lives on.
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

    # Second pass: re-read with normal dtype inference, now that we
    # know which row to treat as the header.
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


def detect_uploaded_file_type(uploaded_file):
    """
    Figure out whether an uploaded CSV is a Labor CSV or an Estimate
    CSV by checking whether each format's required header columns can
    be found in it. Used when files are dropped in bulk without the
    user labeling them.

    Returns (file_type, dataframe, header_row) where file_type is
    "labor", "estimate", or None if neither format's headers were
    found.
    """
    # Try Labor headers first, then Estimate headers -- whichever
    # required-column set is actually found in the file wins.
    try:
        dataframe, header_row = read_csv_with_detected_header(
            uploaded_file,
            LABOR_REQUIRED_COLUMNS,
        )
        return "labor", dataframe, header_row
    except Exception:
        pass

    try:
        dataframe, header_row = read_csv_with_detected_header(
            uploaded_file,
            ESTIMATE_REQUIRED_COLUMNS,
        )
        return "estimate", dataframe, header_row
    except Exception:
        pass

    return None, None, None

#################

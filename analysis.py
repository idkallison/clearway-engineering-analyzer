import pandas as pd


# -----------------------------
# Convert HH:MM to decimal hours
# -----------------------------
def duration_to_hours(duration):

    if pd.isna(duration):
        return 0

    hours, minutes = duration.split(":")

    return int(hours) + int(minutes) / 60

service_map = {

    "T.EE-Engineering/Design": "Engineering",
    "T.ED-CAD drafting": "Engineering",
    "T.ER-Process Testing": "Engineering",
    "T.FT-Testing": "Engineering",
    "T.ET-Startup/Debug/Testing": "Engineering",

    "Programming - PLC/HMI": "Programming",
    "T.EV-Vision System Programming": "Programming",

    "T.FB-Build/Assemble/Wire": "Assembly - Electrical",
    "T.MB-Build/Assemble": "Assembly - Mechanical",

    "T.AB-Procurement": "Admin",

    "T.FI-Installation": "Installation"
}

def analyze_project(labor_file, estimate_file):

    # -----------------------------
    # Read Labor CSV
    # -----------------------------
    labor_df = pd.read_csv(labor_file, header=4)

    labor_df = labor_df.drop(columns=labor_df.columns[0])

    labor_df = labor_df[labor_df["Activity date"].notna()]

    labor_df = labor_df.reset_index(drop=True)


    # -----------------------------
    # Clean service names
    # -----------------------------
    labor_df["Service"] = (
        labor_df["Product/Service full name"]
        .str.replace("Hourly:", "", regex=False)
        .str.replace("(deleted)", "", regex=False)
        .str.strip()
    )


    # -----------------------------
    # Convert duration to hours
    # -----------------------------
    labor_df["Hours"] = labor_df["Duration"].apply(duration_to_hours)


    # -----------------------------
    # Map labor types
    # -----------------------------
    labor_df["Labor Type"] = labor_df["Service"].map(service_map)

    labor_df["Labor Type"] = labor_df["Labor Type"].fillna("Other")


    # -----------------------------
    # Total actual hours
    # -----------------------------
    actual_hours = labor_df.groupby("Labor Type")["Hours"].sum()

      # -----------------------------
    # Read Estimate Excel
    # -----------------------------
    estimate_df = pd.read_excel(estimate_file)


    # Keep only rows with a labor type
    estimate_df = estimate_df[
        estimate_df["Labor Type"].notna()
    ]


    # Total quoted hours
    estimated_hours = (
        estimate_df
        .groupby("Labor Type")["Required Hrs"]
        .sum()
    )  
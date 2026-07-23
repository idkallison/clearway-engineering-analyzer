import os
import glob
import pandas as pd


# -----------------------------
# Convert HH:MM to decimal hours
# -----------------------------
def duration_to_hours(duration):

    if pd.isna(duration):
        return 0

    hours, minutes = duration.split(":")

    return int(hours) + int(minutes) / 60


# -----------------------------
# Map QuickBooks service names
# to estimate labor types
# -----------------------------
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


# -----------------------------
# Quoted hours from estimate
# -----------------------------
estimated_hours = {

    "Programming": 64,
    "Engineering": 76,
    "Assembly - Electrical": 32,
    "Assembly - Mechanical": 48,
    "Admin": 24,
    "Installation": 0
}


# -----------------------------
# Ask for project number
# -----------------------------
project_number = input("Enter project number: ")

project_folder = "Projects"

matches = glob.glob(os.path.join(project_folder, f"*{project_number}*.csv"))

if not matches:
    print("Project not found.")
    exit()

filename = matches[0]

print("\nLoading:")
print(os.path.basename(filename))


# -----------------------------
# Read CSV
# -----------------------------
df = pd.read_csv(filename, header=4)

df = df.drop(columns=df.columns[0])

df = df[df["Activity date"].notna()]

df = df.reset_index(drop=True)


# -----------------------------
# Clean service names
# -----------------------------
df["Service"] = (
    df["Product/Service full name"]
    .str.replace("Hourly:", "", regex=False)
    .str.replace("(deleted)", "", regex=False)
    .str.strip()
)


# -----------------------------
# Convert duration
# -----------------------------
df["Hours"] = df["Duration"].apply(duration_to_hours)


# -----------------------------
# Map to labor type
# -----------------------------
df["Labor Type"] = df["Service"].map(service_map)

df["Labor Type"] = df["Labor Type"].fillna("Other")


# -----------------------------
# Sum actual hours
# -----------------------------
actual_hours = df.groupby("Labor Type")["Hours"].sum()


print("\n")
print("=" * 65)
print("QUOTE VS ACTUAL LABOR")
print("=" * 65)

print(f'{"Labor Type":30}{"Quoted":>10}{"Actual":>12}{"Difference":>15}')

print("-" * 65)

total_est = 0
total_actual = 0

for labor in estimated_hours:

    est = estimated_hours[labor]

    act = actual_hours.get(labor, 0)

    diff = act - est

    total_est += est
    total_actual += act

    print(f"{labor:30}{est:10.2f}{act:12.2f}{diff:15.2f}")

print("-" * 65)

print(f'{"TOTAL":30}{total_est:10.2f}{total_actual:12.2f}{(total_actual-total_est):15.2f}')


# -----------------------------
# Show unmapped services
# -----------------------------
print("\n")

print("=" * 65)
print("UNMAPPED SERVICES")
print("=" * 65)

unmapped = df[df["Labor Type"] == "Other"]["Service"].value_counts()

if len(unmapped) == 0:
    print("None")
else:
    print(unmapped)

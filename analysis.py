import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Clearway Labor Analyzer",
    page_icon="📊",
    layout="wide"
)

# -----------------------------
# Convert HH:MM to decimal hours
# -----------------------------
def duration_to_hours(duration):
    if pd.isna(duration):
        return 0

    duration = str(duration)

    if ":" not in duration:
        return 0

    hours, minutes = duration.split(":")

    return int(hours) + int(minutes) / 60


# -----------------------------
# Map QuickBooks service names
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
# Map QuickBooks services
# -----------------------------
def map_service(service):

    service = str(service).strip()

    # Keep original mappings first
    if service in service_map:
        return service_map[service]

    # BUILD
    if service.startswith("T.B.Electrical Assembly"):
        return "Assembly - Electrical"

    if service.startswith("T.B.Mechanical Assembly"):
        return "Assembly - Mechanical"

    if service.startswith("T.B.Machine Shop"):
        return "Assembly - Mechanical"

    if service.startswith("T.B.Programming"):
        return "Programming"

    if service.startswith("T.B.Procurement"):
        return "Admin"

    if service.startswith("T.B.Testing"):
        return "Engineering"

    if service.startswith("T.B.Other"):
        return "Assembly - Mechanical"

    # ENGINEERING
    if service.startswith("T.E.Electrical Design"):
        return "Engineering"

    if service.startswith("T.E.Mechanical Design"):
        return "Engineering"

    if service.startswith("T.E.Research/Testing"):
        return "Engineering"

    if service.startswith("T.E.Other"):
        return "Engineering"

    if service.startswith("T.E.Programming"):
        return "Programming"

    # FACTORY ACCEPTANCE TEST
    if service.startswith("T.F."):
        return "Engineering"

    # INSTALLATION
    if service.startswith("T.I."):
        return "Installation"

    # MISC
    if service.startswith("T.M.Office"):
        return "Admin"

    if service.startswith("T.M.Project"):
        return "Admin"

    if service.startswith("T.M.Procurement"):
        return "Admin"

    if service.startswith("T.M.Part Pick Up"):
        return "Admin"

    if service.startswith("T.M.Travel"):
        return "Admin"

    if service.startswith("T.M.Training"):
        return "Admin"

    if service.startswith("T.M.Sales"):
        return "Admin"

    if service.startswith("T.M.R&D"):
        return "Engineering"

    if service.startswith("T.M.Summer Friday"):
        return "Admin"

    # NON-PROJECT
    if service.startswith("T.N."):
        return "Non-Project"

    # PRE-SALE
    if service.startswith("T.P."):
        return "Pre-Sale"

    # SERVICE
    if service.startswith("T.S.Engineering/Programming"):
        return "Programming"

    if service.startswith("T.S.Service Call"):
        return "Installation"

    if service.startswith("T.S.Other"):
        return "Installation"

    return "Other"

st.title("📊 Clearway Labor Analyzer")
st.write(
    "Upload a QuickBooks labor report and an estimate report to compare quoted vs. actual labor hours."
)

labor_file = st.file_uploader("📄 Labor CSV", type="csv")
estimate_file = st.file_uploader("📋 Estimate CSV", type="csv")

if labor_file and estimate_file:

    if st.button("🚀 Analyze Project", use_container_width=True):

        # -----------------------------
        # Read labor CSV
        # -----------------------------
        labor_df = pd.read_csv(labor_file, header=4)

        labor_df = labor_df.drop(columns=labor_df.columns[0])

        labor_df = labor_df[labor_df["Activity date"].notna()]

        labor_df["Service"] = (
            labor_df["Product/Service full name"]
            .astype(str)
            .str.replace("Hourly:", "", regex=False)
            .str.replace("(deleted)", "", regex=False)
            .str.strip()
        )

        labor_df["Hours"] = labor_df["Duration"].apply(duration_to_hours)

        labor_df["Labor Type"] = labor_df["Service"].apply(map_service)

        actual_hours = labor_df.groupby("Labor Type")["Hours"].sum()

        # -----------------------------
        # Read estimate CSV
        # -----------------------------
        estimate_df = pd.read_csv(estimate_file, header=4)

        estimate_df = estimate_df[
            estimate_df["Labor Type"].notna()
        ].copy()

        estimate_df["Required Hrs"] = pd.to_numeric(
            estimate_df["Required Hrs"],
            errors="coerce"
        ).fillna(0)

        estimated_hours = (
            estimate_df
            .groupby("Labor Type")["Required Hrs"]
            .sum()
        )

        labor_types = sorted(
            set(actual_hours.index).union(set(estimated_hours.index))
        )

        results = []

        total_quote = 0
        total_actual = 0

        for labor in labor_types:

            quoted = float(estimated_hours.get(labor, 0))
            actual = float(actual_hours.get(labor, 0))
            diff = actual - quoted

            total_quote += quoted
            total_actual += actual

            results.append({
                "Labor Type": labor,
                "Quoted Hours": round(quoted, 2),
                "Actual Hours": round(actual, 2),
                "Difference": round(diff, 2)
            })

        results_df = pd.DataFrame(results)

        # Summary cards
        st.divider()
        st.subheader("📋 Project Summary")

        c1, c2, c3 = st.columns(3)

        c1.metric("Quoted Hours", f"{total_quote:.2f}")
        c2.metric("Actual Hours", f"{total_actual:.2f}")
        c3.metric(
            "Difference",
            f"{(total_actual-total_quote):.2f}"
        )

        st.divider()

        st.subheader("📊 Quote vs Actual")

        st.dataframe(
            results_df,
            hide_index=True,
            use_container_width=True
        )

        st.divider()

        st.subheader("📈 Labor Comparison")

        chart_df = (
            results_df
            .set_index("Labor Type")[["Quoted Hours", "Actual Hours"]]
        )

        st.bar_chart(chart_df)

        st.divider()

        st.subheader("⚠️ Unmapped Services")

        unmapped = (
            labor_df[labor_df["Labor Type"] == "Other"]["Service"]
            .value_counts()
            .reset_index()
        )

        if len(unmapped) == 0:
            st.success("No unmapped services found.")
        else:
            unmapped.columns = ["Service", "Occurrences"]
            st.dataframe(
                unmapped,
                hide_index=True,
                use_container_width=True
            )

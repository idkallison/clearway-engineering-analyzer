

# =========================================================
# Labor helpers
# =========================================================


def duration_to_hours(duration):
    if pd.isna(duration):
        return 0.0

    text = str(duration).strip()

    if not text:
        return 0.0

    # Handles HH:MM and HH:MM:SS.
    if ":" in text:
        parts = text.split(":")

        try:
            hours = float(parts[0])
            minutes = float(parts[1])
            seconds = (
                float(parts[2])
                if len(parts) > 2
                else 0.0
            )

            return (
                hours
                + minutes / 60
                + seconds / 3600
            )
        except (ValueError, IndexError):
            return 0.0

    # Handles a plain numeric number of hours.
    numeric_value = pd.to_numeric(
        text,
        errors="coerce",
    )

    if pd.isna(numeric_value):
        return 0.0

    return float(numeric_value)


def clean_service_name(service):
    return (
        str(service)
        .replace("Hourly:", "")
        .replace("(deleted)", "")
        .strip()
    )


def map_service(service):
    """
    Normalize actual QuickBooks services to the broad labor categories
    used by this version of the report.
    """
    text = clean_service_name(service)
    lower = text.lower()

    # New T.B hierarchy
    if lower.startswith("t.b.electrical assembly"):
        return "Assembly - Electrical"

    if lower.startswith("t.b.mechanical assembly"):
        return "Assembly - Mechanical"

    if lower.startswith("t.b.machine shop"):
        return "Assembly - Mechanical"

    if lower.startswith("t.b.programming"):
        return "Programming"

    if lower.startswith("t.b.procurement"):
        return "Admin"

    if lower.startswith("t.b.testing"):
        return "Engineering"

    if lower.startswith("t.b.other"):
        return "Assembly - Mechanical"

    # New T.E hierarchy
    if lower.startswith("t.e.programming"):
        return "Programming"

    if lower.startswith("t.e."):
        return "Engineering"

    # FAT
    if lower.startswith("t.f."):
        return "Engineering"

    # Installation
    if lower.startswith("t.i."):
        return "Installation"

    # Miscellaneous
    if lower.startswith("t.m.r&d"):
        return "Engineering"

    if lower.startswith("t.m."):
        return "Admin"

    # Non-project
    if lower.startswith("t.n."):
        return "Non-Project"

    # Pre-sale
    if lower.startswith("t.p."):
        return "Pre-Sale"

    # Service
    if lower.startswith(
        "t.s.engineering/programming"
    ):
        return "Programming"

    if lower.startswith("t.s."):
        return "Installation"

    # Legacy QuickBooks service names
    legacy_exact = {
        "t.ee-engineering/design": "Engineering",
        "t.ed-cad drafting": "Engineering",
        "t.er-process testing": "Engineering",
        "t.ft-testing": "Engineering",
        "t.et-startup/debug/testing": "Engineering",
        "programming - plc/hmi": "Programming",
        "t.ev-vision system programming": "Programming",
        "t.fb-build/assemble/wire": "Assembly - Electrical",
        "t.mb-build/assemble": "Assembly - Mechanical",
        "t.ab-procurement": "Admin",
        "t.fi-installation": "Installation",
    }

    if lower in legacy_exact:
        return legacy_exact[lower]

    return "Other"


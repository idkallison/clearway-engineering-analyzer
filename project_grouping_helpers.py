import difflib
import re
from pathlib import Path


# =========================================================
# Project grouping helpers
# =========================================================
#
# When the user drops a whole folder of files (multiple projects'
# worth of Labor + Estimate CSVs), we need to guess which files belong
# to the same project from their filenames. This is a best-effort
# heuristic -- the UI always shows the result in an editable table so
# the user can fix any mis-grouping by hand.

_NOISE_WORDS = {
    "labor", "labour", "estimate", "estimates", "quote", "quoted",
    "hours", "hrs", "export", "exported", "csv", "utf8", "utf",
    "report", "final", "data", "sheet", "list", "clearway",
}

_DATE_PATTERN = re.compile(r"\b\d{1,2}[-_/]\d{1,2}[-_/]\d{2,4}\b")
_VERSION_PATTERN = re.compile(r"\bv\d+\b")


def clean_project_key(filename):
    """
    Strip dates, version tags, and generic words like "labor" or
    "estimate" from a filename to guess the underlying project name.
    """
    name = Path(filename).stem.lower()
    name = _DATE_PATTERN.sub(" ", name)
    name = _VERSION_PATTERN.sub(" ", name)
    name = re.sub(r"[_\-]+", " ", name)

    words = [
        word
        for word in name.split()
        if word not in _NOISE_WORDS
    ]

    cleaned = " ".join(words).strip()

    return cleaned if cleaned else Path(filename).stem.strip()


def group_files_into_projects(filenames, similarity_threshold=0.55):
    """
    Groups filenames into projects using fuzzy matching on their
    cleaned keys. Returns a dict of {suggested_project_name: [filenames]}.
    """
    clusters = []

    for filename in filenames:
        key = clean_project_key(filename)

        best_cluster = None
        best_score = 0.0

        for cluster in clusters:
            score = difflib.SequenceMatcher(
                None, key, cluster["key"]
            ).ratio()

            if score > best_score:
                best_score = score
                best_cluster = cluster

        if best_cluster is not None and best_score >= similarity_threshold:
            best_cluster["files"].append(filename)
        else:
            clusters.append({"key": key, "files": [filename]})

    result = {}
    used_names = set()

    for cluster in clusters:
        label = cluster["key"] or "Project"
        final_label = label
        suffix = 2

        while final_label in used_names:
            final_label = f"{label} ({suffix})"
            suffix += 1

        used_names.add(final_label)
        result[final_label] = cluster["files"]

    return result

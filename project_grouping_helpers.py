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

# Generic words stripped out before comparing filenames, since they
# show up in every project's files and would otherwise make unrelated
# projects look similar.
_NOISE_WORDS = {
    "labor", "labour", "estimate", "estimates", "quote", "quoted",
    "hours", "hrs", "export", "exported", "csv", "utf8", "utf",
    "report", "final", "data", "sheet", "list", "clearway", "xlsx",
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

    # If everything got stripped out (an unusually generic filename),
    # fall back to the original stem rather than an empty key.
    return cleaned if cleaned else Path(filename).stem.strip()


def group_files_into_projects(filenames, fuzzy_threshold=0.85):
    """
    Groups filenames into projects.

    Pass 1: exact match on the cleaned key. This is the reliable case
    -- e.g. "Project 5571 - Labor.csv" and "Project 5571 - Estimate.csv"
    clean down to the identical key "project 5571", so they group
    correctly even though many *different* projects in the same batch
    also share lots of common words (like "engineering", "inspection",
    "conveyor").

    Pass 2: any key that's still a singleton after pass 1 (e.g. a typo
    or slightly different naming) gets a chance to fuzzy-merge into an
    existing group, but only at a strict similarity threshold -- loose
    fuzzy matching is what caused unrelated projects to merge before,
    since sharing a handful of common words was enough to look similar.
    """
    exact_groups = {}

    for filename in filenames:
        key = clean_project_key(filename)
        exact_groups.setdefault(key, []).append(filename)

    # Groups with 2+ files already found their pair/set exactly.
    settled = {
        key: files
        for key, files in exact_groups.items()
        if len(files) > 1
    }

    # Groups with only 1 file are candidates for the fuzzy pass below.
    leftovers = {
        key: files
        for key, files in exact_groups.items()
        if len(files) == 1
    }

    for key, files in list(leftovers.items()):
        best_key = None
        best_score = 0.0

        # Find the closest already-settled group, if any is close
        # enough to trust.
        for candidate_key in settled:
            score = difflib.SequenceMatcher(
                None, key, candidate_key
            ).ratio()

            if score > best_score:
                best_score = score
                best_key = candidate_key

        if best_key is not None and best_score >= fuzzy_threshold:
            settled[best_key].extend(files)
        else:
            # No close enough match -- this file stays its own group.
            settled[key] = files

    result = {}
    used_names = set()

    # De-duplicate final group labels in case two different keys
    # happened to clean down to the same display name.
    for key, files in settled.items():
        label = key or "Project"
        final_label = label
        suffix = 2

        while final_label in used_names:
            final_label = f"{label} ({suffix})"
            suffix += 1

        used_names.add(final_label)
        result[final_label] = files

    return result

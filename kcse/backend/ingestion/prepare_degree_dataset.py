import os
import re
import pandas as pd


DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))
SOURCE_FILE = os.path.join(DATA_DIR, "DEGREE_CUTOFFS_ENRICHED_FINAL (1).xlsx")
OUTPUT_XLSX = os.path.join(DATA_DIR, "DEGREE_CUTOFFS_ENRICHED_CLEAN.xlsx")
OUTPUT_CSV = os.path.join(DATA_DIR, "DEGREE_CUTOFFS_ENRICHED_CLEAN.csv")


EXPECTED_COLUMNS = [
    "#",
    "prog_code",
    "institution_name",
    "programme_name",
    "cutoff_2018",
    "cutoff_2019",
    "cutoff_2020",
    "cutoff_2021",
    "cutoff_2022",
    "cutoff_2023",
    "cutoff_2024",
    "qualification_type",
    "minimum_mean_grade",
    "subject_requirements",
    "cluster_or_points_info",
    "course_description",
    "career_paths",
    "notes",
    "source_reference",
]


def clean_text(value):
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "not available", "n/a", "-"}:
        return ""
    return text


def normalize_mean_grade(value):
    text = clean_text(value)
    if not text:
        return ""
    match = re.search(r"\b([A-E][+-]?)\b", text.upper())
    if match:
        return match.group(1)
    return text


def main():
    df = pd.read_excel(SOURCE_FILE)
    df.columns = [str(col).strip() for col in df.columns]
    df = df.loc[:, ~df.columns.str.contains(r"^Unnamed", case=False)]

    for column in EXPECTED_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    df = df[EXPECTED_COLUMNS].copy()

    for column in df.columns:
        df[column] = df[column].map(clean_text)

    # Drop placeholder/category/header-style rows carried over from spreadsheets.
    mask_valid = (
        (df["prog_code"] != "")
        & (df["institution_name"] != "")
        & (df["programme_name"] != "")
        & (df["programme_name"].str.lower() != "programme_name")
        & (df["institution_name"].str.lower() != "institution_name")
        & (df["prog_code"].str.lower() != "prog_code")
    )
    df = df.loc[mask_valid].copy()

    # Normalize a few high-value fields for easier downstream use.
    df["qualification_type"] = df["qualification_type"].replace(
        {
            "Bachelor's Degree": "Degree",
            "Bachelors Degree": "Degree",
            "Bachelor Degree": "Degree",
        }
    )
    df.loc[df["qualification_type"] == "", "qualification_type"] = "Degree"

    df["minimum_mean_grade"] = df["minimum_mean_grade"].map(normalize_mean_grade)

    df.to_excel(OUTPUT_XLSX, index=False)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")

    print(f"Saved cleaned dataset: {OUTPUT_XLSX}")
    print(f"Saved cleaned dataset: {OUTPUT_CSV}")
    print(f"Rows: {len(df)}")
    print(f"Columns: {len(df.columns)}")


if __name__ == "__main__":
    main()

"""
Simple script to merge a directory of CSVs into a single document.
Run with python merge_csvs.py "C:/path/to/your/folder"

Gracefully handles missing or invalid directories.
Automatically skips duplicate headers if they appear in the middle of the data.
Does not sort the files — it merges in filesystem order (which is fine for your use case).
"""

from pathlib import Path
import pandas as pd
import sys

def merge_csvs(directory):
    path = Path(directory)
    if not path.is_dir():
        print(f"Error: {directory} is not a valid directory.")
        return

    all_files = list(path.glob("*.csv"))
    if not all_files:
        print(f"No CSV files found in {directory}")
        return

    dfs = []
    header = None
    for file in all_files:
        df = pd.read_csv(file)
        if header is None:
            header = list(df.columns)
        else:
            # Drop any repeated header rows
            df = df[df[df.columns[0]] != header[0]]
        dfs.append(df)

    df_merged = pd.concat(dfs, ignore_index=True)

    output_file = path / f"merged{path.name}.csv"
    df_merged.to_csv(output_file, index=False)

    print(f"Merged {len(all_files)} CSV files into: {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python merge_csvs.py <directory_path>")
    else:
        merge_csvs(sys.argv[1])

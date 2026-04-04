import json
import pandas as pd
from typing import List, Any


class FewShotPosts:
    def __init__(self, file_path: str = "data/processed_posts.json"):
        self.df: pd.DataFrame | None = None
        self.unique_tags: set[str] = set()
        self.load_posts(file_path)

    def load_posts(self, file_path: str):
        with open(file_path, encoding="utf-8") as f:
            posts = json.load(f)
        # Normalize into DataFrame
        self.df = pd.json_normalize(posts)

        # Ensure tags column exists and is a list for every row
        if "tags" not in self.df.columns:
            self.df["tags"] = [[] for _ in range(len(self.df))]
        else:
            # Replace missing/NaN with empty list
            self.df["tags"] = self.df["tags"].apply(lambda x: x if isinstance(x, list) else ([] if pd.isna(x) else [x]))

        # Add length category column based on line_count
        if "line_count" not in self.df.columns:
            # if missing, default to 0
            self.df["line_count"] = 0
        self.df["length"] = self.df["line_count"].apply(self.categorize_length)

        # Build unique tags robustly
        unique = set()
        for tags in self.df["tags"]:
            if isinstance(tags, (list, tuple, set)):
                unique.update(tags)
            elif tags is None:
                continue
            else:
                unique.add(str(tags))
        self.unique_tags = unique

    def categorize_length(self, line_count: int) -> str:
        try:
            lc = int(line_count)
        except Exception:
            lc = 0
        if lc < 5:
            return "Short"
        elif 5 <= lc <= 10:
            return "Medium"
        else:
            return "Long"

    def get_tags(self) -> List[str]:
        return sorted(self.unique_tags)

    def get_filtered_posts(self, length: str, language: str, tag: str) -> List[dict]:
        """
        Return list of posts that match language, length category and contain the given tag.
        """
        if self.df is None:
            return []

        # Defensive: ensure 'language' and 'length' columns exist
        df = self.df.copy()
        if "language" not in df.columns:
            df["language"] = None
        if "length" not in df.columns:
            df["length"] = df["line_count"].apply(self.categorize_length)

        # Filter rows
        df_filtered = df[
            (df["language"] == language) &
            (df["length"] == length) &
            (df["tags"].apply(lambda tags: tag in tags if isinstance(tags, (list, tuple, set)) else False))
        ]

        return df_filtered.to_dict(orient="records")


if __name__ == "__main__":
    fs = FewShotPosts()
    posts = fs.get_filtered_posts("Medium", "English", "Regression")
    print(posts)

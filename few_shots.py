"""Compatibility wrapper for processed post repository helpers."""

from linkedin_post_generator.repository import FewShotPosts, categorize_length, load_processed_posts

__all__ = ["FewShotPosts", "categorize_length", "load_processed_posts"]


if __name__ == "__main__":
    repository = FewShotPosts()
    print(repository.get_filtered_posts("Medium", "English", "Regression"))

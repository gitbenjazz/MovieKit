from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from moviekit import MovieRepository

repository = MovieRepository()
movies, seen, unseen = repository.update_watched_1001_outputs()

print("=" * 50)
print(f"Seen      : {len(seen)}")
print(f"Remaining : {len(unseen)}")
print(f"Progress  : {len(seen)/len(movies):.1%}")
print("=" * 50)

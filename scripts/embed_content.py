import json
import sys
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.embedder import embed_text
from storage.vectors import upsert_content_vector


def main():
    passages_dir = Path(__file__).parent.parent / "data" / "passages"
    passage_files = sorted(passages_dir.rglob("*.json"))

    if not passage_files:
        print(" No passage files found. Run from project root.")
        sys.exit(1)

    print(f"\n📚 Embedding {len(passage_files)} passages into content-library-index...")
    print("=" * 60)

    success_count = 0
    for f in passage_files:
        try:
            passage = json.loads(f.read_text())
            if "passage_id" not in passage:
                continue

            passage_id = passage["passage_id"]
            title = passage.get("title", "")
            difficulty_band = passage.get("difficulty_band", "")
            text = passage.get("text", "")

            if not text:
                print(f" {passage_id}: no text, skipping")
                continue

            print(f"  Embedding {passage_id} ({title})... ", end="", flush=True)
            vector = embed_text(text)

            metadata = {
                "passage_id": passage_id,
                "title": title,
                "difficulty_band": difficulty_band,
                "target_phoneme_patterns": passage.get("target_phoneme_patterns", []),
            }

            ok = upsert_content_vector(passage_id, vector, metadata)
            if ok:
                print(f"✓  ({len(vector)} dims)")
                success_count += 1
            else:
                print("Failed to store vector")

        except Exception as e:
            print(f"Error: {e}")

    print("=" * 60)
    if success_count == len(passage_files):
        print(f" Content library ready. {success_count} passages embedded.")
    else:
        print(f" {success_count}/{len(passage_files)} passages embedded successfully.")


if __name__ == "__main__":
    main()

import os
import json
from pathlib import Path
from datetime import datetime

# Directory containing your source documents (adjust as needed)
DOCS_ROOT = Path("../documents/cbc/")

# Output file for metadata index
INDEX_PATH = Path("document_index.json")

def scan_documents(root):
    metadata_list = []
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            if fname.startswith('.'):
                continue  # skip hidden files
            fpath = Path(dirpath) / fname
            rel_path = fpath.relative_to(root)
            ext = fpath.suffix.lower().lstrip('.')
            doc_type = ext if ext else 'unknown'
            title = fname.rsplit('.', 1)[0]
            uploaded = datetime.fromtimestamp(fpath.stat().st_mtime).isoformat()
            metadata = {
                "title": title,
                "type": doc_type,
                "path": str(rel_path),
                "uploaded": uploaded
            }
            metadata_list.append(metadata)
    return metadata_list

if __name__ == "__main__":
    docs = scan_documents(DOCS_ROOT)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(docs, f, indent=2)
    print(f"Indexed {len(docs)} documents from {DOCS_ROOT} to {INDEX_PATH}")

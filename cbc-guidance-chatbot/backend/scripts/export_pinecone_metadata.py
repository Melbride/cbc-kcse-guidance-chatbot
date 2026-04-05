
import os
import json
from pinecone import Pinecone
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set your Pinecone API key and environment

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENV = os.getenv("PINECONE_ENV")
INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")

if not (PINECONE_API_KEY and PINECONE_ENV and INDEX_NAME):
    raise RuntimeError("Please set PINECONE_API_KEY, PINECONE_ENVIRONMENT, and PINECONE_INDEX_NAME in your environment.")

pc = Pinecone(api_key=PINECONE_API_KEY, environment=PINECONE_ENV)
index = pc.Index(INDEX_NAME)

# Get all vector IDs
stats = index.describe_index_stats()
all_ids = []
for ns in stats['namespaces']:
    # Pinecone returns vector_count, but not IDs directly. You may need to keep IDs elsewhere for large indexes.
    # For small indexes, you can use fetch with known IDs or use upserted IDs if tracked.
    # Here, we assume default namespace and small index for demonstration.
    if ns == '':
        # If you have a way to get all IDs, use it here. Otherwise, this is a limitation.
        print("WARNING: Pinecone does not provide all IDs directly. Please ensure you have a list of IDs.")

# If you have a list of IDs, replace all_ids with that list.
# Example: all_ids = ['doc1', 'doc2', ...]
# For demonstration, we'll exit if no IDs are found.
if not all_ids:
    print("No IDs found. Please provide a list of document IDs to fetch metadata.")
    exit(1)

# Fetch metadata for each ID in batches
metadata_list = []
BATCH_SIZE = 100
for i in range(0, len(all_ids), BATCH_SIZE):
    batch_ids = all_ids[i:i+BATCH_SIZE]
    response = index.fetch(ids=batch_ids)
    for v in response['vectors'].values():
        metadata_list.append(v.get('metadata', {}))

# Save to document_index.json
with open("document_index.json", "w", encoding="utf-8") as f:
    json.dump(metadata_list, f, indent=2)

print(f"Exported {len(metadata_list)} document metadata entries to document_index.json")

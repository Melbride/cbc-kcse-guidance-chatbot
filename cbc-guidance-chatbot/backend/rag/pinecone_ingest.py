import os
from dotenv import load_dotenv
from langchain_pinecone import PineconeVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from .document_processor import DocumentProcessor  

#Load environment variables
load_dotenv()
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
print("INGEST INDEX:", PINECONE_INDEX_NAME)
#Initialize embeddings
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

#Load and chunk documents
print("Loading and chunking documents...")
processor = DocumentProcessor("../documents/cbc")
#To return document objects with metadata
documents = processor.load_and_chunk()  
print(f"\nTotal documents to upload: {len(documents)}")
print("\n Sample Document")
print(f"Content: {documents[0].page_content[:200]}...")
print(f"Metadata: {documents[0].metadata}")

#Group by folder to see distribution
from collections import Counter
folder_counts = Counter([doc.metadata.get('folder', 'unknown') for doc in documents])
print("\n Documents by Folder")
for folder, count in folder_counts.items():
    print(f"{folder}: {count} chunks")

#Confirm before uploading
print(f"\nUploading {len(documents)} chunks to Pinecone...")
input("Press Enter to continue or Ctrl+C to cancel...")

#Upload to Pinecone
vectorstore = PineconeVectorStore.from_documents(
    documents=documents,
    embedding=embeddings,
    index_name=PINECONE_INDEX_NAME,
)

#Append metadata to document_index.json 
import json
from pathlib import Path

index_path = Path("document_index.json")
docs_metadata = []
if index_path.exists():
    with open(index_path, "r", encoding="utf-8") as f:
        docs_metadata = json.load(f)

for doc in documents:
    meta = doc.metadata.copy()
    meta["preview"] = doc.page_content[:100]
    docs_metadata.append(meta)

with open(index_path, "w", encoding="utf-8") as f:
    json.dump(docs_metadata, f, indent=2)

print("Documents successfully stored in Pinecone with metadata!")

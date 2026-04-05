#import required libraries for document processing
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from .document_loader import load_documents

class DocumentProcessor:
    """
    Processes CBC curriculum documents for RAG (Retrieval-Augmented Generation) system.
    
    Purpose:
    - Loads documents from CBC curriculum files
    - Chunks documents into optimal sizes for vector search
    - Preserves metadata for source tracking and citation
    - Prepares documents for Pinecone vector database ingestion
    """
    
    def __init__(self, base_path: str = "../documents/cbc"):
        """
        Initialize document processor with default CBC documents path.
        
        Args:
            base_path: Path to CBC documents directory
        """
        self.base_path = Path(base_path)
        
        #configure text splitter for optimal chunking
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=600,        #optimal size for embedding models
            chunk_overlap=120,     #20% overlap for context continuity
            separators=["\n\n", "\n", ". ", " ", ""]  #hierarchical splitting
        )
        
    def load_and_chunk(self):
        """
        Load CBC documents and chunk them while preserving metadata.
        
        Process:
        1. Load all documents from directory
        2. Split documents into optimal chunks
        3. Filter out small/meaningless chunks
        4. Create Document objects with metadata
        5. Return structured chunks for vector database
        
        Returns:
            List of Document objects with content and metadata
        """
        #load all documents from cbc directory
        documents = load_documents(self.base_path)
        all_chunks = []
        
        #process each document
        for doc in documents:
            #split document into chunks
            text_chunks = self.text_splitter.split_text(doc["content"])
            
            #create document objects for each chunk
            for i, chunk in enumerate(text_chunks):
                #filter out very small chunks
                if len(chunk.strip()) < 50:
                    continue
                    
                #extract source path information
                source_path = Path(doc["source"])
                
                #create document with rich metadata
                chunk_document = Document(
                    page_content=chunk,
                    metadata={
                        "source": str(source_path),           #full file path
                        "filename": source_path.name,        #file name only
                        "folder": source_path.parent.name,   #directory name
                        "chunk_index": i,                    #chunk position in file
                        "file_type": source_path.suffix      #file extension
                    }
                )
                
                all_chunks.append(chunk_document)
                
        return all_chunks

#testing and demonstration code
if __name__ == "__main__":
    #initialize processor
    processor = DocumentProcessor()
    
    #process documents
    chunks = processor.load_and_chunk()
    
    #display results
    print(f"Total chunks created: {len(chunks)}")
    print("\nSample chunk with metadata:\n")
    print(f"Content: {chunks[0].page_content[:300]}...")
    print(f"Metadata: {chunks[0].metadata}")


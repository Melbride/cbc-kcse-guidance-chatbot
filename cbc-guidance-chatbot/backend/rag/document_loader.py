#import required libraries for document processing
from pathlib import Path
from pypdf import PdfReader
from docx import Document as DocxDocument

def load_pdf(file_path: Path) -> str:
    """
    Extract text content from PDF files for CBC document processing.
    
    Purpose:
    - Loads PDF documents from CBC curriculum files
    - Extracts readable text for RAG system
    - Handles corrupted or unreadable files gracefully
    
    Args:
        file_path: Path to PDF file to process
    
    Returns:
        Extracted text content as string, empty string if failed
    """
    try:
        #initialize pdf reader
        reader = PdfReader(file_path)
        text = []
        
        #extract text from each page
        for page in reader.pages:
            page_text = page.extract_text() or ""
            text.append(page_text)
        return "\n".join(text)
        
    except Exception as e:
        #error handling - log warning and return empty
        print(f"Warning: Could not load PDF {file_path}: {e}")
        return ""

def load_docx(file_path: Path) -> str:
    """
    Extract text content from DOCX files for CBC document processing.
    
    Purpose:
    - Loads Word documents from CBC curriculum files
    - Extracts paragraph text for RAG system
    - Handles corrupted or unreadable files gracefully
    
    Args:
        file_path: Path to DOCX file to process
    
    Returns:
        Extracted text content as string, empty string if failed
    """
    try:
        #initialize docx reader
        doc = DocxDocument(file_path)
        #extract text from all paragraphs
        paragraph_texts = [p.text for p in doc.paragraphs]
        return "\n".join(paragraph_texts)
        
    except Exception as e:
        #error handling - log warning and return empty
        print(f"Warning: Could not load DOCX {file_path}: {e}")
        return ""

def load_documents(base_path: Path) -> list[dict]:
    """
    Load and process all CBC curriculum documents from directory structure.
    
    Purpose:
    - Scans document directory for PDF and DOCX files
    - Extracts content from all readable documents
    - Structures data for RAG pipeline processing
    - Preserves source information for citation
    
    Args:
        base_path: Root directory containing CBC documents
    
    Returns:
        List of dictionaries with 'source' and 'content' keys
    """
    documents = []
    
    #recursively scan directory for documents
    for file_path in base_path.rglob("*"):
        #skip temporary office files
        if file_path.name.startswith("~$"):
            continue  
        #process pdf files
        if file_path.suffix.lower() == ".pdf":
            content = load_pdf(file_path) 
        #process docx files
        elif file_path.suffix.lower() == ".docx":
            content = load_docx(file_path)  
        #skip other file types
        else:
            continue
            
        #add document if content exists
        if content.strip():
            documents.append({
                "source": str(file_path),
                "content": content
            })
        else:
            print(f"Skipping empty file: {file_path}")   
    return documents

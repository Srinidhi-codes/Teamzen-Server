import os
import django
from PyPDF2 import PdfReader
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
import sys

# Capture API key BEFORE Django setup (Django might override environment)
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
print(f"DEBUG: API Key captured: {OPENAI_API_KEY[:20] if OPENAI_API_KEY else 'NOT FOUND'}...")

# Setup Django environment
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from ai_engine.models import PolicyDocument

def ingest_pdf(file_path):
    print(f"Starting ingestion for: {file_path}")
    
    # 1. Read PDF
    reader = PdfReader(file_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text()
    
    # 2. Split Text
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
        separators=["\n\n", "\n", " ", ""]
    )
    chunks = text_splitter.split_text(text)
    print(f"Split into {len(chunks)} chunks.")

    # 3. Generate Embeddings and Store
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not found in environment variables")
    
    print(f"Using API key: {OPENAI_API_KEY[:20]}...")
    embeddings_model = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
    
    for i, chunk in enumerate(chunks):
        embedding = embeddings_model.embed_query(chunk)
        PolicyDocument.objects.create(
            title=os.path.basename(file_path),
            content=chunk,
            embedding=embedding,
            metadata={"chunk_index": i, "source": file_path}
        )
    
    print("Ingestion complete!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ingest_policy.py <path_to_pdf>")
    else:
        ingest_pdf(sys.argv[1])

import os
import django
from PyPDF2 import PdfReader
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from django.contrib.postgres.search import SearchVector
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
    
    # 1. Read PDF per page
    reader = PdfReader(file_path)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
        separators=["\n\n", "\n", " ", ""]
    )

    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not found in environment variables")
    
    print(f"Using API key: {OPENAI_API_KEY[:20]}...")
    embeddings_model = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
    
    created_ids = []
    global_chunk_index = 0
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        if not page_text.strip():
            continue
        chunks = text_splitter.split_text(page_text)
        print(f"Page {page_number}: {len(chunks)} chunks.")
        for chunk in chunks:
            embedding = embeddings_model.embed_query(chunk)
            doc = PolicyDocument.objects.create(
                title=os.path.basename(file_path),
                content=chunk,
                embedding=embedding,
                page_number=page_number,
                metadata={
                    "chunk_index": global_chunk_index,
                    "page_number": page_number,
                    "source": file_path,
                },
            )
            created_ids.append(doc.id)
            global_chunk_index += 1

    if created_ids:
        PolicyDocument.objects.filter(id__in=created_ids).update(
            search_vector=SearchVector('content', config='english')
        )
    
    print(f"Ingestion complete! {global_chunk_index} chunks.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ingest_policy.py <path_to_pdf>")
    else:
        ingest_pdf(sys.argv[1])

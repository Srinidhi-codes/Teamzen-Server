"""
Service for processing policy PDF files and generating embeddings
"""
import os
import tempfile
import requests
from PyPDF2 import PdfReader
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from django.conf import settings

from ai_engine.models import PolicyDocument, PolicyFile


class PolicyProcessingService:
    """Handles PDF processing and embedding generation"""
    
    def __init__(self):
        # Prefer directly getting from environment if available
        api_key = os.getenv('OPENAI_API_KEY') or getattr(settings, 'OPENAI_API_KEY', None)
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment or settings")
            
        self.embeddings_model = OpenAIEmbeddings(openai_api_key=api_key)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100,
            separators=["\n\n", "\n", " ", ""]
        )
        
        # Initialize Cloudinary SDK
        import cloudinary
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_STORAGE['CLOUD_NAME'],
            api_key=settings.CLOUDINARY_STORAGE['API_KEY'],
            api_secret=settings.CLOUDINARY_STORAGE['API_SECRET'],
            secure=True
        )

    def process_policy_file(self, policy_file: PolicyFile):
        """
        Download PDF from Cloudinary and process it.
        """
        tmp_path = None
        try:
            import requests
            from cloudinary import utils
            
            # 1. Prepare identifiers
            raw_url = policy_file.file.url
            public_id = policy_file.file.public_id
            
            # Ensure extension
            public_id_with_ext = public_id
            if '.' not in public_id_with_ext and '.' in raw_url:
                ext = raw_url.split('.')[-1].split('?')[0]
                public_id_with_ext = f"{public_id}.{ext}"
            
            # 2. Extract version
            version = None
            if '/v' in raw_url:
                version = raw_url.split('/v')[-1].split('/')[0]

            # 3. Strategy Loop to get content
            strategies = [
                {"resource_type": "raw", "type": "authenticated", "public_id": public_id_with_ext},
                {"resource_type": "raw", "type": "upload", "public_id": public_id_with_ext, "version": version},
                {"url": raw_url}
            ]
            
            response = None
            for strategy in strategies:
                try:
                    target_url = strategy.get("url") or utils.cloudinary_url(
                        strategy["public_id"],
                        resource_type=strategy["resource_type"],
                        type=strategy["type"],
                        version=strategy.get("version"),
                        sign_url=True,
                        secure=True
                    )[0]
                    res = requests.get(target_url, timeout=10)
                    if res.status_code == 200:
                        response = res
                        break
                except Exception: continue
            
            if not response:
                raise ValueError(f"Could not download file from Cloudinary for processing (401/404).")
            
            # 4. Use common processing logic
            return self.process_file_content(policy_file, response.content, public_id_with_ext)
            
        except Exception as e:
            print(f"❌ Error processing policy file {policy_file.id}: {str(e)}")
            policy_file.is_processed = False
            policy_file.processing_error = str(e)
            policy_file.save()
            raise

    def process_file_content(self, policy_file: PolicyFile, content: bytes, source_name: str):
        """
        Common logic to process PDF content (bytes)
        """
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                tmp_file.write(content)
                tmp_path = tmp_file.name
            
            text = self._extract_text_from_pdf(tmp_path)
            if not text.strip():
                raise ValueError("No text extracted from PDF.")
            
            chunks = self.text_splitter.split_text(text)
            PolicyDocument.objects.filter(policy_file=policy_file).delete()
            
            for i, chunk in enumerate(chunks):
                embedding = self.embeddings_model.embed_query(chunk)
                PolicyDocument.objects.create(
                    policy_file=policy_file,
                    title=policy_file.title,
                    content=chunk,
                    embedding=embedding,
                    metadata={
                        "chunk_index": i,
                        "source": source_name,
                        "organization_id": policy_file.organization.id,
                    }
                )
            
            policy_file.is_processed = True
            policy_file.is_active = True
            policy_file.processing_error = None
            policy_file.save()
            return len(chunks)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    def delete_policy_file(self, policy_file: PolicyFile):
        """
        Delete PDF from Cloudinary
        """
        try:
            import cloudinary.uploader
            public_id = policy_file.file.public_id
            print(f"🗑️ Deleting from Cloudinary: {public_id}")
            cloudinary.uploader.destroy(public_id, resource_type="raw")
            return True
        except Exception as e:
            print(f"❌ Error deleting from Cloudinary: {str(e)}")
            return False

    def _extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF file"""
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            content = page.extract_text()
            if content:
                text += content + "\n"
        return text
    
    def reprocess_all_active_policies(self, organization_id=None, include_inactive=False):
        """
        Reprocess policy files
        
        Args:
            organization_id: Optional organization ID to filter by
            include_inactive: Whether to include files marked as inactive
        """
        queryset = PolicyFile.objects.all()
        if not include_inactive:
            queryset = queryset.filter(is_active=True)
            
        if organization_id:
            queryset = queryset.filter(organization_id=organization_id)
        
        results = []
        for policy_file in queryset:
            try:
                chunks_count = self.process_policy_file(policy_file)
                results.append({
                    'policy_file_id': policy_file.id,
                    'title': policy_file.title,
                    'status': 'success',
                    'chunks_count': chunks_count
                })
            except Exception as e:
                results.append({
                    'policy_file_id': policy_file.id,
                    'title': policy_file.title,
                    'status': 'error',
                    'error': str(e)
                })
        
        return results

from django.db import models
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from pgvector.django import VectorField
from cloudinary.models import CloudinaryField
from organizations.models import Organization

class PolicyFile(models.Model):
    """Stores uploaded policy PDF files"""
    organization = models.ForeignKey(
        Organization, 
        on_delete=models.CASCADE, 
        related_name='policy_files'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    file = CloudinaryField('policy_pdfs', resource_type='raw')
    file_size = models.IntegerField(null=True, blank=True)  # in bytes
    uploaded_by = models.ForeignKey(
        'users.CustomUser', 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='uploaded_policies'
    )
    is_active = models.BooleanField(default=True)
    is_processed = models.BooleanField(default=False)
    processing_error = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Policy File'
        verbose_name_plural = 'Policy Files'
    
    def __str__(self):
        return f"{self.title} - {self.organization.name}"

class PolicyDocument(models.Model):
    """Stores text chunks with embeddings from policy files"""
    policy_file = models.ForeignKey(
        PolicyFile,
        on_delete=models.CASCADE,
        related_name='document_chunks',
        null=True,
        blank=True
    )
    title = models.CharField(max_length=255)
    content = models.TextField()
    metadata = models.JSONField(default=dict)
    embedding = VectorField(dimensions=1536)  # Default for OpenAI ada-002 / text-embedding-3-small
    page_number = models.PositiveIntegerField(null=True, blank=True)
    search_vector = SearchVectorField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            GinIndex(fields=['search_vector']),
        ]

    def __str__(self):
        return self.title

class AIConfiguration(models.Model):
    """Stores AI Model settings per organization"""
    MODEL_CHOICES = [
        ('gpt-4o', 'GPT-4o (OpenAI Premium)'),
        ('gpt-4o-mini', 'GPT-4o Mini (OpenAI Fast)'),
        ('gemini-1.5-flash', 'Gemini 1.5 Flash (Google Free/Fast)'),
        ('gemini-1.5-pro', 'Gemini 1.5 Pro (Google Premium)'),
        ('llama-3.3-70b-versatile', 'Llama 3.3 70B (Groq Smart)'),
        ('llama-3.1-8b-instant', 'Llama 3.1 8B (Groq Free/Fast)'),
        ('mixtral-8x7b-32768', 'Mixtral 8x7B (Groq Fast)'),
    ]
    
    organization = models.OneToOneField(
        Organization, 
        on_delete=models.CASCADE, 
        related_name='ai_config'
    )
    model_name = models.CharField(
        max_length=50, 
        choices=MODEL_CHOICES, 
        default='gpt-4o'
    )
    temperature = models.FloatField(default=0.7)
    max_tokens = models.IntegerField(default=1024)
    system_prompt_override = models.TextField(
        blank=True, 
        null=True, 
        help_text="Custom instructions for the AI"
    )
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"AI Config for {self.organization.name} ({self.model_name})"

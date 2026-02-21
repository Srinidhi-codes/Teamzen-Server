from django.db import models
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
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return self.title

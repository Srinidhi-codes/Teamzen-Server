"""
Django Admin configuration for AI Engine
"""
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe

from ai_engine.models import PolicyFile, PolicyDocument
from ai_engine.services import PolicyProcessingService


@admin.register(PolicyFile)
class PolicyFileAdmin(admin.ModelAdmin):
    list_display = [
        'title', 
        'organization', 
        'uploaded_by', 
        'file_size_display',
        'status_badge',
        'chunk_count',
        'created_at',
        'actions_column'
    ]
    list_filter = ['is_active', 'is_processed', 'organization', 'created_at']
    search_fields = ['title', 'description', 'organization__name']
    readonly_fields = [
        'is_processed', 
        'processing_error', 
        'file_size', 
        'created_at', 
        'updated_at',
        'file_preview'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('organization', 'title', 'description', 'uploaded_by')
        }),
        ('File', {
            'fields': ('file', 'file_preview', 'file_size')
        }),
        ('Status', {
            'fields': ('is_active', 'is_processed', 'processing_error')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        """Set uploaded_by to current user if not set"""
        if not obj.uploaded_by:
            obj.uploaded_by = request.user
        
        # Set file size if file is present
        if obj.file and hasattr(obj.file, 'bytes'):
            obj.file_size = obj.file.bytes
        
        super().save_model(request, obj, form, change)
    
    def file_size_display(self, obj):
        """Display file size in human-readable format"""
        if not obj.file_size:
            return '-'
        
        size = obj.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    file_size_display.short_description = 'File Size'
    
    def status_badge(self, obj):
        """Display processing status as a colored badge"""
        if obj.is_processed:
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 3px 10px; border-radius: 3px;">✓ Processed</span>'
            )
        elif obj.processing_error:
            return format_html(
                '<span style="background-color: #dc3545; color: white; padding: 3px 10px; border-radius: 3px;">✗ Error</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #ffc107; color: black; padding: 3px 10px; border-radius: 3px;">⏳ Pending</span>'
            )
    status_badge.short_description = 'Status'
    
    def chunk_count(self, obj):
        """Display number of document chunks"""
        count = obj.document_chunks.count()
        if count > 0:
            url = reverse('admin:ai_engine_policydocument_changelist') + f'?policy_file__id__exact={obj.id}'
            return format_html('<a href="{}">{} chunks</a>', url, count)
        return '0 chunks'
    chunk_count.short_description = 'Chunks'
    
    def file_preview(self, obj):
        """Display file download link"""
        if obj.file:
            return format_html(
                '<a href="{}" target="_blank" class="button">📄 Download PDF</a>',
                obj.file.url
            )
        return '-'
    file_preview.short_description = 'File Preview'
    
    def actions_column(self, obj):
        """Display action buttons"""
        if obj.is_processed:
            return format_html(
                '<a class="button" href="#" onclick="return confirm(\'Reprocess this file?\') && reprocessPolicy({});">🔄 Reprocess</a>',
                obj.id
            )
        return '-'
    actions_column.short_description = 'Actions'
    
    actions = ['reprocess_selected_policies', 'mark_as_active', 'mark_as_inactive']
    
    def reprocess_selected_policies(self, request, queryset):
        """Admin action to reprocess selected policies"""
        service = PolicyProcessingService()
        success_count = 0
        error_count = 0
        
        for policy_file in queryset:
            try:
                service.process_policy_file(policy_file)
                success_count += 1
            except Exception as e:
                error_count += 1
                self.message_user(
                    request,
                    f"Error processing {policy_file.title}: {str(e)}",
                    level='ERROR'
                )
        
        if success_count > 0:
            self.message_user(
                request,
                f"Successfully reprocessed {success_count} policy file(s).",
                level='SUCCESS'
            )
        if error_count > 0:
            self.message_user(
                request,
                f"Failed to process {error_count} policy file(s).",
                level='WARNING'
            )
    reprocess_selected_policies.short_description = "🔄 Reprocess selected policies"
    
    def mark_as_active(self, request, queryset):
        """Mark selected policies as active"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} policy file(s) marked as active.")
    mark_as_active.short_description = "✓ Mark as active"
    
    def mark_as_inactive(self, request, queryset):
        """Mark selected policies as inactive"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} policy file(s) marked as inactive.")
    mark_as_inactive.short_description = "✗ Mark as inactive"


@admin.register(PolicyDocument)
class PolicyDocumentAdmin(admin.ModelAdmin):
    list_display = [
        'title',
        'policy_file_link',
        'chunk_preview',
        'created_at'
    ]
    list_filter = ['created_at', 'policy_file__organization']
    search_fields = ['title', 'content', 'policy_file__title']
    readonly_fields = ['title', 'content', 'embedding', 'metadata', 'created_at', 'policy_file']
    
    fieldsets = (
        ('Document Information', {
            'fields': ('policy_file', 'title', 'content')
        }),
        ('Embedding Data', {
            'fields': ('embedding', 'metadata'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
        }),
    )
    
    def has_add_permission(self, request):
        """Disable manual creation - chunks are auto-generated"""
        return False
    
    def policy_file_link(self, obj):
        """Link to parent policy file"""
        if obj.policy_file:
            url = reverse('admin:ai_engine_policyfile_change', args=[obj.policy_file.id])
            return format_html('<a href="{}">{}</a>', url, obj.policy_file.title)
        return '-'
    policy_file_link.short_description = 'Policy File'
    
    def chunk_preview(self, obj):
        """Show preview of content"""
        preview = obj.content[:100] + '...' if len(obj.content) > 100 else obj.content
        return preview
    chunk_preview.short_description = 'Content Preview'

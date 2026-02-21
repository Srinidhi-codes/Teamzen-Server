from rest_framework import serializers
from .models import PolicyFile

class PolicyFileSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.StringRelatedField(read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    file_url = serializers.SerializerMethodField()
    
    def get_file_url(self, obj):
        if not obj.file:
            return None
        try:
            import cloudinary.utils
            raw_url = obj.file.url
            public_id = obj.file.public_id
            
            # Extension handling
            if hasattr(obj.file, 'url') and '.' in raw_url:
                ext = raw_url.split('.')[-1].split('?')[0]
                if not public_id.endswith(f'.{ext}'):
                    public_id = f"{public_id}.{ext}"
            
            # Version handling
            version = None
            if '/v' in raw_url:
                version = raw_url.split('/v')[-1].split('/')[0]
            
            return cloudinary.utils.cloudinary_url(
                public_id,
                resource_type='raw',
                type='upload',
                version=version,
                sign_url=True,
                secure=True
            )[0]
        except Exception:
            return obj.file.url if hasattr(obj.file, 'url') else str(obj.file)
            
    class Meta:
        model = PolicyFile
        fields = [
            'id', 'title', 'description', 'file', 'file_url', 
            'file_size', 'organization', 'organization_name',
            'uploaded_by', 'is_active', 'is_processed', 
            'processing_error', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'is_processed', 'processing_error', 'created_at', 
            'updated_at', 'uploaded_by', 'file_size', 'organization'
        ]

    def create(self, validated_data):
        # Automatically set file size and uploaded_by user if available in context
        request = self.context.get('request')
        if request and request.user:
            validated_data['uploaded_by'] = request.user
            
        file_obj = validated_data.get('file')
        if file_obj:
            validated_data['file_size'] = file_obj.size
            
        return super().create(validated_data)

from django.contrib import admin
from .models import Post, PostLike, Comment, CommentLike

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('id', 'author', 'created_at', 'likes_count', 'comments_count')
    list_filter = ('created_at',)
    search_fields = ('content', 'author__email')

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'post', 'author', 'created_at', 'likes_count')
    list_filter = ('created_at',)
    search_fields = ('content', 'author__email')

admin.site.register(PostLike)
admin.site.register(CommentLike)

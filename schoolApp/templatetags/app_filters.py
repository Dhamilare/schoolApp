from django import template
import base64
import os
from django.conf import settings

register = template.Library()

@register.filter
def base64_encode(file_path):
    if not file_path:
        return ''
    
    full_path = os.path.join(settings.MEDIA_ROOT, file_path) if not os.path.isabs(file_path) else file_path

    if not os.path.exists(full_path):
        print(f"DEBUG: File not found for base64 encoding: {full_path}")
        return ''

    try:
        with open(full_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            # Determine MIME type based on file extension
            _, file_extension = os.path.splitext(full_path)
            if file_extension.lower() == '.png':
                mime_type = 'image/png'
            elif file_extension.lower() == '.jpg' or file_extension.lower() == '.jpeg':
                mime_type = 'image/jpeg'
            elif file_extension.lower() == '.gif':
                mime_type = 'image/gif'
            elif file_extension.lower() == '.svg':
                mime_type = 'image/svg+xml'
            else:
                mime_type = 'application/octet-stream' # Fallback for unknown types

            return f"data:{mime_type};base64,{encoded_string}"
    except Exception as e:
        print(f"Error encoding file to base64: {full_path} - {e}")
        return ''


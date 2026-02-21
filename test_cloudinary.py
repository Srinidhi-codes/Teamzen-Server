import os
import django
import requests
import cloudinary
import cloudinary.utils
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

cloudinary.config(
    cloud_name=settings.CLOUDINARY_STORAGE['CLOUD_NAME'],
    api_key=settings.CLOUDINARY_STORAGE['API_KEY'],
    api_secret=settings.CLOUDINARY_STORAGE['API_SECRET'],
    secure=True
)

from ai_engine.models import PolicyFile

def test_single_strategy(public_id, rt, tp, version=None):
    url = cloudinary.utils.cloudinary_url(
        public_id,
        resource_type=rt,
        type=tp,
        version=version,
        sign_url=True,
        secure=True
    )[0]
    res = requests.get(url, timeout=5)
    print(f"[{tp}/{rt}] PID={public_id} VER={version} -> Status: {res.status_code}")
    if res.status_code == 200:
        print(f"🏆 SUCCESS URL: {url}")
        return True
    return False

if __name__ == "__main__":
    pf = PolicyFile.objects.get(id=4)
    raw_url = pf.file.url
    public_id = pf.file.public_id
    version = raw_url.split('/v')[-1].split('/')[0] if '/v' in raw_url else None
    
    print(f"Testing for ID 4. PublicID: {public_id}, Version: {version}")
    
    # Common combinations
    test_single_strategy(f"{public_id}.pdf", "raw", "upload", version)
    test_single_strategy(f"{public_id}.pdf", "raw", "upload")
    test_single_strategy(f"{public_id}.pdf", "raw", "authenticated")
    test_single_strategy(public_id, "image", "upload", version)
    test_single_strategy(public_id, "image", "authenticated")
    
    # Try public URL directly
    res = requests.get(raw_url)
    print(f"[DIRECT] URL={raw_url} -> Status: {res.status_code}")

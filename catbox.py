"""
Catbox.moe uploader
Uploads image bytes and returns the public URL.
"""

import httpx
import logging

log = logging.getLogger(__name__)

CATBOX_API = "https://catbox.moe/user/api.php"


async def upload_to_catbox(file_bytes: bytes, filename: str = "image.jpg") -> str | None:
    """
    Upload image bytes to catbox.moe anonymously.
    Returns public URL like: https://files.catbox.moe/xxxxxx.jpg
    """
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                CATBOX_API,
                data={"reqtype": "fileupload"},
                files={"fileToUpload": (filename, file_bytes, "image/jpeg")},
            )
            response.raise_for_status()
            url = response.text.strip()
            if url.startswith("https://"):
                return url
            else:
                log.error(f"Catbox returned unexpected response: {url}")
                return None
    except Exception as e:
        log.error(f"Catbox upload failed: {e}")
        return None

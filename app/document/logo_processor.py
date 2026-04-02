import io

import requests
from PIL import Image

from app.config import settings


def download_and_process(output_path: str) -> str:
    resp = requests.get(settings.OPIKA_LOGO_URL, timeout=15)
    resp.raise_for_status()
    image = Image.open(io.BytesIO(resp.content)).convert("RGBA")

    new_data = []
    for r, g, b, a in image.getdata():
        if r < 30 and g < 30 and b < 30:
            new_data.append((r, g, b, 0))
        else:
            new_data.append((r, g, b, a))
    image.putdata(new_data)
    image.save(output_path, "PNG")
    return output_path

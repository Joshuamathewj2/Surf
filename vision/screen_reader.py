import os
import pytesseract
from PIL import ImageGrab

if os.name == 'nt' and os.path.exists(r'C:\Program Files\Tesseract-OCR\tesseract.exe'):
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def read_screen_text() -> str:
    """Capture full screen and return all visible text via OCR."""
    try:
        img = ImageGrab.grab()
        return pytesseract.image_to_string(img).strip()
    except Exception as e:
        print(f"  [Error] OCR failed: {e}")
        return ""

def find_text_on_screen(target: str):
    """Return (x, y) center coordinates of target text on screen, or None."""
    try:
        img = ImageGrab.grab()
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        
        for i, word in enumerate(data['text']):
            if target.lower() in word.lower() and int(data['conf'][i]) > 60:
                x = data['left'][i] + data['width'][i] // 2
                y = data['top'][i] + data['height'][i] // 2
                return (x, y)
    except Exception as e:
        print(f"  [Error] OCR failed: {e}")
    return None

import os
import cv2
import numpy as np
import pytesseract
from PIL import Image

# For Windows, set the default tesseract path if it exists to avoid PATH errors
if os.name == 'nt' and os.path.exists(r'C:\Program Files\Tesseract-OCR\tesseract.exe'):
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def find_text_on_screen(image: Image.Image, target_text: str):
    """
    Uses Tesseract OCR to find the target_text on the screen image.
    Returns the (x, y) center position of the text if found, else None.
    """
    import logging
    
    # Convert PIL Image to OpenCV format
    img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    img_gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    
    # Optional image preprocessing for better OCR (thresholding)
    # img_gray = cv2.threshold(img_gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    
    # Process text using pytesseract with bounding boxes
    try:
        data = pytesseract.image_to_data(img_gray, output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractNotFoundError:
        print("[Error] Tesseract OCR is not installed or not in PATH.")
        return None

    target = target_text.lower().strip()
    
    # First pass: try exact word matching
    for i in range(len(data['text'])):
        text = data['text'][i].strip().lower()
        if not text:
            continue
            
        if target == text:
            x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
            if w > 0 and h > 0:
                center_x = x + (w // 2)
                center_y = y + (h // 2)
                print(f"  [Vision] Found exact match '{target}' at ({center_x}, {center_y})")
                return (center_x, center_y)

    # Second pass: try partial match
    for i in range(len(data['text'])):
        text = data['text'][i].strip().lower()
        if not text:
            continue
            
        # If target word is inside a longer string
        if target in text or text in target:
            x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
            if w > 0 and h > 0:
                center_x = x + (w // 2)
                center_y = y + (h // 2)
                print(f"  [Vision] Found partial match '{target}' inside '{text}' at ({center_x}, {center_y})")
                return (center_x, center_y)
                
    print(f"  [Vision] Could not find '{target}' on screen.")
    return None

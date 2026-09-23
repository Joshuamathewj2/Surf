"""
vision/model.py
Integration with Moondream2 (or similar 1.8B model) to understand screenshots.
"""
def analyze_screen(prompt: str, image_path: str = None) -> str:
    """
    Passes a screenshot and a prompt to the vision LLM.
    Returns the description or coordinates.
    """
    print(f"[Vision Model] Analyzing screen for: '{prompt}'")
    # Placeholder: requires transformers & model weights
    return "Not implemented natively yet."

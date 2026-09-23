"""
agent/app_index.py
Scans Desktop and Start Menu to build a fuzzy lookup dict of installed apps and projects.
"""
import os
import glob
from rapidfuzz import process, fuzz

DEFAULT_PATHS = [
    os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
    os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
    os.path.expandvars(r"%USERPROFILE%\Desktop"),
    os.path.expandvars(r"C:\Users\Public\Desktop"),
]

# We can also add common project folders here if needed
EXTRA_PATHS = [
    r"c:\sprint" # known from previous user contexts
]

app_dict = {}

def build_index():
    global app_dict
    app_dict.clear()
    
    # Scan standard shortcut paths
    for path in DEFAULT_PATHS:
        if os.path.exists(path):
            for root, dirs, files in os.walk(path):
                for f in files:
                    if f.endswith('.lnk') or f.endswith('.url'):
                        name = os.path.splitext(f)[0].lower()
                        app_dict[name] = os.path.join(root, f)
    
    # Scan project paths just 1 level deep for executables or web shortcuts
    for path in EXTRA_PATHS:
        if os.path.exists(path):
            project_dirs = [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))]
            for pd in project_dirs:
                # We can launch VS code on this folder or a start script
                app_dict[pd.lower()] = os.path.join(path, pd)
    
    print(f"[AppIndex] Built index with {len(app_dict)} items.")

def find_app(query: str):
    if not app_dict:
        build_index()
    
    query = query.lower()
    items = list(app_dict.keys())
    
    if not items:
        return None
        
    match = process.extractOne(query, items, scorer=fuzz.partial_ratio)
    if match and match[1] > 70:  # Score threshold
        matched_name = match[0]
        return app_dict[matched_name]
    
    return None

# Build on first import
build_index()

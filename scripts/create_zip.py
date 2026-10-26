import os
import shutil
import zipfile

WORKSPACE_DIR = os.path.abspath(".")
ZIP_NAME = "cascade-sentinel.zip"
WORKSPACE_ZIP = os.path.join(WORKSPACE_DIR, ZIP_NAME)
ARTIFACT_DIR = r"C:\Users\LENOVO\.gemini\antigravity\brain\a55cf323-286d-4e97-a4a3-1126fd698761"
ARTIFACT_ZIP = os.path.join(ARTIFACT_DIR, ZIP_NAME)

EXCLUDE_DIRS = {
    ".git", ".pytest_cache", "__pycache__", ".venv", "venv", "node_modules", ".gemini"
}
EXCLUDE_EXTS = {
    ".pyc", ".pyo", ".pyd"
}
EXCLUDE_FILES = {
    ZIP_NAME, ".DS_Store"
}

print(f"Creating zip archive from {WORKSPACE_DIR}...")

# Remove existing zip if any
if os.path.exists(WORKSPACE_ZIP):
    try:
        os.remove(WORKSPACE_ZIP)
    except Exception as e:
        print(f"Warning: could not remove existing {WORKSPACE_ZIP}: {e}")

file_count = 0
total_size = 0

with zipfile.ZipFile(WORKSPACE_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    for root, dirs, files in os.walk(WORKSPACE_DIR):
        # Filter out exclude dirs in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]

        for file in files:
            if file in EXCLUDE_FILES:
                continue
            _, ext = os.path.splitext(file)
            if ext in EXCLUDE_EXTS:
                continue

            full_path = os.path.join(root, file)
            # Relative path inside the zip archive with prefix 'cascade-sentinel/' for clean extraction
            rel_path = os.path.relpath(full_path, WORKSPACE_DIR)
            arc_name = os.path.join("cascade-sentinel", rel_path).replace("\\", "/")

            zf.write(full_path, arc_name)
            file_count += 1
            total_size += os.path.getsize(full_path)

zip_size_mb = os.path.getsize(WORKSPACE_ZIP) / (1024 * 1024)
print(f"Successfully packaged {file_count} files ({total_size / (1024*1024):.2f} MB uncompressed).")
print(f"Zip archive created: {WORKSPACE_ZIP} ({zip_size_mb:.2f} MB)")

# Copy to artifact directory for download access
if os.path.exists(ARTIFACT_DIR):
    shutil.copy2(WORKSPACE_ZIP, ARTIFACT_ZIP)
    print(f"Copied zip to artifact directory: {ARTIFACT_ZIP}")
else:
    print(f"Artifact dir does not exist: {ARTIFACT_DIR}")

print("Verification complete.")

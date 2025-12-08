import subprocess
import os
import sys

# Threshold in bytes (100 MB)
THRESHOLD = 100 * 1024 * 1024
DEBUG = False  # Set to True for verbose output

def debug_print(message):
    if DEBUG:
        print(f"🐛 DEBUG: {message}")

def find_large_blobs():
    print("🔍 Scanning repository for large blobs (>100MB)...")
    debug_print("Running git rev-list --objects --all")
    
    rev_list = subprocess.Popen(
        ["git", "rev-list", "--objects", "--all"],
        stdout=subprocess.PIPE
    )
    cat_file = subprocess.Popen(
        ["git", "cat-file", "--batch-check=%(objecttype) %(objectname) %(objectsize) %(rest)"],
        stdin=rev_list.stdout,
        stdout=subprocess.PIPE
    )
    rev_list.stdout.close()
    output = cat_file.communicate()[0].decode("utf-8")

    debug_print(f"Found {len(output.splitlines())} total objects")

    large_blobs = []
    for line in output.splitlines():
        if not line.startswith("blob"):
            continue
        parts = line.split(maxsplit=4)
        if len(parts) < 4:
            continue
        _, obj_hash, size_str, *rest = parts
        try:
            size = int(size_str)
        except ValueError:
            debug_print(f"Skipping line with invalid size: {line}")
            continue
            
        if size > THRESHOLD:
            path = rest[0] if rest else "(unknown)"
            large_blobs.append((obj_hash, size, path))
            debug_print(f"Found large blob: {path} ({size} bytes)")

    return large_blobs

def check_git_filter_repo():
    """Check if git filter-repo is available"""
    try:
        result = subprocess.run(["git", "filter-repo", "--version"], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            debug_print(f"git filter-repo version: {result.stdout.strip()}")
            return True
        else:
            return False
    except FileNotFoundError:
        return False

def remove_large_files(paths):
    print(f"\n🧹 Removing {len(paths)} large files from history using git filter-repo...")
    
    # Filter out paths that are "(unknown)" as they can't be processed
    valid_paths = [path for path in paths if path != "(unknown)"]
    
    if not valid_paths:
        print("❌ No valid file paths found to remove.")
        return False
    
    # Build the git filter-repo command with all paths at once
    cmd = ["git", "filter-repo", "--force"]
    
    # Add each path with --path and --invert-paths
    for path in valid_paths:
        cmd.extend(["--path", path])
    
    cmd.append("--invert-paths")
    
    print(f"  Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("✅ All specified large files have been removed from history.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running git filter-repo: {e.stderr}")
        print(f"   Command failed with return code: {e.returncode}")
        return False

def main():
    if not os.path.exists(".git"):
        print("❌ This script must be run from the root of a Git repository.")
        sys.exit(1)

    # Check for git filter-repo availability
    if not check_git_filter_repo():
        print("❌ git filter-repo is not available. Please install it and try again.")
        sys.exit(1)

    large_blobs = find_large_blobs()
    if not large_blobs:
        print("✅ No files larger than 100MB found in the repository.")
        return

    print("\n📦 Large blobs found:")
    for i, (obj_hash, size, path) in enumerate(large_blobs, 1):
        print(f"  [{i}] {obj_hash} - {size / (1024 * 1024):.2f} MB - {path}")

    paths_to_remove = [path for _, _, path in large_blobs]
    success = remove_large_files(paths_to_remove)
    
    if success:
        print("\n🧼 You may now run: git gc --prune=now --aggressive")
        print("🚀 Cleanup complete.")
    else:
        print("\n❌ Failed to remove large files. Check the error messages above.")

if __name__ == "__main__":
    main()

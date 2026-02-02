import sys
import os
import shutil
import time
import subprocess

def main():
    # Expecting arguments:
    # 1: Source Directory (Temp folder with new files)
    # 2: Destination Directory (Install folder)
    # 3: Main Executable Name (e.g., PmGen.exe)
    
    if len(sys.argv) < 4:
        # If run manually, just exit
        sys.exit(0)

    src_dir = sys.argv[1]
    dst_dir = sys.argv[2]
    exe_name = sys.argv[3]
    
    target_exe = os.path.join(dst_dir, exe_name)

    # 1. Wait for the main application to close
    # We try to rename the executable to itself. If it's locked, the app is still open.
    for _ in range(20): # Try for 10 seconds (20 * 0.5)
        try:
            if os.path.exists(target_exe):
                os.rename(target_exe, target_exe)
                break # Success, file is not locked
        except OSError:
            time.sleep(0.5)

    # 2. Delete master database file.
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        db_to_delete = os.path.join(local_appdata, "PmGen", "catalog_manager.db")
        if os.path.exists(db_to_delete):
            try:
                os.remove(db_to_delete)
            except OSError:
                pass

    # 3. Move Files
    # We use copytree with dirs_exist_ok=True to merge/overwrite folders like _internal
    try:
        shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)
    except Exception:
        # If this fails, there's not much we can do silently. 
        # Ideally, log this or popup an error if you had a UI library linked.
        pass

    # 4. Clean up Source
    try:
        shutil.rmtree(src_dir)
        # We can also attempt to clean up the zip if passed as arg 4, 
        # but the main app usually deletes it before calling this.
    except Exception:
        pass

    # 5. Restart Main Application
    if os.path.exists(target_exe):
        subprocess.Popen([target_exe], cwd=dst_dir)

if __name__ == "__main__":
    main()
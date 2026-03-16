import sys
import os
import shutil
import time
import subprocess
import logging
import traceback

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
LOG_DIR = os.path.join(os.path.expanduser("~"), ".indybiz_pm")
LOG_FILE = os.path.join(LOG_DIR, "updater.log")
MAX_RETRIES = 60
RETRY_DELAY = 1.0


def resolve_payload_root(src_dir, target_exe_name):
    """
    Finds the directory inside src_dir that contains the target executable.
    This handles ZIPs that may have an extra top-level folder.
    """
    direct_exe = os.path.join(src_dir, target_exe_name)
    if os.path.exists(direct_exe):
        return src_dir

    for root, _, files in os.walk(src_dir):
        if target_exe_name in files:
            return root

    return src_dir


def replace_internal_folder(src_dir, dst_dir):
    """
    Replaces destination _internal folder with source _internal folder.
    This prevents stale runtime files from previous builds.
    """
    src_internal = os.path.join(src_dir, "_internal")
    dst_internal = os.path.join(dst_dir, "_internal")

    if not os.path.exists(src_internal):
        logging.warning("Source update does not contain _internal; skipping _internal replacement.")
        return 0

    if os.path.exists(dst_internal):
        logging.info("Removing existing destination _internal folder...")
        shutil.rmtree(dst_internal)

    logging.info("Copying new _internal folder...")
    shutil.copytree(src_internal, dst_internal)

    files_copied = 0
    for _, _, files in os.walk(src_internal):
        files_copied += len(files)
    return files_copied

def setup_logging():
    """Sets up a standalone logger for the updater process."""
    if not os.path.exists(LOG_DIR):
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
        except Exception:
            return # Can't log if we can't create dir

    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    # Also print to stdout for debugging if run from console
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG)
    logging.getLogger('').addHandler(console)

def install_update(src_dir, dst_dir):
    """
    Iterates over the source directory and copies files to destination.
    Returns (success: bool, message: str)
    """
    # 1. Verify Source
    if not os.path.exists(src_dir):
        return False, f"Source directory does not exist: {src_dir}"

    logging.info(f"Starting copy from '{src_dir}' to '{dst_dir}'")

    files_copied = 0
    
    try:
        files_copied += replace_internal_folder(src_dir, dst_dir)

        for root, dirs, files in os.walk(src_dir):
            if root == src_dir and "_internal" in dirs:
                dirs.remove("_internal")

            rel_path = os.path.relpath(root, src_dir)
            target_path = os.path.join(dst_dir, rel_path)

            if not os.path.exists(target_path):
                os.makedirs(target_path, exist_ok=True)

            for file in files:
                src_file = os.path.join(root, file)
                dst_file = os.path.join(target_path, file)

                # Allow updater.exe to be updated. The main app stages the running updater
                # to a temp location, so the installed updater.exe is safe to overwrite.
                try:
                    shutil.copy2(src_file, dst_file)
                except PermissionError:
                    if file.lower() == "updater.exe" and os.path.exists(dst_file):
                        try:
                            backup_path = dst_file + ".old"
                            if os.path.exists(backup_path):
                                os.remove(backup_path)
                            os.replace(dst_file, backup_path)
                            shutil.copy2(src_file, dst_file)
                        except Exception:
                            raise
                    else:
                        raise
                files_copied += 1
        
        return True, f"Successfully copied {files_copied} files."

    except Exception as e:
        return False, f"Copy failed: {str(e)}\n{traceback.format_exc()}"

def main():
    setup_logging()
    logging.info("="*60)
    logging.info(f"Updater Started. PID: {os.getpid()}")
    logging.info(f"Arguments: {sys.argv}")

    # Expected: [script_path, src_dir, dst_dir, exe_name]
    if len(sys.argv) < 4:
        logging.error("Not enough arguments provided. Exiting.")
        logging.error(f"Received: {sys.argv}")
        return

    src_dir = sys.argv[1]
    dst_dir = sys.argv[2]
    target_exe_name = sys.argv[3]
    src_dir = resolve_payload_root(src_dir, target_exe_name)

    logging.info(f"Resolved payload source directory: {src_dir}")

    target_exe_path = os.path.join(dst_dir, target_exe_name)

    success = False
    
    for i in range(MAX_RETRIES):
        logging.info(f"Attempt {i+1}/{MAX_RETRIES} to install update...")
        
        success, msg = install_update(src_dir, dst_dir)
        
        if success:
            logging.info("Update files copied successfully.")
            break
        else:
            logging.warning(f"Attempt failed: {msg}")
            logging.info(f"Waiting {RETRY_DELAY}s for files to unlock...")
            time.sleep(RETRY_DELAY)

    if not success:
        logging.critical("Timed out waiting for file locks. Update failed.")
        return

    logging.info("Cleaning up temp files...")
    try:
        shutil.rmtree(src_dir, ignore_errors=True)
    except Exception as e:
        logging.error(f"Failed to remove temp dir: {e}")

    logging.info(f"Relaunching application: {target_exe_path}")
    if os.path.exists(target_exe_path):
        try:
            subprocess.Popen([target_exe_path], cwd=dst_dir, close_fds=True)
            logging.info("Relaunch successful. Exiting updater.")
        except Exception as e:
            logging.error(f"Failed to relaunch app: {e}")
    else:
        logging.error(f"Target executable not found: {target_exe_path}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        if os.path.exists(LOG_DIR):
            with open(LOG_FILE, "a") as f:
                f.write(f"\nCRITICAL CRASH: {e}\n{traceback.format_exc()}\n")
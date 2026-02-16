import sys
import os
import shutil
import time
import subprocess
import logging
import traceback
from datetime import datetime

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
LOG_DIR = os.path.join(os.path.expanduser("~"), ".indybiz_pm")
LOG_FILE = os.path.join(LOG_DIR, "updater.log")
MAX_RETRIES = 60
RETRY_DELAY = 1.0

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
        for root, dirs, files in os.walk(src_dir):
            rel_path = os.path.relpath(root, src_dir)
            target_path = os.path.join(dst_dir, rel_path)

            if not os.path.exists(target_path):
                os.makedirs(target_path, exist_ok=True)

            for file in files:
                src_file = os.path.join(root, file)
                dst_file = os.path.join(target_path, file)

                if "updater.exe" in file.lower():
                    continue

                shutil.copy2(src_file, dst_file)
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
import sys
import os
import requests
import subprocess
import zipfile
import shutil
import tempfile
import time
from packaging import version
from PyQt6.QtCore import QObject, pyqtSignal

# --- CONFIGURATION ---
GITHUB_REPO = "c0pper22/PmGen"
ASSET_NAME = "PmGen.zip" 
CURRENT_VERSION = "2.5.9"
HEADERS = {'User-Agent': f"PmGen-Updater/{CURRENT_VERSION}"}

class UpdateWorker(QObject):
    """
    Runs in a background thread to check for updates, download, and extract.
    """
    check_finished = pyqtSignal(bool, str, str) 
    download_progress = pyqtSignal(int)
    extraction_progress = pyqtSignal(int)
    download_finished = pyqtSignal(str)
    extraction_finished = pyqtSignal(str, str) 
    error_occurred = pyqtSignal(str)

    def check_updates(self):
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            latest_tag = data['tag_name'].lstrip('v')
            
            if version.parse(latest_tag) > version.parse(CURRENT_VERSION):
                download_url = None
                for asset in data['assets']:
                    if asset['name'] == ASSET_NAME:
                        download_url = asset['browser_download_url']
                        break
                
                if download_url:
                    self.check_finished.emit(True, latest_tag, download_url)
                else:
                    self.error_occurred.emit(f"Update found ({latest_tag}), but asset is missing.")
            else:
                self.check_finished.emit(False, latest_tag, "")
                
        except Exception as e:
            self.error_occurred.emit(f"Update check failed: {str(e)}")

    def download_update(self, url):
        try:
            temp_dir = tempfile.gettempdir()
            zip_path = os.path.join(temp_dir, "pmgen_update.zip")
            
            # Use headers here too
            r = requests.get(url, headers=HEADERS, stream=True)
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            
            downloaded = 0
            with open(zip_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = int((downloaded / total_size) * 100)
                        self.download_progress.emit(pct)
            
            self.download_finished.emit(zip_path)
            
        except Exception as e:
            self.error_occurred.emit(f"Download failed: {str(e)}")

    def extract_update(self, zip_path):
        try:
            temp_extract_dir = os.path.join(tempfile.gettempdir(), "pmgen_new_files")
            
            if os.path.exists(temp_extract_dir):
                shutil.rmtree(temp_extract_dir, ignore_errors=True)
            os.makedirs(temp_extract_dir, exist_ok=True)

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                members = zip_ref.infolist()
                total_files = len(members)
                
                for i, member in enumerate(members):
                    zip_ref.extract(member, temp_extract_dir)
                    if total_files > 0:
                        pct = int(((i + 1) / total_files) * 100)
                        self.extraction_progress.emit(pct)

            self.extraction_finished.emit(zip_path, temp_extract_dir)

        except Exception as e:
            self.error_occurred.emit(f"Extraction failed: {str(e)}")


def perform_restart(zip_path, temp_extract_dir):
    """
    Updates the application using 'Rename & Replace' for ALL files,
    not just the executable. This bypasses 'File in Use' errors.
    """
    if not getattr(sys, 'frozen', False):
        print("Not running frozen. Skipping update.")
        return

    current_exe = sys.executable
    current_dir = os.path.dirname(current_exe)
    
    try:
        # 1. Iterate over the NEW files in the temp directory
        for item in os.listdir(temp_extract_dir):
            src_path = os.path.join(temp_extract_dir, item)
            dst_path = os.path.join(current_dir, item)
            
            if os.path.exists(dst_path):
                old_path = dst_path + f".old.{int(time.time())}"
                try:
                    os.rename(dst_path, old_path)
                except OSError:
                    # If we can't rename it, it's likely a permission issue or heavily locked.
                    print(f"Warning: Could not move locked file {dst_path}")
                    continue

            # Move the new file into place
            shutil.move(src_path, dst_path)

        # 2. Clean up the download
        try:
            os.remove(zip_path)
            os.rmdir(temp_extract_dir)
        except OSError:
            pass

        # 3. Restart the Application
        # DETACHED_PROCESS (0x00000008) or CREATE_NEW_CONSOLE (0x00000010)
        print("Restarting application...")
        
        # Determine flags based on OS (Windows specific flags)
        creation_flags = 0
        if sys.platform == 'win32':
            creation_flags = subprocess.CREATE_NEW_CONSOLE

        subprocess.Popen(
            [current_exe],
            cwd=current_dir,
            creationflags=creation_flags,
            close_fds=True # Important! Close file handles so the child doesn't inherit locks
        )
        
        # 4. Exit this process immediately
        sys.exit(0)

    except Exception as e:
        print(f"Update failed: {e}")
        # Note: We can't easily 'rollback' here because we renamed multiple files.
        # Ideally, your app should detect broken states on startup.
        raise e
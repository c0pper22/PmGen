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
CURRENT_VERSION = "2.7.1"
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
    Launches the separate 'updater.exe' to handle the file move
    and restarts the app.
    """
    if not getattr(sys, 'frozen', False):
        print("Not running frozen. Skipping update.")
        return

    current_exe = sys.executable
    current_dir = os.path.dirname(current_exe)
    exe_name = os.path.basename(current_exe)
    
    # The updater.exe is now bundled in the same folder
    updater_exe = os.path.join(current_dir, "updater.exe")

    if not os.path.exists(updater_exe):
        print("Error: updater.exe not found!")
        return

    # Delete the zip file now since we have extracted it
    try:
        os.remove(zip_path)
    except OSError:
        pass

    # Launch updater.exe detached
    # Args: 1. New Files Path, 2. Install Dir, 3. Exe Name
    # creationflags=0x00000008 (DETACHED_PROCESS) is useful on Windows to ensure 
    # the updater survives the parent death if running from console, 
    # but Popen default behavior usually works fine for GUI apps.
    subprocess.Popen([updater_exe, temp_extract_dir, current_dir, exe_name])
    
    # Exit immediately so the updater can grab the file locks
    sys.exit(0)
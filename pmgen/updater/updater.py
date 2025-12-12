import sys
import os
import requests
import subprocess
import zipfile
import shutil
import tempfile
from packaging import version
from PyQt6.QtCore import QObject, pyqtSignal

# --- CONFIGURATION ---
GITHUB_REPO = "c0pper22/PmGen"
ASSET_NAME = "PmGen.zip" 
CURRENT_VERSION = "2.3.3" 

class UpdateWorker(QObject):
    """
    Runs in a background thread to check for updates without freezing the GUI.
    """
    check_finished = pyqtSignal(bool, str, str) # (update_found, version_tag, download_url)
    download_progress = pyqtSignal(int)         # (percentage)
    download_finished = pyqtSignal(str)         # (path_to_zip_file)
    error_occurred = pyqtSignal(str)            # (error_message)

    def check_updates(self):
        """Checks GitHub for a newer version."""
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        try:
            response = requests.get(url, timeout=5)
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
                    self.error_occurred.emit(f"Update found ({latest_tag}), but {ASSET_NAME} is missing.")
            else:
                self.check_finished.emit(False, latest_tag, "")
                
        except Exception as e:
            self.error_occurred.emit(f"Update check failed: {str(e)}")

    def download_update(self, url):
        """Downloads the new zip file."""
        try:
            temp_dir = tempfile.gettempdir()
            zip_path = os.path.join(temp_dir, "pmgen_update.zip")
            
            r = requests.get(url, stream=True)
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

def perform_restart(zip_path):
    """
    1. Extracts the zip to a temp folder.
    2. Creates a .bat file to handle the file swap.
    3. Launches the .bat and kills the current app.
    """
    if not getattr(sys, 'frozen', False):
        print("Not running frozen (exe). Skipping self-update.")
        return

    current_app_dir = os.path.dirname(sys.executable)
    exe_name = os.path.basename(sys.executable)
    
    temp_extract_dir = os.path.join(tempfile.gettempdir(), "pmgen_new_files")
    
    if os.path.exists(temp_extract_dir):
        try:
            shutil.rmtree(temp_extract_dir)
        except OSError:
            pass
    os.makedirs(temp_extract_dir, exist_ok=True)

    try:
        print(f"Extracting {zip_path} to {temp_extract_dir}...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_extract_dir)

        bat_path = os.path.join(tempfile.gettempdir(), "pmgen_updater.bat")
        
        bat_content = f"""
@echo off
title Updating PmGen...
echo Waiting for application to close...
timeout /t 3 /nobreak > NUL

echo Copying new files...
xcopy "{temp_extract_dir}\\*" "{current_app_dir}\\" /E /H /Y /I

echo Cleaning up...
del "{zip_path}"
rmdir /s /q "{temp_extract_dir}"

echo Restarting application...
start "" "{os.path.join(current_app_dir, exe_name)}"

echo Done.
del "%~f0"
"""
        with open(bat_path, "w") as bat_file:
            bat_file.write(bat_content)

        # 4. Execute Batch and Exit
        print("Launching updater script and exiting...")
        subprocess.Popen([bat_path], shell=True)
        sys.exit()

    except Exception as e:
        print(f"Failed to prepare update: {e}")
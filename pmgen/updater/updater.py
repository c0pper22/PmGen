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
CURRENT_VERSION = "2.5.3" 
# Add a User-Agent so GitHub/EDRs know this isn't a generic bot script
HEADERS = {'User-Agent': 'PmGen-Updater/1.0'}

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
            # Always use headers!
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
    Updates the application using the 'Rename & Replace' strategy.
    This avoids using .bat files and cmd.exe, reducing AV false positives.
    """
    if not getattr(sys, 'frozen', False):
        print("Not running frozen. Skipping update.")
        return

    current_exe = sys.executable
    current_dir = os.path.dirname(current_exe)
    
    # Define the backup name (e.g., PmGen.exe.old)
    backup_exe = current_exe + ".old"
    
    try:
        # 1. Clean up any previous backup if it exists
        if os.path.exists(backup_exe):
            try:
                os.remove(backup_exe)
            except OSError:
                print("Could not remove old backup. Proceeding anyway.")

        # 2. Rename the CURRENT running executable
        # Windows allows renaming a running executable!
        os.rename(current_exe, backup_exe)

        # 3. Move the NEW files from temp to the application directory
        # We use shutil.copytree or a loop to copy everything over
        for item in os.listdir(temp_extract_dir):
            s = os.path.join(temp_extract_dir, item)
            d = os.path.join(current_dir, item)
            if os.path.isdir(s):
                # Copy tree, remove destination if it exists
                if os.path.exists(d):
                    shutil.rmtree(d)
                shutil.copytree(s, d)
            else:
                shutil.copy2(s, d)

        # 4. Clean up temp files
        try:
            os.remove(zip_path)
            shutil.rmtree(temp_extract_dir)
        except OSError:
            pass

        # 5. Restart the Application
        # We launch the NEW executable (which now has the original name)
        # We do NOT use shell=True
        print("Restarting application...")
        subprocess.Popen([current_exe])
        
        # 6. Exit this process
        sys.exit()

    except Exception as e:
        print(f"Update failed: {e}")
        # If we failed after renaming, try to restore the name so the app isn't broken
        if os.path.exists(backup_exe) and not os.path.exists(current_exe):
            try:
                os.rename(backup_exe, current_exe)
            except:
                pass
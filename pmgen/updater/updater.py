import sys
import logging
import subprocess
import zipfile
import shutil
import tempfile
import requests
from pathlib import Path
from typing import Optional, Tuple

from packaging import version
from PyQt6.QtCore import QObject, pyqtSignal

# --- CONFIGURATION ---
GITHUB_REPO = "c0pper22/PmGen"
ASSET_NAME = "PmGen.zip"
CURRENT_VERSION = "2.8.3"
USER_AGENT = f"PmGen-Updater/{CURRENT_VERSION}"
UPDATER_EXE_NAME = "updater.exe"

class UpdateWorker(QObject):
    """
    Handles update logic (check, download, extract) in a background thread
    to prevent freezing the PyQt UI.
    """
    # Signals
    check_finished = pyqtSignal(bool, str, str)
    download_progress = pyqtSignal(int)
    download_finished = pyqtSignal(str)
    extraction_progress = pyqtSignal(int)
    extraction_finished = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.headers = {'User-Agent': USER_AGENT}

    def check_updates(self) -> None:
        """Queries GitHub API to compare current version against the latest release."""
        logging.info("Checking for updates via GitHub API...")
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            latest_tag = data.get('tag_name', '').lstrip('v')
            
            if not latest_tag:
                raise ValueError("Could not retrieve tag name from GitHub.")

            if version.parse(latest_tag) > version.parse(CURRENT_VERSION):
                logging.info(f"Update found: {latest_tag}")
                
                download_url = next(
                    (asset['browser_download_url'] for asset in data.get('assets', []) if asset['name'] == ASSET_NAME),
                    None
                )

                if download_url:
                    self.check_finished.emit(True, latest_tag, download_url)
                else:
                    self.error_occurred.emit(f"Update {latest_tag} found, but asset '{ASSET_NAME}' is missing.")
            else:
                logging.info("System is up to date.")
                self.check_finished.emit(False, latest_tag, "")

        except requests.RequestException as e:
            logging.error(f"Network error during update check: {e}")
            self.error_occurred.emit(f"Network error: {str(e)}")
        except Exception as e:
            logging.exception("Unexpected error during update check.")
            self.error_occurred.emit(f"Error checking updates: {str(e)}")

    def download_update(self, url: str) -> None:
        """Downloads the update ZIP file to a temporary directory."""
        logging.info(f"Downloading update from: {url}")
        
        try:
            temp_dir = Path(tempfile.gettempdir())
            zip_path = temp_dir / "pmgen_update.zip"

            with requests.get(url, headers=self.headers, stream=True, timeout=30) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0

                with open(zip_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                pct = int((downloaded / total_size) * 100)
                                self.download_progress.emit(pct)

            logging.info("Download complete.")
            self.download_finished.emit(str(zip_path))

        except Exception as e:
            logging.error(f"Download failed: {e}")
            self.error_occurred.emit(f"Download failed: {str(e)}")

    def extract_update(self, zip_path_str: str) -> None:
        """Extracts the downloaded ZIP to a temporary folder."""
        zip_path = Path(zip_path_str)
        try:
            temp_extract_dir = Path(tempfile.gettempdir()) / "pmgen_new_files"

            if temp_extract_dir.exists():
                shutil.rmtree(temp_extract_dir, ignore_errors=True)
            temp_extract_dir.mkdir(parents=True, exist_ok=True)

            logging.info(f"Extracting to {temp_extract_dir}")
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                members = zip_ref.infolist()
                total_files = len(members)

                for i, member in enumerate(members):
                    zip_ref.extract(member, temp_extract_dir)
                    if total_files > 0:
                        pct = int(((i + 1) / total_files) * 100)
                        self.extraction_progress.emit(pct)

            self.extraction_finished.emit(str(zip_path), str(temp_extract_dir))

        except Exception as e:
            logging.error(f"Extraction failed: {e}")
            self.error_occurred.emit(f"Extraction failed: {str(e)}")


def perform_restart(zip_path_str: str, temp_extract_dir_str: str) -> None:
    """
    Terminates the current application and launches an external updater executable
    to move files from temp_extract_dir to the main directory.
    """
    if not getattr(sys, 'frozen', False):
        logging.warning("Application is not frozen. Skipping restart/update logic.")
        return

    current_exe = Path(sys.executable)
    current_dir = current_exe.parent
    exe_name = current_exe.name
    updater_exe = current_dir / UPDATER_EXE_NAME

    if not updater_exe.exists():
        logging.critical(f"Updater executable not found at: {updater_exe}")
        return

    zip_path = Path(zip_path_str)
    try:
        if zip_path.exists():
            zip_path.unlink()
    except OSError as e:
        logging.warning(f"Could not delete temp zip: {e}")

    logging.info("Launching external updater and exiting...")

    subprocess.Popen(
        [str(updater_exe), temp_extract_dir_str, str(current_dir), exe_name],
        cwd=str(current_dir)
    )
    
    sys.exit(0)
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from tkinter import Tk, filedialog, messagebox
from zipfile import ZipFile


APP_EXE_NAME = "PmGen.exe"
PAYLOAD_ZIP_NAME = "PmGen.zip"


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def _find_payload_zip(base_dir: Path) -> Path:
    candidates = [
        base_dir / PAYLOAD_ZIP_NAME,
        Path.cwd() / PAYLOAD_ZIP_NAME,
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Could not find bundled payload: {PAYLOAD_ZIP_NAME}")


def _is_safe_zip_path(dest_root: Path, member_name: str) -> bool:
    target_path = (dest_root / member_name).resolve()
    return os.path.commonpath([str(dest_root.resolve()), str(target_path)]) == str(dest_root.resolve())


def _safe_extract_zip(zip_path: Path, destination: Path) -> None:
    with ZipFile(zip_path, "r") as archive:
        for member in archive.namelist():
            if not _is_safe_zip_path(destination, member):
                raise ValueError(f"Unsafe zip entry detected: {member}")
        archive.extractall(destination)


def _resolve_payload_root(extract_root: Path) -> Path:
    if (extract_root / APP_EXE_NAME).exists() and (extract_root / "_internal").is_dir():
        return extract_root

    candidates = []
    for child in extract_root.iterdir():
        if child.is_dir() and (child / APP_EXE_NAME).exists() and (child / "_internal").is_dir():
            candidates.append(child)

    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError(f"Payload invalid. Expected {APP_EXE_NAME} and _internal in extracted content.")
    raise ValueError("Payload invalid. Multiple app roots detected in extracted content.")


def _choose_install_folder() -> Path | None:
    selected = filedialog.askdirectory(title="Select your current PmGen install folder")
    if not selected:
        return None
    return Path(selected).resolve()


def _replace_with_backup(target_dir: Path, payload_root: Path) -> Path:
    if not target_dir.exists() or not target_dir.is_dir():
        raise FileNotFoundError("Selected install folder does not exist.")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_dir = target_dir.parent / f"{target_dir.name}.backup.{timestamp}"

    shutil.move(str(target_dir), str(backup_dir))
    try:
        shutil.copytree(str(payload_root), str(target_dir))
    except Exception:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        shutil.move(str(backup_dir), str(target_dir))
        raise

    return backup_dir


def _launch_updated_app(target_dir: Path) -> None:
    app_path = target_dir / APP_EXE_NAME
    if not app_path.exists():
        raise FileNotFoundError(f"Updated app not found at: {app_path}")
    subprocess.Popen([str(app_path)], cwd=str(target_dir))


def main() -> int:
    root = Tk()
    root.withdraw()

    temp_session: Path | None = None
    backup_dir: Path | None = None
    target_dir: Path | None = None

    try:
        base_dir = _get_base_dir()
        bundled_zip = _find_payload_zip(base_dir)

        target_dir = _choose_install_folder()
        if target_dir is None:
            return 0

        if not messagebox.askyesno(
            "Confirm Update",
            f"This will fully replace:\n{target_dir}\n\nContinue?",
            parent=root,
        ):
            return 0

        temp_session = Path(tempfile.mkdtemp(prefix="pmgen_bootstrap_"))
        staged_zip = temp_session / PAYLOAD_ZIP_NAME
        extract_root = temp_session / "payload"
        extract_root.mkdir(parents=True, exist_ok=True)

        shutil.copy2(bundled_zip, staged_zip)
        _safe_extract_zip(staged_zip, extract_root)
        payload_root = _resolve_payload_root(extract_root)

        backup_dir = _replace_with_backup(target_dir, payload_root)

        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)

        _launch_updated_app(target_dir)
        messagebox.showinfo("Update Complete", "PmGen was updated successfully.", parent=root)
        return 0

    except Exception as exc:
        if backup_dir is not None and target_dir is not None and backup_dir.exists() and not target_dir.exists():
            try:
                shutil.move(str(backup_dir), str(target_dir))
            except Exception:
                pass

        messagebox.showerror("Update Failed", f"Update failed and was rolled back if possible.\n\n{exc}", parent=root)
        return 1

    finally:
        if temp_session is not None and temp_session.exists():
            shutil.rmtree(temp_session, ignore_errors=True)
        root.destroy()


if __name__ == "__main__":
    raise SystemExit(main())
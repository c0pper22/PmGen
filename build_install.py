from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ------------------------------
# Constants / defaults
# ------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
SPEC_FILE = PROJECT_ROOT / "pmgen.spec"
VENV_DIR = PROJECT_ROOT / ".venv"
DIST_DIR = PROJECT_ROOT / "dist" / "PmGen"
INSTALL_DIR = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "PmGen"
START_MENU_DIR = Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs"
START_MENU_SHORTCUT = START_MENU_DIR / "PmGen.lnk"
DESKTOP_DIR = Path(os.path.expanduser("~")) / "Desktop"
DESKTOP_SHORTCUT = DESKTOP_DIR / "PmGen.lnk"

PYTHON_EXE = sys.executable

# ------------------------------
# Utilities
# ------------------------------
def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None, check: bool = True) -> int:
    print(f"[RUN] {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=cwd, env=env, check=check)
    return proc.returncode

def ensure_venv(fresh: bool = False) -> Path:
    if fresh and VENV_DIR.exists():
        print("[INFO] Removing existing venv…")
        shutil.rmtree(VENV_DIR, ignore_errors=True)
    if not VENV_DIR.exists():
        print("[INFO] Creating venv…")
        run([PYTHON_EXE, "-m", "venv", str(VENV_DIR)])
    return VENV_DIR

def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"

def venv_pip() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "pip.exe"
    return VENV_DIR / "bin" / "pip"

def pip_install(pkgs: list[str]) -> None:
    run([str(venv_python()), "-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools"])
    run([str(venv_pip()), "install"] + pkgs)

def clean_build_artifacts() -> None:
    for p in ["build", "dist", ".spec_cache"]:
        path = PROJECT_ROOT / p
        if path.exists():
            print(f"[INFO] Removing {path} …")
            shutil.rmtree(path, ignore_errors=True)

def pyinstaller_build(console: bool, clean: bool) -> None:
    if clean:
        clean_build_artifacts()
    if not SPEC_FILE.exists():
        raise FileNotFoundError(f"Spec not found: {SPEC_FILE}")

    args = [str(venv_python()), "-m", "PyInstaller", "--clean", "-y", str(SPEC_FILE)]
    print("[INFO] Building with PyInstaller...")
    run(args)

    if console:
        print("[INFO] (Optional) Building console variant directly from entrypoint …")
        entry = PROJECT_ROOT / "pmgen" / "ui" / "app.py"
        run([str(venv_python()), "-m", "PyInstaller", "--clean", "-y",
             "--windowed", "--onefile" if False else "",
             "--name", "PmGen-Console",
             "--console",
             str(entry)])
        print("[WARN] Console variant built separately (./dist/PmGen-Console/).")

def copy_install() -> None:
    if not DIST_DIR.exists():
        raise FileNotFoundError(f"Built app not found: {DIST_DIR} — did the build succeed?")
    if INSTALL_DIR.exists():
        print(f"[INFO] Removing previous install at {INSTALL_DIR} …")
        shutil.rmtree(INSTALL_DIR, ignore_errors=True)
    print(f"[INFO] Installing to {INSTALL_DIR} …")
    shutil.copytree(DIST_DIR, INSTALL_DIR, dirs_exist_ok=True)

def create_shortcut(target_exe: Path, shortcut_path: Path) -> None:
    """Create a .lnk via win32com if available, else via a small VBScript."""
    target_exe = target_exe.resolve()
    workdir = target_exe.parent
    icon = (workdir / "PmGen.exe") if (workdir / "PmGen.exe").exists() else target_exe

    try:
        import win32com.client  # type: ignore
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(str(shortcut_path))
        shortcut.TargetPath = str(target_exe)
        shortcut.WorkingDirectory = str(workdir)
        shortcut.IconLocation = str(icon)
        shortcut.Description = "PmGen"
        shortcut.save()
        print(f"[INFO] Shortcut created: {shortcut_path}")
        return
    except Exception as e:
        print(f"[WARN] win32com not available ({e}), using VBScript fallback…")

    # VBScript fallback (no dependency on pywin32)
    vbs = f"""
    Set WshShell = WScript.CreateObject("WScript.Shell")
    Set lnk = WshShell.CreateShortcut("{shortcut_path}")
    lnk.TargetPath = "{target_exe}"
    lnk.WorkingDirectory = "{workdir}"
    lnk.IconLocation = "{icon}"
    lnk.Description = "PmGen"
    lnk.Save
    """
    tmp_vbs = PROJECT_ROOT / "_mk_shortcut.vbs"
    tmp_vbs.write_text(vbs.strip(), encoding="utf-8")
    try:
        run(["cscript", "//nologo", str(tmp_vbs)])
    finally:
        tmp_vbs.unlink(missing_ok=True)
    print(f"[INFO] Shortcut created: {shortcut_path}")

def install_shortcuts(add_desktop: bool) -> None:
    exe = INSTALL_DIR / "PmGen.exe"
    START_MENU_DIR.mkdir(parents=True, exist_ok=True)
    create_shortcut(exe, START_MENU_SHORTCUT)
    if add_desktop:
        create_shortcut(exe, DESKTOP_SHORTCUT)

def uninstall() -> None:
    removed_any = False
    if INSTALL_DIR.exists():
        print(f"[INFO] Removing {INSTALL_DIR} …")
        shutil.rmtree(INSTALL_DIR, ignore_errors=True)
        removed_any = True
    for s in (START_MENU_SHORTCUT, DESKTOP_SHORTCUT):
        if s.exists():
            print(f"[INFO] Removing {s} …")
            s.unlink(missing_ok=True)
            removed_any = True
    if not removed_any:
        print("[INFO] Nothing to uninstall.")

# ------------------------------
# Main CLI
# ------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Build & install PmGen on Windows")
    ap.add_argument("--fresh-venv", action="store_true", help="Recreate virtual environment")
    ap.add_argument("--console", action="store_true", help="Also build a console variant (dev aid)")
    ap.add_argument("--clean", action="store_true", help="Clean build artifacts before building")
    ap.add_argument("--desktop-shortcut", action="store_true", help="Create a desktop shortcut in addition to Start Menu")
    ap.add_argument("--uninstall", action="store_true", help="Uninstall the app and remove shortcuts")
    args = ap.parse_args()

    if args.uninstall:
        uninstall()
        return 0

    ensure_venv(fresh=args.fresh_venv)

    req = PROJECT_ROOT / "requirements.txt"
    if req.exists():
        print("[INFO] Installing requirements.txt …")
        pip_install(["-r", str(req)])
    else:
        pip_install([])

    print("[INFO] Installing build deps (pyinstaller, PyQt6, certifi, requests, keyring, pywin32)…")
    pip_install(["pyinstaller", "PyQt6", "certifi", "requests", "keyring", "pywin32"])

    pyinstaller_build(console=args.console, clean=args.clean)
    copy_install()
    install_shortcuts(add_desktop=args.desktop_shortcut)

    print(f"\n[OK] Installed to: {INSTALL_DIR}")
    print(f"[OK] Start Menu shortcut: {START_MENU_SHORTCUT}")
    if args.desktop_shortcut:
        print(f"[OK] Desktop shortcut: {DESKTOP_SHORTCUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

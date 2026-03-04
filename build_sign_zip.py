import os
import subprocess
import getpass
import glob
import zipfile

def get_password(pfx_path):
    password = getpass.getpass(prompt=f"Enter password for {pfx_path}: ")
    return password.strip()

def build_from_spec(spec_file):
    """Runs PyInstaller using the provided .spec file."""
    print(f"--- Building from {spec_file} ---")
    try:
        subprocess.run(["pyinstaller", "--noconfirm", "--clean", spec_file], check=True)
    except subprocess.CalledProcessError:
        print("Build failed. Check your .spec file logic.")
        exit(1)

def find_signtool():
    """Locates the latest version of signtool.exe in the Windows SDK folders."""
    base_path = r"C:\Program Files (x86)\Windows Kits\10\bin"
    search_pattern = os.path.join(base_path, "**", "x64", "signtool.exe")
    files = glob.glob(search_pattern, recursive=True)
    
    if not files:
        raise FileNotFoundError("signtool.exe not found. Is the Windows SDK installed?")
    
    files.sort(reverse=True)
    return files[0]

def sign_binary(signtool, password, binary_path, pfx_path):
    """Signs a single binary file."""
    try:
        cmd = [
            signtool, "sign",
            "/as",
            "/f", pfx_path,
            "/p", password,
            "/fd", "sha256",
            "/tr", "http://timestamp.digicert.com",
            "/td", "sha256",
            "/q",
            binary_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"Successfully signed: {os.path.relpath(binary_path, 'dist')}")
        else:
            print(f"FAILED to sign {binary_path}:")
            print(result.stderr)
            
    except Exception as e:
        print(f"Error signing {binary_path}: {e}")

def zip_directory(folder_path, output_zip):
    """Zips the entire content of a folder into a single archive."""
    print(f"--- Creating Zip: {output_zip} ---")
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_full_path = os.path.join(root, file)
                arcname = os.path.relpath(file_full_path, start=folder_path)
                zipf.write(file_full_path, arcname)
    print(f"Package created: {os.path.abspath(output_zip)}")

if __name__ == "__main__":
    DIST_DIR = "dist/PmGen"
    PFX_FILE = "./helpers/IBSCert.pfx"
    SPEC_FILE = "pmgen.spec"
    ZIP_NAME = "PmGen.zip"

    if not os.path.exists(PFX_FILE):
        print(f"Error: PFX file not found at {PFX_FILE}")
        exit(1)

    signtool_path = find_signtool()
    password = get_password(PFX_FILE)
    
    build_from_spec(SPEC_FILE)
    
    print("\n--- Starting Recursive Signing (EXEs, DLLs, PYDs) ---")
    if os.path.exists(DIST_DIR):
        extensions = ('*.exe', '*.dll', '*.pyd')
        files_to_sign = []
        for ext in extensions:
            files_to_sign.extend(glob.glob(os.path.join(DIST_DIR, "**", ext), recursive=True))

        for file_path in files_to_sign:
            sign_binary(signtool_path, password, file_path, PFX_FILE)
    else:
        print(f"Error: Build directory {DIST_DIR} not found.")
        exit(1)

    zip_directory(DIST_DIR, ZIP_NAME)
    print("\nPipeline Complete!")
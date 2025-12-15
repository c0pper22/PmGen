from pathlib import Path
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT
from PyInstaller.utils.hooks import collect_all, collect_data_files
from PyInstaller.building.datastruct import Tree

block_cipher = None
project_root = Path('.').resolve()
print(project_root)

# Third-party data
reportlab_datas = collect_data_files("reportlab")
certifi_datas, certifi_bins, certifi_hidden = collect_all('certifi')

# datas: ONLY (src, dest) pairs, no Tree here
datas = certifi_datas + reportlab_datas

# Icon tree: this dir MUST exist: pmgen/assets/icons
icons_tree = Tree(
    str(project_root / "pmgen" / "assets" / "icons"),
    prefix="pmgen/assets/icons",
)

hidden = [
    'pmgen.types',
    'pmgen.rules.base',
    'pmgen.rules.generic_life',
    'pmgen.rules.kit_link',
    'pmgen.rules.qty_override',
    'pmgen.engine.run_rules',
    'pmgen.engine.single_report',
    'pmgen.engine.resolve_to_pn',
    'pmgen.parsing.parse_pm_report',
    'pmgen.io.http_client',
    'pmgen.io.ribon_db',
    'pmgen.io.fetch_serials',
    'pmgen.canon.canon_utils',
    'pmgen.catalog.part_kit_catalog',
    "reportlab",
    "reportlab.lib",
    "reportlab.pdfbase",
    "reportlab.pdfbase.ttfonts",
    "reportlab.pdfbase.cidfonts",
    "reportlab.platypus",
    'requests', 'urllib3', 'idna', 'charset_normalizer', 'certifi',
    'keyring',
    'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'PyQt6.QtNetwork',
    'PyQt6.QtSvg', 'PyQt6.QtPrintSupport',
]

a = Analysis(
    ['pmgen/ui/app.py'],
    pathex=[str(project_root)],
    binaries=certifi_bins,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PyQt6.Qt3DCore', 'PyQt6.Qt3DExtras', 'PyQt6.Qt3DInput', 'PyQt6.Qt3DLogic', 'PyQt6.Qt3DRender',
        'PyQt6.QtBluetooth', 'PyQt6.QtNfc', 'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebView', 'PyQt6.QtWebSockets', 'PyQt6.QtQuick3D', 'PyQt6.QtPdf',
        'PyQt6.QtPdfWidgets', 'PyQt6.QtQml', 'PyQt6.QtQuick', 'PyQt6.QtQuickWidgets',
        'PyQt6.QtPositioning', 'PyQt6.QtSensors', 'PyQt6.QtSerialPort', 'PyQt6.QtSql',
        'PyQt6.QtHelp', 'PyQt6.QtTest', 'PyQt6.QtRemoteObjects', 'PyQt6.QtStateMachine',
        'PyQt6.QtTextToSpeech', 'PyQt6.QtDesigner', 'PyQt6.QAxContainer',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    exclude_binaries=True,
    name='PmGen',
    console=False,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    icon=('pmgen.ico' if Path('pmgen.ico').exists() else None),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    icons_tree,
    strip=False,
    upx=True,
    name='PmGen'
)

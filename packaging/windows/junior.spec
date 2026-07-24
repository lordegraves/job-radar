"""Build Junior's Windows desktop bundle with all packaged application data."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules


project_root = Path(SPECPATH).resolve().parents[1]
job_radar_data = collect_data_files("job_radar")
webview_data, webview_binaries, webview_hidden = collect_all("webview")
keyring_hidden = collect_submodules("keyring.backends")

analysis = Analysis(
    [str(project_root / "job_radar" / "desktop_launcher.py")],
    pathex=[str(project_root)],
    binaries=webview_binaries,
    datas=[*job_radar_data, *webview_data],
    hiddenimports=[*webview_hidden, *keyring_hidden],
    excludes=[],
    noarchive=False,
)
python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Junior",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(project_root / "job_radar" / "static" / "junior.ico"),
)

bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="Junior",
)

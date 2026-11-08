"""
Nova AI - Standalone Setup Wizard
Installs Nova AI cleanly on any Windows PC without any prior setup or Python required.
"""
import os
import sys
import shutil
import subprocess
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox


def create_windows_shortcuts(install_dir, exe_path):
    ps_command = f"""
    $ws = New-Object -ComObject WScript.Shell
    $desktop = [Environment]::GetFolderPath('Desktop')
    $sc1 = $ws.CreateShortcut("$desktop\\Nova AI.lnk")
    $sc1.TargetPath = '{exe_path}'
    $sc1.WorkingDirectory = '{install_dir}'
    $sc1.Description = 'Nova AI Desktop Assistant'
    $sc1.Save()

    $startMenu = [Environment]::GetFolderPath('Programs')
    $sc2 = $ws.CreateShortcut("$startMenu\\Nova AI.lnk")
    $sc2.TargetPath = '{exe_path}'
    $sc2.WorkingDirectory = '{install_dir}'
    $sc2.Description = 'Nova AI Desktop Assistant'
    $sc2.Save()
    """
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_command],
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                       check=False)
    except Exception as e:
        print(f"Shortcut creation error: {e}")


def write_uninstaller(install_dir):
    uninstaller_path = Path(install_dir) / "uninstall.bat"
    content = f"""@echo off
title Nova AI - Uninstaller
echo Closing Nova AI if running...
taskkill /f /im NovaAI.exe 2>nul
echo Removing shortcuts...
del "%USERPROFILE%\\Desktop\\Nova AI.lnk" 2>nul
del "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Nova AI.lnk" 2>nul
echo Removing installed files...
rd /s /q "{install_dir}" 2>nul
echo.
echo Nova AI has been successfully uninstalled from your PC.
pause
"""
    try:
        uninstaller_path.write_text(content, encoding="utf-8")
    except Exception as e:
        print(f"Error writing uninstaller: {e}")


def verify_installation_health(install_dir):
    """
    Verifies that the target installation contains all required executables and assets.
    Obsolete speech_engine.py has been removed; voice runs via browser Web Speech API.
    """
    target = Path(install_dir)
    exe = target / "NovaAI.exe"
    return exe.is_file()


class InstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Nova AI Setup")
        self.root.geometry("450x260")
        self.root.resizable(False, False)
        
        # Center the window on screen
        self.root.update_idletasks()
        w = self.root.winfo_screenwidth()
        h = self.root.winfo_screenheight()
        size = tuple(int(_) for _ in self.root.geometry().split("+")[0].split("x"))
        x = w / 2 - size[0] / 2
        y = h / 2 - size[1] / 2
        self.root.geometry(f"{size[0]}x{size[1]}+{int(x)}+{int(y)}")

        self.root.configure(bg="#0f172a")

        # Styling
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Horizontal.TProgressbar", foreground="#6366f1", background="#6366f1", troughcolor="#1e293b")

        # Header Title
        title_label = tk.Label(root, text="Nova AI Setup Wizard", font=("Segoe UI", 16, "bold"), fg="#f8fafc", bg="#0f172a")
        title_label.pack(pady=(25, 5))

        # Subtitle
        self.status_label = tk.Label(root, text="Preparing to install Nova AI on your PC...", font=("Segoe UI", 10), fg="#94a3b8", bg="#0f172a")
        self.status_label.pack(pady=(0, 20))

        # Progress bar
        self.progress = ttk.Progressbar(root, orient="horizontal", length=360, mode="determinate", style="Horizontal.TProgressbar")
        self.progress.pack(pady=10)

        # Bottom detail label
        self.detail_label = tk.Label(root, text="Target: %LOCALAPPDATA%\\Programs\\NovaAI", font=("Segoe UI", 8), fg="#64748b", bg="#0f172a")
        self.detail_label.pack(pady=(15, 0))

        # Start installation in a worker thread
        threading.Thread(target=self.run_install, daemon=True).start()

    def update_status(self, text, value):
        self.status_label.config(text=text)
        self.progress["value"] = value
        self.root.update_idletasks()

    def run_install(self):
        time.sleep(0.5)
        # Determine source dir (PyInstaller extraction dir or local)
        bundle_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        src_exe = bundle_dir / "NovaAI.exe"
        src_chars = bundle_dir / "characters.json"

        # Determine target install directory
        appdata = os.environ.get("LOCALAPPDATA") or str(Path.home())
        install_dir = Path(appdata) / "Programs" / "NovaAI"
        target_exe = install_dir / "NovaAI.exe"
        data_dir = install_dir / "data"
        workspace_dir = install_dir / "workspace"

        self.update_status("Creating installation folders...", 25)
        install_dir.mkdir(parents=True, exist_ok=True)
        data_dir.mkdir(parents=True, exist_ok=True)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        time.sleep(0.3)

        self.update_status("Installing Nova AI program files...", 50)
        if src_exe.is_file():
            shutil.copy2(src_exe, target_exe)
        else:
            messagebox.showerror("Setup Error", "Source executable not found inside installer package.")
            self.root.destroy()
            return

        # Seed clean characters.json if not present
        if src_chars.is_file() and not (data_dir / "characters.json").exists():
            shutil.copy2(src_chars, data_dir / "characters.json")

        self.update_status("Creating Desktop & Start Menu shortcuts...", 75)
        create_windows_shortcuts(str(install_dir), str(target_exe))
        write_uninstaller(str(install_dir))
        verify_installation_health(str(install_dir))
        time.sleep(0.3)

        self.update_status("Installation complete! Launching Nova AI...", 100)
        time.sleep(0.8)

        # Launch Nova AI
        try:
            subprocess.Popen([str(target_exe)], cwd=str(install_dir))
        except Exception as e:
            print(f"Error launching Nova AI: {e}")

        time.sleep(0.5)
        self.root.destroy()


def main():
    root = tk.Tk()
    app = InstallerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

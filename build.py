#!/usr/bin/env python3

import os
import sys
import subprocess
import platform
from pathlib import Path

def build_executable():
    """Build single executable using PyInstaller"""
    
    print("DroneCAN Batch Firmware Updater - Build Script")
    print("=" * 50)
    
    # Get current directory
    project_dir = Path(__file__).parent
    src_dir = project_dir / "src"
    main_script = src_dir / "main.py"
    
    # Check if main script exists
    if not main_script.exists():
        print(f"Error: Main script not found at {main_script}")
        return False
    
    # Determine output name based on platform
    system = platform.system().lower()
    if system == "windows":
        output_name = "dronecan-batch-updater.exe"
    else:
        output_name = "dronecan-batch-updater"
    
    print(f"Building for platform: {platform.system()}")
    print(f"Output executable: {output_name}")
    
    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",  # Single executable
        "--name", output_name.replace(".exe", ""),  # Name without extension
        "--distpath", str(project_dir / "dist"),  # Output directory
        "--workpath", str(project_dir / "build"),  # Work directory
        "--specpath", str(project_dir),  # Spec file location
        "--add-data", f"{src_dir}:src",  # Include src directory
        "--hidden-import", "dronecan",
        "--hidden-import", "pymavlink",
        "--hidden-import", "serial",
        "--hidden-import", "rich",
        "--hidden-import", "colorama",
        "--hidden-import", "click",
        str(main_script)
    ]
    
    # Add additional data files
    firmware_dir = project_dir / "firmware"
    if firmware_dir.exists():
        cmd.extend(["--add-data", f"{firmware_dir}:firmware"])
        print("Including firmware directory in build")
    
    print("\nRunning PyInstaller...")
    print("Command:", " ".join(cmd))
    print()
    
    try:
        # Run PyInstaller
        result = subprocess.run(cmd, cwd=project_dir, check=True)
        
        print("\n" + "=" * 50)
        print("Build completed successfully!")
        
        # Check if executable was created
        dist_dir = project_dir / "dist"
        executable_path = dist_dir / output_name
        
        if executable_path.exists():
            print(f"Executable created: {executable_path}")
            print(f"Size: {executable_path.stat().st_size / (1024*1024):.1f} MB")
            
            # Make executable on Unix systems
            if system != "windows":
                os.chmod(executable_path, 0o755)
                print("Executable permissions set")
            
            return True
        else:
            print(f"Warning: Expected executable not found at {executable_path}")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"Error: PyInstaller failed with return code {e.returncode}")
        return False
    except FileNotFoundError:
        print("Error: PyInstaller not found. Please install it with: pip install pyinstaller")
        return False

def clean_build():
    """Clean build artifacts"""
    project_dir = Path(__file__).parent
    
    # Directories to clean
    clean_dirs = [
        project_dir / "build",
        project_dir / "dist",
        project_dir / "__pycache__",
        project_dir / "src" / "__pycache__"
    ]
    
    # Files to clean
    clean_files = [
        project_dir / "*.spec"
    ]
    
    print("Cleaning build artifacts...")
    
    import shutil
    for dir_path in clean_dirs:
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print(f"Removed: {dir_path}")
    
    import glob
    for pattern in clean_files:
        for file_path in glob.glob(str(pattern)):
            os.remove(file_path)
            print(f"Removed: {file_path}")

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        clean_build()
        return
    
    # Check Python version
    if sys.version_info < (3, 7):
        print("Error: Python 3.7 or higher is required")
        return
    
    # Check if running in virtual environment
    if not hasattr(sys, 'base_prefix') or sys.base_prefix == sys.prefix:
        print("Warning: Not running in a virtual environment")
        response = input("Continue anyway? (y/N): ")
        if response.lower() not in ['y', 'yes']:
            return
    
    # Build the executable
    success = build_executable()
    
    if success:
        print("\nBuild completed successfully!")
        print("You can now distribute the single executable file.")
    else:
        print("\nBuild failed. Please check the error messages above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
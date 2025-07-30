#!/usr/bin/env python3
"""
Simple linting script for the dronecan-batch-updater project.
Runs flake8 on the src/ directory.
"""

import subprocess
import sys
from pathlib import Path

def run_command(cmd, description):
    """Run a command and return success status."""
    print(f"\n🔍 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} passed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        return False

def main():
    """Run all linting tools."""
    print("🚀 Running Python linting tools...")
    
    # Ensure we're in the project directory
    project_root = Path(__file__).parent
    src_dir = project_root / "src"
    
    if not src_dir.exists():
        print("❌ src/ directory not found!")
        return 1
    
    success = True
    
    # Run linting tools
    commands = [
        ("flake8 src/", "Flake8 (style guide enforcement)"),
        ("pylint src/", "Pylint (comprehensive code analysis)"),
    ]
    
    for cmd, desc in commands:
        if not run_command(cmd, desc):
            success = False
    
    if success:
        print("\n🎉 All linting checks passed!")
        return 0
    else:
        print("\n💥 Linting checks failed. Please fix the reported issues.")
        return 1

def fix_issues():
    """Linting tools don't have auto-fix capability."""
    print("🔧 Flake8 and Pylint don't have auto-fix capability.")
    print("Please manually fix the reported issues and run the script again.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--fix":
        fix_issues()
    else:
        sys.exit(main())
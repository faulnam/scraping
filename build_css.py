"""
Utility script to compile Tailwind CSS using tailwind.config.js standalone CLI.
"""
import os
import subprocess
import sys

def build():
    root = os.path.dirname(os.path.abspath(__file__))
    input_css = os.path.join("app", "static", "src", "app.css")
    output_css = os.path.join("app", "static", "css", "app.css")
    tailwind_exe = os.path.join(root, "tailwindcss.exe")
    
    cmd = [
        tailwind_exe,
        "-i", input_css,
        "-o", output_css,
    ]
    
    print("Compiling Tailwind CSS from tailwind.config.js...")
    result = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    
    if result.returncode == 0:
        css_path = os.path.join(root, output_css)
        size = os.path.getsize(css_path)
        content = open(css_path, "r", encoding="utf-8").read()
        print(f"[OK] Successfully built {output_css} ({size} bytes)")
        print(f"     Checks: 'z-50' -> {'z-50' in content}, 'bg-slate-950' -> {'bg-slate-950' in content}")
    else:
        print(f"[ERROR] Tailwind build failed with exit code {result.returncode}")
        sys.exit(result.returncode)

if __name__ == "__main__":
    build()

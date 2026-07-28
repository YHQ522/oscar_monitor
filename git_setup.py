"""Initialize git repo for oscar_monitor and prepare for GitHub push."""
import subprocess
import os
import sys

GIT = r"D:\VSCode\Git\bin\git.exe"
PROJECT = r"d:\VSCode\Project\Shentong\oscar_monitor"
os.chdir(PROJECT)

def run(cmd, cwd=PROJECT):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
    out = (result.stdout + result.stderr).strip()
    if out:
        print(out)
    return result.returncode == 0

print("=== Git Init ===")
if not os.path.exists(os.path.join(PROJECT, ".git")):
    run([GIT, "init"])

print("=== Create .gitignore ===")
gitignore = """# Python
__pycache__/
*.pyc
*.pyo
.venv*/
.venv_test/

# Data files (secrets, configs)
data/servers.json
data/users.json
data/config.json
data/audit.jsonl

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db

# Build artifacts
dist/
build/
*.spec
"""
with open(os.path.join(PROJECT, ".gitignore"), "w", encoding="utf-8") as f:
    f.write(gitignore)
print("Created .gitignore")

print("=== Git Add ===")
run([GIT, "add", "."])

print("=== Git Status ===")
run([GIT, "status", "--short"])

# Set user config (required for commit)
print("=== Configure Git User ===")
run([GIT, "config", "user.email", "admin@oscar-monitor.local"])
run([GIT, "config", "user.name", "Oscar Monitor"])

print("=== Git Commit ===")
run([GIT, "commit", "-m", "feat: oscar_monitor 管控平台 v2.0\n\n- Flask web app with dashboard, server management, control\n- SSH-based data collection (OscarDB/PostgreSQL)\n- OS monitoring (Linux/Windows)\n- User auth with PBKDF2 password hashing\n- Log persistence, alerting, audit trail\n- Modern UI with glassmorphism + SweetAlert2\n- SQL injection protected via parameterized queries"])

print("=== DONE ===")
print("Ready to push. Run:")
print("  git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git")
print("  git push -u origin main")

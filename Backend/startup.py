#!/usr/bin/env python3
"""
Startup script for checking all dependencies and imports before running Flask
"""
import sys

print("=" * 60)
print("LATENCY TOOL - STARTUP CHECK")
print("=" * 60)

# Check Python version
print(f"\n✓ Python version: {sys.version}")

# Check required imports
print("\nChecking imports...")
required_modules = {
    'flask': 'Flask',
    'flask_cors': 'Flask-CORS',
    'werkzeug': 'Werkzeug',
    'requests': 'requests',
    'openpyxl': 'openpyxl',
}

all_good = True
for module, name in required_modules.items():
    try:
        __import__(module)
        print(f"  ✓ {name}")
    except ImportError as e:
        print(f"  ✗ {name} - NOT INSTALLED")
        all_good = False

# Check if app.py can be imported
print("\nChecking app.py...")
try:
    from app import app
    print("  ✓ app.py imported successfully")
except Exception as e:
    print(f"  ✗ Error importing app.py: {e}")
    all_good = False

# Check if zzzzz.py exists and can be imported
print("\nChecking zzzzz.py...")
try:
    from zzzzz import main
    print("  ✓ zzzzz.py imported successfully")
except Exception as e:
    print(f"  ✗ Error importing zzzzz.py: {e}")
    all_good = False

# Check directories
print("\nChecking directories...")
import os
dirs = ['uploads', 'reports']
for d in dirs:
    if not os.path.exists(d):
        os.makedirs(d)
        print(f"  ✓ Created {d}/")
    else:
        print(f"  ✓ {d}/ exists")

print("\n" + "=" * 60)
if all_good:
    print("✓ ALL CHECKS PASSED - Starting Flask app...")
    print("=" * 60 + "\n")
    # Start Flask app
    from app import app
    app.run(debug=True, host="0.0.0.0", port=5000)
else:
    print("✗ SOME CHECKS FAILED - Fix errors above before running")
    print("=" * 60)
    sys.exit(1)

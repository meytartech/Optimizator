#!/usr/bin/env python
"""Start the backtesting & optimization web application"""

import os
import sys
from multiprocessing import freeze_support

# Add root to path
root_path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, root_path)

# Ignore noisy folders for the dev reloader (fnmatch patterns, absolute paths)
EXCLUDED_RELOAD_PATTERNS = [
    os.path.abspath(os.path.join(root_path, "app", "results", "*")),
    os.path.abspath(os.path.join(root_path, "results", "*")),
    os.path.abspath(os.path.join(root_path, "app", "strategies", "*")),
    os.path.abspath(os.path.join(root_path, "strategies", "*")),
    os.path.abspath(os.path.join(root_path, "app", "temp_results", "*")),
    os.path.abspath(os.path.join(root_path, "temp_results", "*")),
    os.path.abspath(os.path.join(root_path, "app", "db", "*")),
    os.path.abspath(os.path.join(root_path, "app", "uploaded-csv", "*")),
    os.path.abspath(os.path.join(root_path, "db", "*")),
    os.path.abspath(os.path.join(root_path, "uploaded-csv", "*")),
]

if __name__ == '__main__':
    # Windows multiprocessing support
    freeze_support()
    
    # Import Flask app only in main process, not in worker processes
    from app.app import app
    print("Starting Backtesting & Optimization System...")
    print("Navigate to: http://localhost:5000")
    print("Press Ctrl+C to stop the server")
    # Keep debug mode but avoid restarts on non-Python artifacts (results folders)
    # Use the 'stat' reloader and explicitly ignore results/strategies/temp_results/db changes.
    app.run(
        debug=True,
        host='localhost',
        port=5000,
        use_reloader=True,
        reloader_type='stat',
        exclude_patterns=EXCLUDED_RELOAD_PATTERNS,
    )

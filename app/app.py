"""
Flask Web Application for Backtesting & Optimization System

Main entry point that initializes Flask app and registers modular routes.
All route logic is delegated to blueprint modules in the routes/ package.
"""

from flask import Flask
import os
import sys
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.jobs import JobManager
from app.routes import register_blueprints

# ============================================================================
# Flask Application Setup
# ============================================================================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'

# App directories
APP_DIR = os.path.dirname(os.path.abspath(__file__))
app.config['UPLOAD_FOLDER'] = os.path.join(APP_DIR, 'db')
app.config['STRATEGIES_FOLDER'] = os.path.join(APP_DIR, 'strategies')
app.config['RESULTS_FOLDER'] = os.path.join(APP_DIR, 'results')
app.config['TEMP_RESULTS_FOLDER'] = os.path.join(APP_DIR, 'temp_results')
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1GB max file size

# Legacy path fallbacks
LEGACY_DATA_DIR = os.path.join(os.path.dirname(APP_DIR), 'data')
LEGACY_UPLOADS = os.path.join(LEGACY_DATA_DIR, 'db')
LEGACY_STRATEGIES = os.path.join(LEGACY_DATA_DIR, 'strategies')

# Create required directories
for folder in [app.config['UPLOAD_FOLDER'], app.config['STRATEGIES_FOLDER'], 
               app.config['TEMP_RESULTS_FOLDER']]:
    os.makedirs(folder, exist_ok=True)

for subfolder in ['backtests', 'optimizations']:
    os.makedirs(os.path.join(app.config['RESULTS_FOLDER'], subfolder), exist_ok=True)

# ============================================================================
# Job Manager Setup
# ============================================================================
job_manager = JobManager(jobs_dir=os.path.join(APP_DIR, 'jobs'))

# Mark any running jobs as failed (server restart detected)
logger.info("=" * 60)
logger.info("APP STARTUP - Checking for orphaned running jobs")
for job in job_manager.list_jobs():
    if job.status == 'running':
        logger.warning(f"Marking orphaned job as failed: {job.job_id}")
        job.status = 'failed'
        job.error = 'Server restart detected'
        job.completed_at = datetime.now().isoformat()
        job_manager._save_job(job)

# Clear old jobs (older than 1 day)
deleted_count = job_manager.clear_old_jobs(days=1)
if deleted_count > 0:
    logger.info(f"Cleaned up {deleted_count} old jobs (>1 day)")
logger.info("=" * 60)

# Store job_manager in app context for access in routes
app.job_manager = job_manager

# ============================================================================
# Register Modular Routes (from blueprints)
# ============================================================================
register_blueprints(app)


if __name__ == '__main__':
    print("=" * 60)
    print("Backtesting & Optimization System".center(60))
    print("=" * 60)
    print("\nStarting Flask server...")
    print("Open your browser to: http://localhost:5000")
    print("\nPress Ctrl+C to stop the server\n")
    
    app.run(debug=False, host='0.0.0.0', port=5000)

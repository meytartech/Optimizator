"""
Data management routes - CSV uploads, preview, and deletion.
"""

from flask import Blueprint, request, jsonify, render_template
import os
from datetime import datetime
from werkzeug.utils import secure_filename
import logging

from core.data_loader import CSVDataLoader
from core.score_loader import ScoreDataLoader

logger = logging.getLogger(__name__)
bp = Blueprint('data', __name__, url_prefix='')


def get_app_config():
    """Get app config from Flask current_app context."""
    from flask import current_app
    return current_app.config


def list_data_files():
    """Return unique CSV filenames from current and legacy upload folders."""
    from flask import current_app
    config = current_app.config
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    LEGACY_DATA_DIR = os.path.join(os.path.dirname(APP_DIR), 'data')
    LEGACY_UPLOADS = os.path.join(LEGACY_DATA_DIR, 'db')
    
    files = set()
    if os.path.isdir(config['UPLOAD_FOLDER']):
        files.update([f for f in os.listdir(config['UPLOAD_FOLDER']) if f.endswith('.csv')])
    if os.path.isdir(LEGACY_UPLOADS):
        files.update([f for f in os.listdir(LEGACY_UPLOADS) if f.endswith('.csv')])
    return sorted(files)


def get_data_file_path(filename: str) -> str:
    """Resolve a CSV file path, preferring current folder then legacy."""
    from flask import current_app
    config = current_app.config
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    LEGACY_DATA_DIR = os.path.join(os.path.dirname(APP_DIR), 'data')
    LEGACY_UPLOADS = os.path.join(LEGACY_DATA_DIR, 'db')
    
    preferred = os.path.join(config['UPLOAD_FOLDER'], filename)
    # Always prefer the current UPLOAD_FOLDER for saving
    if os.path.exists(preferred):
        return preferred
    # For reading, check legacy folder, but always return preferred for new uploads
    if os.path.exists(os.path.join(LEGACY_UPLOADS, filename)):
        return os.path.join(LEGACY_UPLOADS, filename)
    # For new files, always save to preferred location
    return preferred


def list_score_files():
    """Return unique .db filenames from uploads folder and project db folder."""
    from flask import current_app
    config = current_app.config
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    files = set()
    # Current uploads folder (.db uploaded via web UI)
    uploads_dir = config['UPLOAD_FOLDER']
    if os.path.isdir(uploads_dir):
        files.update([f for f in os.listdir(uploads_dir) if f.lower().endswith('.db')])

    # Project-level db folder (manual/CLI-managed databases)
    project_db_dir = os.path.join(os.path.dirname(APP_DIR), 'db')
    if os.path.isdir(project_db_dir):
        files.update([f for f in os.listdir(project_db_dir) if f.lower().endswith('.db')])

    return sorted(files)


@bp.route('/data')
def data_management():
    """Data management page - view and upload CSV files."""
    files = []
    for filename in list_data_files():
        filepath = get_data_file_path(filename)
        size = os.path.getsize(filepath)
        modified = datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%Y-%m-%d %H:%M')
        
        files.append({
            'name': filename,
            'size': f"{size / 1024:.1f} KB" if size < 1024*1024 else f"{size / (1024*1024):.1f} MB",
            'modified': modified
        })

    # Also list score database files (.db)
    score_files = []
    for filename in list_score_files():
        # Prefer current uploads folder for metadata if present, else fallback to db folder
        from flask import current_app
        config = current_app.config
        APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        preferred_path = os.path.join(config['UPLOAD_FOLDER'], filename)
        fallback_path = os.path.join(os.path.dirname(APP_DIR), 'db', filename)
        filepath = preferred_path if os.path.exists(preferred_path) else fallback_path
        if not os.path.exists(filepath):
            continue
        size = os.path.getsize(filepath)
        modified = datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%Y-%m-%d %H:%M')
        score_files.append({
            'name': filename,
            'size': f"{size / 1024:.1f} KB" if size < 1024*1024 else f"{size / (1024*1024):.1f} MB",
            'modified': modified
        })
    
    return render_template('data.html', files=files, score_files=score_files)


@bp.route('/data/upload', methods=['POST'])
def upload_data():
    """Handle CSV file upload."""
    from flask import current_app
    config = current_app.config
    
    logger.info("=" * 60)
    logger.info("DATA UPLOAD REQUEST")
    if 'file' not in request.files:
        logger.error("Upload failed: No file provided")
        return
    
    file = request.files['file']
    if file.filename == '':
        return
    
    if not file.filename.endswith('.csv'):
        return
    
    filename = secure_filename(file.filename)
    filepath = get_data_file_path(filename)
    logger.info(f"Uploading file: {filename}")
    file.save(filepath)
    
    # Validate the uploaded file
    try:
        data = CSVDataLoader.load_csv(filepath)
        if not CSVDataLoader.validate_data(data):
            logger.error("Validation failed")
        
        info = CSVDataLoader.get_data_info(data)
        logger.info(f"✓ File uploaded successfully: {filename}")
        logger.info(f"  Rows: {info['rows']}, Columns: {info['columns']}")
        return jsonify({'success': True, 'filename': filename, 'info': info})
    except Exception as e:
        logger.error(f"✗ Upload failed: {str(e)}")
        if os.path.exists(filepath):
            os.remove(filepath)
        return


@bp.route('/scores/upload', methods=['POST'])
def upload_scores_db():
    """Handle score database (.db) upload to the same uploads folder as CSV."""
    from flask import current_app
    config = current_app.config
    
    logger.info("=" * 60)
    logger.info("SCORES DB UPLOAD REQUEST")
    if 'file' not in request.files:
        logger.error("Upload failed: No file provided")
        return
    
    file = request.files['file']
    if file.filename == '':
        return
    
    if not file.filename.endswith('.db'):
        return
    
    filename = secure_filename(file.filename)
    # Always save uploads to current uploads folder
    filepath = os.path.join(config['UPLOAD_FOLDER'], filename)
    logger.info(f"Uploading scores db: {filename}")
    file.save(filepath)
    
    # Validate the uploaded database
    try:
        is_valid = ScoreDataLoader.validate_database(filepath)
        if not is_valid:
            logger.error("Validation failed")
        logger.info(f"✓ Scores DB uploaded and validated: {filename}")
        return jsonify({'success': True, 'filename': filename})
    except Exception as e:
        logger.error(f"✗ Upload failed: {str(e)}")
        if os.path.exists(filepath):
            os.remove(filepath)
        return


@bp.route('/data/preview/<filename>')
def preview_data(filename):
    """Preview data from CSV file."""
    filepath = get_data_file_path(filename)
    
    if not os.path.exists(filepath):
        return
    
    try:
        data = CSVDataLoader.load_csv(filepath)
        info = CSVDataLoader.get_data_info(data)
        preview = data[:100]  # First 100 rows
        
        return jsonify({
            'info': info,
            'preview': preview
        })
    except Exception as e:
        return


@bp.route('/data/delete/<filename>', methods=['POST'])
def delete_data(filename):
    """Delete a CSV file."""
    from flask import current_app
    config = current_app.config
    
    filepath = os.path.join(config['UPLOAD_FOLDER'], filename)
    
    if not os.path.exists(filepath):
        return
    
    try:
        os.remove(filepath)
        return jsonify({'success': True})
    except Exception as e:
        return


@bp.route('/scores/delete/<filename>', methods=['POST'])
def delete_scores_db(filename):
    """Delete a scores .db file from uploads folder."""
    from flask import current_app
    config = current_app.config
    
    filepath = os.path.join(config['UPLOAD_FOLDER'], filename)
    
    if not os.path.exists(filepath):
        return jsonify({'success': False, 'error': 'File not found'}), 404
    
    try:
        os.remove(filepath)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

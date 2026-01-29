"""
Data management routes - CSV uploads, preview, and deletion.
"""

from flask import Blueprint, request, jsonify, render_template
import os
from datetime import datetime
from werkzeug.utils import secure_filename
import logging

from core.score_loader import ScoreDataLoader

logger = logging.getLogger(__name__)
bp = Blueprint('data', __name__, url_prefix='')


def get_app_config():
    """Get app config from Flask current_app context."""
    from flask import current_app
    return current_app.config


def list_data_files():
    """Return unique .db filenames from current and legacy upload folders."""
    from flask import current_app
    config = current_app.config
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    LEGACY_DATA_DIR = os.path.join(os.path.dirname(APP_DIR), 'data')
    LEGACY_UPLOADS = os.path.join(LEGACY_DATA_DIR, 'db')
    
    files = set()
    if os.path.isdir(config['UPLOAD_FOLDER']):
        # Include only combined .db files
        for f in os.listdir(config['UPLOAD_FOLDER']):
            if f.lower().endswith('.db'):
                full_path = os.path.join(config['UPLOAD_FOLDER'], f)
                if ScoreDataLoader.is_valid_db(full_path):
                    files.add(f)
    
    if os.path.isdir(LEGACY_UPLOADS):
        for f in os.listdir(LEGACY_UPLOADS):
            if f.lower().endswith('.db'):
                full_path = os.path.join(LEGACY_UPLOADS, f)
                if ScoreDataLoader.is_valid_db(full_path):
                    files.add(f)
    
    return sorted(files)


def get_data_file_path(filename: str) -> str:
    """Resolve a .db file path, preferring current folder then legacy."""
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


@bp.route('/data')
def data_management():
    """Data management page - view and upload combined .db files."""
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
    
    return render_template('data.html', files=files)


@bp.route('/data/upload', methods=['POST'])
def upload_data():
    """Handle combined .db file upload ."""
    from flask import current_app
    config = current_app.config
    
    logger.info("=" * 60)
    logger.info("DATA UPLOAD REQUEST")
    if 'file' not in request.files:
        logger.error("Upload failed: No file provided")
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'Empty filename'}), 400
    
    # Accept only .db files
    if not file.filename.lower().endswith('.db'):
        return jsonify({'success': False, 'error': 'Only .db files accepted'}), 400
    
    filename = secure_filename(file.filename)
    filepath = get_data_file_path(filename)
    logger.info(f"Uploading combined .db file: {filename}")
    file.save(filepath)
    
    # Validate the uploaded file
    try:
        # Validate combined .db format
        if not ScoreDataLoader.is_valid_db(filepath):
            logger.error("Not a combined .db format (missing required columns: timestamp, score_1m, score_5m, score_15m, score_60m, high, low, open, close)")
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({'success': False, 'error': 'Invalid combined .db format. Required columns: timestamp, score_1m, score_5m, score_15m, score_60m, high, low, open, close'}), 400
        
        # Load to get info
        unified_data = ScoreDataLoader.load_combined_db(filepath)
        logger.info(f"✓ Combined .db uploaded successfully: {filename}")
        logger.info(f"  Unified bars: {len(unified_data)}")
        return jsonify({
            'success': True, 
            'filename': filename, 
            'info': {
                'price_bars': len(unified_data),
                'score_records': len(unified_data) * 4,  # 4 timeframes per bar
                'format': 'combined_db'
            }
        })
    
    except Exception as e:
        logger.error(f"✗ Upload failed: {str(e)}")
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'success': False, 'error': str(e)}), 500


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


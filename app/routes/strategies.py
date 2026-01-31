"""
Strategy management routes - upload, view, and generate strategy templates.
"""

from flask import Blueprint, request, jsonify, render_template
import os
from datetime import datetime
from werkzeug.utils import secure_filename
import logging

logger = logging.getLogger(__name__)
bp = Blueprint('strategies', __name__, url_prefix='')

def list_strategies():
    """Return unique strategy names (without .py) from current and legacy folders."""
    from flask import current_app
    config = current_app.config
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    LEGACY_DATA_DIR = os.path.join(os.path.dirname(APP_DIR), 'data')
    LEGACY_STRATEGIES = os.path.join(LEGACY_DATA_DIR, 'strategies')
    
    names = set()
    if os.path.isdir(config['STRATEGIES_FOLDER']):
        names.update([f[:-3] for f in os.listdir(config['STRATEGIES_FOLDER']) if f.endswith('.py') and not f.startswith('__')])
    if os.path.isdir(LEGACY_STRATEGIES):
        names.update([f[:-3] for f in os.listdir(LEGACY_STRATEGIES) if f.endswith('.py') and not f.startswith('__')])
    return sorted(names)


def resolve_strategy_path(strategy_name: str) -> str:
    """Resolve full path to a strategy .py file, preferring current folder."""
    from flask import current_app
    config = current_app.config
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    LEGACY_DATA_DIR = os.path.join(os.path.dirname(APP_DIR), 'data')
    LEGACY_STRATEGIES = os.path.join(LEGACY_DATA_DIR, 'strategies')
    
    preferred = os.path.join(config['STRATEGIES_FOLDER'], f"{strategy_name}.py")
    if os.path.exists(preferred):
        return preferred
    return os.path.join(LEGACY_STRATEGIES, f"{strategy_name}.py")


"""
Optimization routes - parameter optimization and configuration.
"""

from flask import Blueprint, request, jsonify, render_template, current_app
import os
import json
from datetime import datetime
import pytz
import importlib.util
import logging
import threading

from core.data_loader import CSVDataLoader
from core.score_loader import ScoreDataLoader
from .data import list_data_files, get_data_file_path, list_score_files
from .strategies import list_strategies, resolve_strategy_path

logger = logging.getLogger(__name__)
bp = Blueprint('optimize', __name__, url_prefix='')


def snake_to_pascal_case(name):
    """Convert snake_case to PascalCase (e.g., mnq_strategy -> MNQStrategy)."""
    parts = name.split('_')
    return ''.join(part.upper() if len(part) <= 3 else part.capitalize() for part in parts)


def build_result_folder(kind: str, strategy_name: str, timestamp: str | None = None) -> str:
    """Create a human-friendly result folder name with kind prefix and readable datetime."""
    ts = timestamp or datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    prefix = 'bt' if kind == 'backtest' else 'opt'
    return f"{prefix}_{ts}_{strategy_name}"


@bp.route('/optimize')
def optimize_page():
    """Optimization configuration and runner page."""
    data_files = list_data_files()
    strategies = list_strategies()
    score_files = list_score_files()
    
    return render_template('optimize.html', data_files=data_files, strategies=strategies, score_files=score_files)


@bp.route('/optimize/get_params/<strategy_name>')
def get_strategy_params(strategy_name):
    """Get parameter ranges for a strategy."""
    try:
        strategy_path = resolve_strategy_path(strategy_name)
        
        spec = importlib.util.spec_from_file_location(strategy_name, strategy_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        strategy_class_name = snake_to_pascal_case(strategy_name)
        strategy_class = getattr(module, strategy_class_name)
        strategy = strategy_class({})
        param_ranges = strategy.get_parameter_ranges()
        
        return jsonify({'parameters': param_ranges})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@bp.route('/optimize/run', methods=['POST'])
def run_optimization():
    """Queue an optimization job for background execution."""
    logger.info("=" * 60)
    logger.info("OPTIMIZATION JOB QUEUED")
    try:
        from .results import _execute_optimization_job
        
        config = request.json
        job_manager = current_app.job_manager
        
        # Create job
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        job_id = f"optimize_{timestamp}_{config['strategy']}"
        job = job_manager.create_job(job_id, 'optimization', config['strategy'])
        logger.info(f"Job ID: {job_id}")
        logger.info(f"Strategy: {config['strategy']}")
        logger.info(f"Data file: {config['data_file']}")
        
        # Start background thread
        thread = threading.Thread(target=_execute_optimization_job, args=(job_id, config), daemon=True)
        thread.start()
        
        logger.info("=" * 60)
        return jsonify({
            'success': True,
            'job_id': job_id,
            'status': 'queued'
        })
    
    except Exception as e:
        logger.exception(f"OPTIMIZATION QUEUE FAILED: {str(e)}")
        logger.error("=" * 60)
        return jsonify({'error': str(e)}), 400

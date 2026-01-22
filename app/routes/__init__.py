"""
Routes package for Flask application.

This package contains blueprint modules for different route categories:
- data.py: Data management (CSV uploads, preview, delete)
- strategies.py: Strategy management (upload, view, templates)
- backtest.py: Backtest execution and management
- optimize.py: Optimization execution and management
- results.py: Results viewing and dashboard
- jobs.py: Background job management
"""

from flask import Blueprint
from .data import bp as data_bp
from .strategies import bp as strategies_bp
from .backtest import bp as backtest_bp
from .optimize import bp as optimize_bp
from .results import bp as results_bp
from .jobs import bp as jobs_bp


def register_blueprints(app):
    """Register all route blueprints with the Flask app."""
    app.register_blueprint(data_bp)
    app.register_blueprint(strategies_bp)
    app.register_blueprint(backtest_bp)
    app.register_blueprint(optimize_bp)
    app.register_blueprint(results_bp)
    app.register_blueprint(jobs_bp)

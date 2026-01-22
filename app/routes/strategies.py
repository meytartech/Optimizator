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


def snake_to_pascal_case(name):
    """Convert snake_case to PascalCase (e.g., mnq_strategy -> MNQStrategy)."""
    parts = name.split('_')
    # Handle special cases like 'mnq' -> 'MNQ'
    return ''.join(part.upper() if len(part) <= 3 else part.capitalize() for part in parts)


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


@bp.route('/strategies')
def strategy_management():
    """Strategy management page."""
    strategies = []
    for strategy_name in list_strategies():
        filename = f"{strategy_name}.py"
        filepath = resolve_strategy_path(strategy_name)
        modified = datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%Y-%m-%d %H:%M')
        
        strategies.append({
            'name': strategy_name,
            'filename': filename,
            'modified': modified
        })
    
    return render_template('strategies.html', strategies=strategies)


@bp.route('/strategies/view/<filename>')
def view_strategy(filename):
    """View strategy code."""
    filepath = resolve_strategy_path(filename[:-3])
    
    if not os.path.exists(filepath):
        return
    
    with open(filepath, 'r') as f:
        code = f.read()
    
    return jsonify({'code': code})


@bp.route('/strategies/upload', methods=['POST'])
def upload_strategy():
    """Upload a new strategy file."""
    from flask import current_app
    config = current_app.config
    
    if 'file' not in request.files:
        return
    
    file = request.files['file']
    if file.filename == '':
        return
    
    if not file.filename.endswith('.py'):
        return
    
    filename = secure_filename(file.filename)
    # Always save uploads to current strategies folder
    filepath = os.path.join(config['STRATEGIES_FOLDER'], filename)
    logger.info(f"Uploading strategy: {filename}")
    file.save(filepath)
    logger.info(f"✓ Strategy uploaded successfully: {filename}")
    
    return jsonify({'success': True, 'filename': filename})


@bp.route('/strategies/template')
def strategy_template_page():
    """Page to generate strategy template."""
    return render_template('strategy_template.html')


@bp.route('/strategies/generate-template', methods=['POST'])
def generate_template():
    """Generate a strategy template file."""
    from flask import current_app
    config = current_app.config
    
    try:
        data = request.json
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        params = data.get('parameters', [])
        
        if not name:
            return
        
        # Convert name to snake_case for filename
        safe_name = name.lower().replace(' ', '_')
        filename = f"{safe_name}.py"
        class_name = snake_to_pascal_case(safe_name)
        
        # Generate parameter initialization and ranges
        param_inits = []
        param_ranges_code = "        return {}"
        if params:
            for param in params:
                pname = param.get('name', '').lower().replace(' ', '_')
                if pname:
                    default = param.get('default', 0)
                    param_inits.append(f"        self.{pname} = self.params.get('{pname}', {default})")
            
            if param_inits:
                ranges = []
                for param in params:
                    pname = param.get('name', '').lower().replace(' ', '_')
                    if pname:
                        min_val = param.get('min', 0)
                        max_val = param.get('max', 100)
                        step = param.get('step', 1)
                        ranges.append(f"            '{pname}': ({min_val}, {max_val}, {step}),")
                param_ranges_code = "        return {\n" + "\n".join(ranges) + "\n        }"
        param_init_code = "\n".join(param_inits) if param_inits else "        # No tunable parameters yet\n        pass"
        
        # Generate template code (import from core.base_strategy)
        template_code = f'''"""
Strategy Template: {name}

Description: {description}
"""

from typing import Any, Dict, List, Optional, Tuple

from core.base_strategy import BaseStrategy, TradeSignal


class {class_name}(BaseStrategy):
    """{name} Strategy
    
    {description}
    """
    
    def setup(self):
        """Initialize strategy parameters for backtests/optimizations."""
        # Get parameters with defaults
{param_init_code}
    
    def generate_signal(self, prices_data: List[Dict[str, Any]], scores_data: Optional[List[Dict[str, Any]]] = None) -> List[TradeSignal]:
        """Generate trading signals for the full selected period.
        
        Args:
            prices_data: List of price bars with timestamp + OHLC/price
            scores_data: Optional score/indicator data from database (timestamp-matched)
        """
        signals: List[TradeSignal] = []
        history: List[Dict[str, Any]] = []
        for bar in prices_data:
            history.append(bar)
            timestamp = bar.get("timestamp", "")
            price = bar.get("close", bar.get("price"))
            if price is None:
                signals.append(TradeSignal(signal=0, entry_price=0.0, timestamp=timestamp))
                continue
            if len(history) < 5:
                signals.append(TradeSignal(signal=0, entry_price=price, timestamp=timestamp))
                continue
            # TODO: Implement your strategy logic here
            # Example: scores lookup by timestamp if provided
            # matched_score = next((s for s in scores_data or [] if s.get("timestamp") == timestamp), None)
            signals.append(TradeSignal(signal=0, entry_price=price, timestamp=timestamp))
        return signals

    def get_parameter_ranges(self) -> Dict[str, Tuple[float, float, float]]:
        """Define parameters for optimization (min, max, step)."""
{param_ranges_code}

    def get_position_size(self, capital: float, price: float) -> int:
        return int(self.params.get('position_size', 1))
    
    def get_info(self) -> Dict[str, Any]:
        """Strategy metadata."""
        return {{
            'name': '{name}',
            'version': '1.0',
            'description': '{description}'
        }}
'''
        
        # Save the template
        filepath = os.path.join(config['STRATEGIES_FOLDER'], filename)
        with open(filepath, 'w') as f:
            f.write(template_code)
        
        return jsonify({
            'success': True,
            'filename': filename,
            'template': template_code,
            'message': f'Strategy template "{name}" created successfully'
        })
    except Exception as e:
        return

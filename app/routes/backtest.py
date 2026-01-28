"""
Backtest routes - backtest configuration, execution, and management.
"""

from flask import Blueprint, request, jsonify, render_template, Response, stream_with_context, current_app
import os
import json
from datetime import datetime
import importlib.util
import logging
import csv
import queue

from core.backtester import GenericBacktester
from core.score_loader import ScoreDataLoader
from core.equity_plotter import EquityPlotter
from .data import list_data_files, get_data_file_path
from .strategies import list_strategies, resolve_strategy_path

logger = logging.getLogger(__name__)
bp = Blueprint('backtest', __name__, url_prefix='')


def snake_to_pascal_case(name):
    """Convert snake_case to PascalCase (e.g., mnq_strategy -> MNQStrategy)."""
    parts = name.split('_')
    return ''.join(part.upper() if len(part) <= 3 else part.capitalize() for part in parts)


def build_result_folder(kind: str, strategy_name: str, timestamp: str | None = None) -> str:
    """Create a human-friendly result folder name with kind prefix and readable datetime."""
    ts = timestamp or datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    prefix = 'bt' if kind == 'backtest' else 'opt'
    return f"{prefix}_{ts}_{strategy_name}"


def get_job_manager():
    """Get job manager from app context."""
    from flask import current_app
    return current_app.job_manager


@bp.route('/backtest')
def backtest_page():
    """Backtest configuration and runner page."""
    data_files = list_data_files()
    strategies = list_strategies()
    
    return render_template('backtest.html', data_files=data_files, strategies=strategies)


@bp.route('/backtest/prepare', methods=['POST'])
def prepare_live_backtest():
    """Prepare a live backtest run: ensure only one temp result exists.

    - Clears existing temp_results dir contents
    - Creates a new temp folder named with strategy + timestamp
    - Saves the provided config.json into that folder
    - Returns the temp_result_id to redirect to /results/temp/<id>
    """
    try:
        raw_data = request.get_json(force=True)
        logger.info(f"Received prepare request: {raw_data}")
        
        config = raw_data or {}
        
        # Sanitize config: remove None/undefined values and ensure JSON serializable
        sanitized_config = {}
        for key, value in config.items():
            if value is None:
                continue
            try:
                json.dumps(value)
                sanitized_config[key] = value
            except (TypeError, ValueError):
                sanitized_config[key] = str(value)
        
        logger.info(f"Sanitized config: {sanitized_config}")
        strategy_name = sanitized_config.get('strategy', 'strategy')

        # Keep only one temp result: clear all existing
        temp_results_folder = current_app.config['TEMP_RESULTS_FOLDER']
        for name in os.listdir(temp_results_folder):
            path = os.path.join(temp_results_folder, name)
            if os.path.isdir(path):
                import shutil
                shutil.rmtree(path, ignore_errors=True)

        # Create a fresh temp result folder
        folder_name = build_result_folder('backtest', strategy_name)
        temp_dir = os.path.join(temp_results_folder, folder_name)
        os.makedirs(temp_dir, exist_ok=True)

        # Store config in results.json (will be updated when backtest completes)
        initial_results = {'config': sanitized_config, 'status': 'pending'}
        with open(os.path.join(temp_dir, 'results.json'), 'w', encoding='utf-8') as f:
            json.dump(initial_results, f, indent=2)

        return jsonify({'success': True, 'temp_result_id': folder_name})
    except Exception as e:
        logger.exception(f"Failed to prepare live backtest: {e}")
        return jsonify({'error': str(e)}), 400


@bp.route('/backtest/execute/<temp_result_id>', methods=['POST'])
def execute_live_backtest(temp_result_id):
    """Execute a live backtest for a prepared temp_result_id, streaming logs (SSE).

    Reuses the same temp folder (no new temp id), so the results page can stay
    on the same URL while logs stream and metrics become available.
    """
    try:
        temp_dir = os.path.join(current_app.config['TEMP_RESULTS_FOLDER'], temp_result_id)
        results_path = os.path.join(temp_dir, 'results.json')
        if not os.path.exists(results_path):
            return jsonify({'error': 'Temp result not found'}), 404

        with open(results_path, 'r', encoding='utf-8') as f:
            initial_data = json.load(f)
            config = initial_data.get('config', {})

        def generate():
            """Generator function that yields log messages and final result."""
            log_queue = queue.Queue()
            
            class QueueHandler(logging.Handler):
                def emit(self, record):
                    log_msg = self.format(record)
                    log_queue.put(log_msg)
            
            queue_handler = QueueHandler()
            queue_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))
            logger.addHandler(queue_handler)
            
            try:
                yield f"data: {json.dumps({'type': 'log', 'message': '=== Starting Backtest ==='})}\n\n"
                
                logger.info("=" * 60)
                logger.info("BACKTEST STARTED (LIVE EXECUTION)")
                logger.info(f"Data file: {config['data_file']}")
                logger.info(f"Strategy: {config['strategy']}")
                logger.info(f"Initial capital: ${config.get('initial_capital', 100000):,.2f}")
                
                while not log_queue.empty():
                    yield f"data: {json.dumps({'type': 'log', 'message': log_queue.get()})}\n\n"
                
                # Load price data (detect if combined .db or CSV)
                data_file = config['data_file']
                data_path = get_data_file_path(data_file)
                logger.info(f"Loading price data from: {data_path}")
                
                # Load combined .db format (OHLC + scores together)
                if not data_path.lower().endswith('.db') or not ScoreDataLoader.is_combined_database(data_path):
                    logger.error(f"Invalid data file: {data_file}. Only combined .db files (with OHLC + scores) are supported.")
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Invalid data file format. Expected combined .db file with OHLC and score data.'})}\n\n"
                    raise ValueError("Only combined .db files are supported")
                
                logger.info("Loading combined .db format (OHLC + scores together)")
                try:
                    data = ScoreDataLoader.load_combined_db(data_path)
                    logger.info(f"Combined data loaded: {len(data)} unified bars with embedded OHLC+scores")
                except Exception as e:
                    logger.error(f"Failed to load combined .db: {e}")
                    yield f"data: {json.dumps({'type': 'error', 'message': f'Failed to load data: {str(e)}'})}\n\n"
                    raise
                
                while not log_queue.empty():
                    yield f"data: {json.dumps({'type': 'log', 'message': log_queue.get()})}\n\n"
                
                # Load strategy
                strategy_name = config['strategy']
                strategy_path = resolve_strategy_path(strategy_name)
                logger.info(f"Loading strategy from: {strategy_path}")
                
                spec = importlib.util.spec_from_file_location(strategy_name, strategy_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                strategy_class_name = snake_to_pascal_case(strategy_name)
                strategy_class = getattr(module, strategy_class_name)
                
                params = config.get('parameters', {})
                params['point_value'] = config.get('point_value', 1.0)
                params['tick_size'] = config.get('tick_size', 0.01)
                params['instrument_type'] = config.get('instrument_type', 'stock')
                params['position_size'] = config.get('position_size', 1)
                
                strategy = strategy_class(params)
                
                # Capture strategy setup parameters
                strategy_setup_params = {}
                exclude_attrs = {'name', 'params', 'point_value', 'tick_size', 'instrument_type', 'generate_signal', 'setup', 'get_parameter_ranges'}
                for attr_name in dir(strategy):
                    if attr_name.startswith('_') or attr_name in exclude_attrs:
                        continue
                    try:
                        attr_value = getattr(strategy, attr_name)
                        if callable(attr_value):
                            continue
                        if isinstance(attr_value, (int, float, str, bool)):
                            strategy_setup_params[attr_name] = attr_value
                        elif isinstance(attr_value, (list, dict)) and len(str(attr_value)) < 200:
                            try:
                                strategy_setup_params[attr_name] = attr_value
                            except:
                                pass
                    except:
                        pass
                
                logger.info(f"Running backtest with {len(data)} unified bars (OHLCV + scores)")
                
                while not log_queue.empty():
                    yield f"data: {json.dumps({'type': 'log', 'message': log_queue.get()})}\n\n"
                
                backtester = GenericBacktester(
                    initial_capital=config.get('initial_capital', 100000),
                    commission_per_trade=config.get('commission', 0),
                    slippage_ticks=config.get('slippage_ticks', 0),
                    max_bars_back=config.get('max_bars_back', 100),
                    verbose=False
                )
                
                result = backtester.run(strategy, data)
                
                logger.info("Backtest completed successfully!")
                logger.info(f"Win Rate: {result.win_rate:.2f}%")
                logger.info(f"Total Trades: {result.total_trades}")
                logger.info(f"Average R/R: {result.avg_rr:.2f}%")
                
                while not log_queue.empty():
                    yield f"data: {json.dumps({'type': 'log', 'message': log_queue.get()})}\n\n"
                
                # Create results data structure
                results_data = {
                    'data_file': config.get('data_file', ''),  # Store .db path for later loading
                    'parameters': config.get('parameters', {}),
                    'strategy_setup_params': strategy_setup_params,
                    'point_value': config.get('point_value', 1.0),
                    'tick_size': config.get('tick_size', 0.01),
                    'instrument_type': config.get('instrument_type', 'stock'),
                    'position_size': config.get('position_size', 1),
                    'initial_capital': config.get('initial_capital', 100000),
                    'commission': config.get('commission', 0),
                    'slippage_ticks': config.get('slippage_ticks', 0),
                    'strategy': strategy_name,
                    'data_file': config['data_file'],
                    'config': config
                }
                
                # Add backtest metrics
                result_dict = result.to_dict()
                results_data.update(result_dict)
                
                # Save to temporary location
                with open(os.path.join(temp_dir, 'results.json'), 'w', encoding='utf-8') as f:
                    json.dump(results_data, f, indent=2, default=str)
                
                # Note: Price and score data not saved to reduce storage
                # Load from original .db file when needed (path stored in results.json)
                
                # Save trades CSV
                try:
                    trades_csv_path = os.path.join(temp_dir, 'trades.csv')
                    headers = ['entry_time', 'exit_time', 'entry_price', 'exit_price', 'direction', 'quantity', 'pnl', 'pnl_percent', 'is_win', 'exit_reason', 'stop_loss', 'metadata']
                    with open(trades_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                        writer = csv.writer(csvfile)
                        writer.writerow(headers)
                        for t in getattr(result, 'trades', []) or []:
                            metadata_str = ''
                            try:
                                metadata_str = json.dumps(getattr(t, 'metadata', {}) or {})
                            except Exception:
                                metadata_str = str(getattr(t, 'metadata', {}) or {})
                            writer.writerow([
                                getattr(t, 'entry_time', ''),
                                getattr(t, 'exit_time', ''),
                                getattr(t, 'entry_price', ''),
                                getattr(t, 'exit_price', ''),
                                getattr(t, 'direction', ''),
                                getattr(t, 'quantity', ''),
                                getattr(t, 'pnl', ''),
                                getattr(t, 'pnl_percent', ''),
                                getattr(t, 'is_win', ''),
                                getattr(t, 'exit_reason', ''),
                                getattr(t, 'stop_loss', ''),
                                metadata_str
                            ])
                    logger.info(f"Temporary trades CSV saved")
                except Exception as csv_err:
                    logger.error(f"Failed to save trades CSV: {csv_err}")
                
                # Save strategy code (config data is already in results.json)
                with open(strategy_path, 'r', encoding='utf-8') as f:
                    strategy_code = f.read()
                with open(os.path.join(temp_dir, 'strategy_code.txt'), 'w', encoding='utf-8') as f:
                    f.write(strategy_code)
                
                # Generate equity curve
                try:
                    equity_chart_path = os.path.join(temp_dir, 'equity_curve.png')
                    EquityPlotter.plot_enhanced_results(
                        result.equity_curve,
                        result.trades,
                        result.session_stats,
                        result.hourly_stats,
                        equity_chart_path,
                        title=f"{strategy_name} - Backtest Results",
                        initial_capital=config.get('initial_capital', 100000)
                    )
                    logger.info(f"Temporary equity curve saved")
                except Exception as plot_err:
                    logger.error(f"Failed to generate equity chart: {plot_err}")
                
                logger.info("=" * 60)
                
                while not log_queue.empty():
                    yield f"data: {json.dumps({'type': 'log', 'message': log_queue.get()})}\n\n"
                
                # Send completion
                yield f"data: {json.dumps({'type': 'complete', 'temp_result_id': temp_result_id})}\n\n"
                
            except Exception as e:
                logger.exception(f"Backtest failed: {str(e)}")
                while not log_queue.empty():
                    yield f"data: {json.dumps({'type': 'log', 'message': log_queue.get()})}\n\n"
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            
            finally:
                logger.removeHandler(queue_handler)
        
        return Response(stream_with_context(generate()), mimetype='text/event-stream')
    except Exception as e:
        logger.exception(f"Failed to execute live backtest: {e}")
        return jsonify({'error': str(e)}), 400


@bp.route('/backtest/rerun/<temp_result_id>', methods=['POST'])
def rerun_backtest(temp_result_id):
    """Rerun a backtest with the same parameters in the SAME temp folder."""
    try:
        temp_dir = os.path.join(current_app.config['TEMP_RESULTS_FOLDER'], temp_result_id)
        
        if not os.path.exists(temp_dir):
            return jsonify({'error': 'Temp result not found'}), 404
        
        # Load config from results.json
        results_path = os.path.join(temp_dir, 'results.json')
        with open(results_path, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
            config = existing_data.get('config', {})
        
        # Clean up old results before rerunning (keep results.json with config)
        import shutil
        for filename in os.listdir(temp_dir):
            if filename not in ['results.json']:  # Keep results.json for config
                filepath = os.path.join(temp_dir, filename)
                if os.path.isdir(filepath):
                    shutil.rmtree(filepath, ignore_errors=True)
                else:
                    try:
                        os.remove(filepath)
                    except:
                        pass
        
        # Execute the backtest using the same temp_result_id
        # Call the generate() function from execute_live_backtest directly
        response = execute_live_backtest(temp_result_id)
        return response
    
    except Exception as e:
        logger.exception(f"Failed to rerun backtest: {str(e)}")
        return jsonify({'error': str(e)}), 400

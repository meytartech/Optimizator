"""
Results and dashboard routes - viewing backtests, optimizations, and managing results.
Also contains background job worker functions.
"""

from flask import Blueprint, render_template, jsonify, request, current_app, send_file
import os
import json
from datetime import datetime
import pytz
import logging
import shutil
import importlib.util
import csv
import threading

from core.data_loader import CSVDataLoader
from core.backtester import GenericBacktester
from core.score_loader import ScoreDataLoader
from core.optimizer import StrategyOptimizer
from core.equity_plotter import EquityPlotter
from .data import get_data_file_path, list_data_files
from .strategies import resolve_strategy_path

logger = logging.getLogger(__name__)
bp = Blueprint('results', __name__, url_prefix='')


def snake_to_pascal_case(name):
    """Convert snake_case to PascalCase (e.g., mnq_strategy -> MNQStrategy)."""
    parts = name.split('_')
    return ''.join(part.upper() if len(part) <= 3 else part.capitalize() for part in parts)


def build_result_folder(kind: str, strategy_name: str, timestamp: str | None = None) -> str:
    """Create a human-friendly result folder name with kind prefix and readable datetime."""
    ts = timestamp or datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    prefix = 'bt' if kind == 'backtest' else 'opt'
    return f"{prefix}_{ts}_{strategy_name}"


def _format_result_datetime(date_part: str, time_part: str) -> str:
    """Return readable datetime from folder name parts (handles legacy names)."""
    try:
        if len(date_part) == 8 and date_part.isdigit():
            date_fmt = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:]}"
        else:
            date_fmt = date_part.replace('-', '/')

        if time_part:
            if len(time_part) in (4, 6) and time_part.replace('-', '').isdigit():
                time_str = time_part.replace('-', ':')
                return f"{date_fmt} {time_str}"
            else:
                return f"{date_fmt} {time_part}"
            return f"{date_fmt} {time_fmt}"
        return date_fmt
    except Exception:
        return f"{date_part} {time_part}".strip()


def parse_result_metadata(dirname: str, default_strategy: str = '') -> dict:
    """Extract human-readable date and strategy from a result folder name."""
    parts = dirname.split('_')
    if parts and parts[0] in {'bt', 'opt'}:
        parts = parts[1:]

    date_part = parts[0] if parts else ''
    time_part = parts[1] if len(parts) > 1 else ''
    strategy_part = '_'.join(parts[2:]) if len(parts) > 2 else default_strategy

    return {
        'id': dirname,
        'date': _format_result_datetime(date_part, time_part),
        'strategy': strategy_part or default_strategy
    }


@bp.route('/')
def results_page():
    """Results page (default homepage): render shell, data loads asynchronously via API."""
    return render_template('results.html')


@bp.route('/results/compare')
def compare_backtests():
    """Compare multiple backtest results side-by-side."""
    ids = request.args.get('ids', '').split(',')
    ids = [id.strip() for id in ids if id.strip()]
    
    if len(ids) < 2:
        return "Please select at least 2 backtests to compare", 400
    
    config = current_app.config
    backtest_dir = os.path.join(config['RESULTS_FOLDER'], 'backtests')
    
    comparisons = []
    for result_id in ids:
        dirpath = os.path.join(backtest_dir, result_id)
        results_file = os.path.join(dirpath, 'results.json')
        config_file = os.path.join(dirpath, 'config.json')
        
        if not os.path.exists(results_file):
            continue
        
        try:
            with open(results_file, 'r') as f:
                results = json.load(f)
            
            config_data = {}
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    config_data = json.load(f)
            
            meta = parse_result_metadata(result_id)
            
            comparisons.append({
                'id': result_id,
                'date': meta['date'],
                'strategy': meta['strategy'],
                'results': results,
                'config': config_data,
                'has_equity': os.path.exists(os.path.join(dirpath, 'equity_curve.png'))
            })
        except Exception as e:
            logger.error(f"Failed to load backtest {result_id}: {e}")
            continue
    
    if len(comparisons) < 2:
        return "Unable to load enough backtests for comparison", 400
    
    return render_template('compare.html', comparisons=comparisons)


@bp.route('/api/results')
def api_results():
    """Return recent backtests and optimizations as JSON, with pagination."""
    limit = request.args.get('limit', default=50, type=int)
    bt_offset = request.args.get('bt_offset', default=0, type=int)
    opt_offset = request.args.get('opt_offset', default=0, type=int)
    only = request.args.get('only', default=None, type=str)

    summaries = _collect_results_summary(limit, bt_offset, opt_offset)
    if only == 'backtests':
        return jsonify({'backtests': summaries['backtests']})
    if only == 'optimizations':
        return jsonify({'optimizations': summaries['optimizations']})
    return jsonify(summaries)


def _collect_results_summary(max_results: int = 50, bt_offset: int = 0, opt_offset: int = 0):
    """Collect recent backtest and optimization summaries."""
    config = current_app.config
    summaries = {'backtests': [], 'optimizations': []}

    # Backtests
    backtest_dir = os.path.join(config['RESULTS_FOLDER'], 'backtests')
    if os.path.exists(backtest_dir):
        backtest_dirs = [(d, os.path.getmtime(os.path.join(backtest_dir, d)))
                         for d in os.listdir(backtest_dir)
                         if os.path.isdir(os.path.join(backtest_dir, d))]
        backtest_dirs.sort(key=lambda x: x[1], reverse=True)

        for dirname, _ in backtest_dirs[bt_offset:bt_offset + max_results]:
            dirpath = os.path.join(backtest_dir, dirname)
            results_file = os.path.join(dirpath, 'results.json')
            if os.path.exists(results_file):
                try:
                    with open(results_file, 'r') as f:
                        data = json.load(f)
                    meta = parse_result_metadata(dirname)
                    summaries['backtests'].append({
                        'id': dirname,
                        'date': meta['date'],
                        'strategy': meta['strategy'],
                        'win_rate': data.get('win_rate', 0),
                        'avg_rr': data.get('avg_rr', 0),
                        'description': data.get('description', '')
                    })
                except Exception:
                    pass

    # Optimizations
    opt_dir = os.path.join(config['RESULTS_FOLDER'], 'optimizations')
    if os.path.exists(opt_dir):
        opt_dirs = [(d, os.path.getmtime(os.path.join(opt_dir, d)))
                    for d in os.listdir(opt_dir)
                    if os.path.isdir(os.path.join(opt_dir, d))]
        opt_dirs.sort(key=lambda x: x[1], reverse=True)

        for dirname, _ in opt_dirs[opt_offset:opt_offset + max_results]:
            dirpath = os.path.join(opt_dir, dirname)
            summary_file = os.path.join(dirpath, 'optimization_results_summary.json')
            results_file = os.path.join(dirpath, 'optimization_results.json')
            
            data = None
            if os.path.exists(summary_file):
                try:
                    with open(summary_file, 'r') as f:
                        data = json.load(f)
                except Exception:
                    pass
            
            if not data and os.path.exists(results_file):
                try:
                    with open(results_file, 'r') as f:
                        data = json.load(f)
                except Exception:
                    pass
            
            if data:
                meta = parse_result_metadata(dirname)
                top_result = data.get('top_results', [{}])[0] if data.get('top_results') else {}
                summaries['optimizations'].append({
                    'id': dirname,
                    'date': meta['date'],
                    'strategy': meta['strategy'],
                    'best_metric': top_result.get('metrics', {}).get(data.get('metric', 'total_return'), 0),
                    'total_runs': len(data.get('all_results', []))
                })

    return summaries


@bp.route('/results/temp/<temp_result_id>')
def view_temp_backtest_result(temp_result_id):
    """View temporary (unsaved) backtest results."""
    config = current_app.config
    result_dir = os.path.join(config['TEMP_RESULTS_FOLDER'], temp_result_id)
    results_file = os.path.join(result_dir, 'results.json')
    config_file = os.path.join(result_dir, 'config.json')

    results = {}
    has_results = False
    if os.path.exists(results_file):
        with open(results_file, 'r') as f:
            results = json.load(f)
        has_results = True
    else:
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as cf:
                    cfg = json.load(cf)
                results = {
                    'strategy': cfg.get('strategy', 'unknown'),
                    'data_file': cfg.get('data_file', ''),
                    'parameters': cfg.get('parameters', {}),
                    'initial_capital': cfg.get('initial_capital', 100000),
                    'commission': cfg.get('commission', 0),
                    'slippage_ticks': cfg.get('slippage_ticks', 0),
                    'instrument_type': cfg.get('instrument_type', 'stock'),
                    'point_value': cfg.get('point_value', 1.0),
                    'tick_size': cfg.get('tick_size', 0.01),
                    'position_size': cfg.get('position_size', 1),
                    'initial_capital': cfg.get('initial_capital', 100000),
                    'final_equity': cfg.get('initial_capital', 100000),
                    'total_return': 0.0,
                    'win_rate': 0.0,
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'avg_win': 0.0,
                    'avg_loss': 0.0,
                    'avg_rr': 0.0,
                    'profit_factor': 0.0,
                    'sharpe_ratio': 0.0,
                    'max_drawdown': 0.0,
                    'max_drawdown_points': 0.0,
                    'realized_points': 0.0,
                    'total_commissions': 0.0,
                    'max_consecutive_wins': 0,
                    'max_consecutive_losses': 0,
                    'unique_entries': 0,
                    'trades': [],
                    'equity_curve': [],
                    'session_stats': {},
                    'exit_reason_stats': {},
                }
            except Exception:
                results = {
                    'initial_capital': 100000,
                    'final_equity': 100000,
                    'total_return': 0.0,
                    'win_rate': 0.0,
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'avg_win': 0.0,
                    'avg_loss': 0.0,
                    'avg_rr': 0.0,
                    'profit_factor': 0.0,
                    'sharpe_ratio': 0.0,
                    'max_drawdown': 0.0,
                    'max_drawdown_points': 0.0,
                    'realized_points': 0.0,
                    'total_commissions': 0.0,
                    'max_consecutive_wins': 0,
                    'max_consecutive_losses': 0,
                    'unique_entries': 0,
                    'trades': [],
                    'equity_curve': [],
                    'session_stats': {},
                    'exit_reason_stats': {},
                }
        else:
            results = {
                'initial_capital': 100000,
                'final_equity': 100000,
                'total_return': 0.0,
                'win_rate': 0.0,
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'avg_rr': 0.0,
                'profit_factor': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'max_drawdown_points': 0.0,
                'realized_points': 0.0,
                'total_commissions': 0.0,
                'max_consecutive_wins': 0,
                'max_consecutive_losses': 0,
                'unique_entries': 0,
                'trades': [],
                'equity_curve': [],
                'session_stats': {},
                'exit_reason_stats': {},
            }
    
    if 'exit_reason_stats' not in results and 'trades' in results:
        exit_reason_stats = {}
        for trade in results['trades']:
            reason = trade.get('exit_reason', 'UNKNOWN')
            exit_reason_stats[reason] = exit_reason_stats.get(reason, 0) + 1
        results['exit_reason_stats'] = exit_reason_stats

    meta = parse_result_metadata(temp_result_id, results.get('strategy_name', ''))
    display_title = f"{meta['strategy']} — {meta['date']}" if meta.get('date') else meta['strategy']

    return render_template(
        'backtest_detail.html',
        result_id=temp_result_id,
        results=results,
        display_title=display_title,
        unsaved=True,
        temp_result_id=temp_result_id,
        has_results=has_results
    )


@bp.route('/results/backtest/<result_id>/trade/<int:trade_index>')
def get_trade_details(result_id, trade_index):
    """Get details for a specific trade including price window."""
    config = current_app.config
    
    # Try saved results first
    result_dir = os.path.join(config['RESULTS_FOLDER'], 'backtests', result_id)
    results_file = os.path.join(result_dir, 'results.json')
    
    # If not found in saved, try temp results
    if not os.path.exists(results_file):
        result_dir = os.path.join(config['TEMP_RESULTS_FOLDER'], result_id)
        results_file = os.path.join(result_dir, 'results.json')
    
    if not os.path.exists(results_file):
        return jsonify({'success': False, 'error': 'Results not found'}), 404
    
    try:
        with open(results_file, 'r') as f:
            results = json.load(f)
        
        trades = results.get('trades', [])
        if trade_index < 0 or trade_index >= len(trades):
            return jsonify({'success': False, 'error': 'Trade not found'}), 404
        
        trade = trades[trade_index]
        
        # Load all price data to find indices
        all_prices = []
        entry_index = 0
        exit_index = 0
        
        prices_file = os.path.join(result_dir, 'prices_data.json')
        if os.path.exists(prices_file):
            try:
                with open(prices_file, 'r') as f:
                    all_prices = json.load(f)
                logger.info(f"Loaded prices from prices_data.json: {len(all_prices)} bars")
            except Exception as e:
                logger.warning(f"Failed to load prices_data.json: {e}")
        
        # Fallback: load from CSV if prices_data.json doesn't exist
        if not all_prices:
            data_file = results.get('data_file', '')
            if data_file:
                csv_paths = [
                    os.path.join(current_app.config['UPLOAD_FOLDER'], data_file),
                    os.path.join(os.path.dirname(os.path.dirname(current_app.config['UPLOAD_FOLDER'])), 'data', 'db', data_file),
                ]
                
                for csv_path in csv_paths:
                    if os.path.exists(csv_path):
                        try:
                            from core.data_loader import CSVDataLoader
                            all_prices = CSVDataLoader.load_csv(csv_path)
                            logger.info(f"Loaded prices from CSV fallback: {len(all_prices)} bars")
                            break
                        except Exception as e:
                            logger.warning(f"Failed to load CSV fallback from {csv_path}: {e}")
        
        if all_prices:
            # Find entry/exit indices in prices data
            entry_ts = trade.get('entry_timestamp', trade.get('entry_time', ''))
            exit_ts = trade.get('exit_timestamp', trade.get('exit_time', ''))
            
            for idx, bar in enumerate(all_prices):
                bar_ts = bar.get('timestamp', '')
                if bar_ts == entry_ts:
                    entry_index = idx
                if bar_ts == exit_ts:
                    exit_index = idx
            
            # Return only a window of prices (entry - 20 bars to exit + 20 bars)
            window_start = max(0, entry_index - 20)
            window_end = min(len(all_prices), exit_index + 21)
            prices_data = all_prices[window_start:window_end]
            
            # Adjust indices relative to the window
            entry_index = entry_index - window_start
            exit_index = exit_index - window_start
        else:
            prices_data = []
        
        # Load scores data if available
        scores_data = {}
        scores_file = os.path.join(result_dir, 'scores_data.json')
        if os.path.exists(scores_file):
            try:
                with open(scores_file, 'r') as f:
                    loaded_scores = json.load(f)
                
                # Ensure scores_data is a dict with timeframe keys
                if isinstance(loaded_scores, dict):
                    scores_data = loaded_scores
                elif isinstance(loaded_scores, list) and loaded_scores:
                    # Convert list format to dict format by looking for timeframe info
                    # Try to organize by timeframe if available
                    if all('timestamp' in item and 'score' in item for item in loaded_scores):
                        # Default to '1m' if no timeframe specified
                        scores_data = {'1m': loaded_scores}
                    else:
                        scores_data = {}
                
                # Filter scores to only window timeframe
                if scores_data and prices_data:
                    window_start_ts = prices_data[0].get('timestamp') if prices_data else None
                    window_end_ts = prices_data[-1].get('timestamp') if prices_data else None
                    
                    filtered_scores = {}
                    for timeframe, scores_list in scores_data.items():
                        if isinstance(scores_list, list):
                            # Filter to only scores within the price window
                            filtered = [
                                s for s in scores_list
                                if window_start_ts and window_end_ts and 
                                   window_start_ts <= s.get('timestamp', '') <= window_end_ts
                            ]
                            if filtered:
                                filtered_scores[timeframe] = filtered
                    
                    scores_data = filtered_scores if filtered_scores else {}
                
                # if scores_data:
                #     logger.info(f"Loaded scores: {list(scores_data.keys())}")
                
            except Exception as e:
                logger.warning(f"Failed to load scores_data.json: {e}")
        
        return jsonify({
            'success': True,
            'trade': trade,
            'prices_data': prices_data,
            'scores_data': scores_data,
            'entry_index': entry_index,
            'exit_index': exit_index
        })
    
    except Exception as e:
        logger.exception(f"Failed to get trade details: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/results/backtest/<result_id>/description', methods=['POST'])
def save_backtest_description(result_id):
    """Save description to backtest results.json"""
    config = current_app.config
    
    try:
        data = request.get_json()
        description = data.get('description', 'No description')
        
        # Try saved results first
        result_dir = os.path.join(config['RESULTS_FOLDER'], 'backtests', result_id)
        results_file = os.path.join(result_dir, 'results.json')
        
        # If not found in saved, try temp results
        if not os.path.exists(results_file):
            result_dir = os.path.join(config['TEMP_RESULTS_FOLDER'], result_id)
            results_file = os.path.join(result_dir, 'results.json')
        
        if not os.path.exists(results_file):
            return jsonify({'success': False, 'error': 'Results file not found'}), 404
        
        # Load, update, and save results.json
        with open(results_file, 'r') as f:
            results = json.load(f)
        
        results['description'] = description
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        return jsonify({'success': True, 'description': description})
    
    except Exception as e:
        logger.exception(f"Failed to save description: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/results/backtest/<result_id>')
def view_backtest_result(result_id):
    """View detailed backtest results."""
    config = current_app.config
    result_dir = os.path.join(config['RESULTS_FOLDER'], 'backtests', result_id)
    results_file = os.path.join(result_dir, 'results.json')
    
    if not os.path.exists(results_file):
        return "Results not found", 404
    
    with open(results_file, 'r') as f:
        results = json.load(f)
    
    if 'exit_reason_stats' not in results and 'trades' in results:
        exit_reason_stats = {}
        for trade in results['trades']:
            reason = trade.get('exit_reason', 'UNKNOWN')
            exit_reason_stats[reason] = exit_reason_stats.get(reason, 0) + 1
        results['exit_reason_stats'] = exit_reason_stats

    meta = parse_result_metadata(result_id, results.get('strategy_name', ''))
    display_title = f"{meta['strategy']} — {meta['date']}" if meta.get('date') else meta['strategy']

    return render_template('backtest_detail.html', result_id=result_id, results=results, display_title=display_title)


@bp.route('/results/backtest/<result_id>/equity_curve.png')
def serve_equity_curve(result_id):
    """Serve equity curve image for a backtest result."""
    config = current_app.config
    result_dir = os.path.join(config['RESULTS_FOLDER'], 'backtests', result_id)
    equity_path = os.path.join(result_dir, 'equity_curve.png')
    
    if not os.path.exists(equity_path):
        return "Equity curve not found", 404
    
    return send_file(equity_path, mimetype='image/png')


@bp.route('/results/save/<temp_result_id>', methods=['POST'])
def save_temp_backtest(temp_result_id):
    """Save temporary backtest results to permanent storage."""
    try:
        config = current_app.config
        temp_dir = os.path.join(config['TEMP_RESULTS_FOLDER'], temp_result_id)
        
        if not os.path.exists(temp_dir):
            return jsonify({'error': 'Temporary results not found'}), 404
        
        with open(os.path.join(temp_dir, 'results.json'), 'r') as f:
            results = json.load(f)
        
        strategy_name = results.get('strategy', 'unknown')
        folder_name = build_result_folder('backtest', strategy_name)
        result_dir = os.path.join(config['RESULTS_FOLDER'], 'backtests', folder_name)
        os.makedirs(result_dir, exist_ok=True)
        
        for filename in os.listdir(temp_dir):
            src = os.path.join(temp_dir, filename)
            dst = os.path.join(result_dir, filename)
            if os.path.isfile(src):
                shutil.copy2(src, dst)
            elif os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
        
        logger.info(f"Saved backtest from temp {temp_result_id} to {folder_name}")
        
        return jsonify({'success': True, 'result_id': folder_name})
    
    except Exception as e:
        logger.exception(f"Failed to save backtest: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/results/backtest/delete/<result_id>', methods=['POST'])
def delete_backtest_result(result_id):
    """Delete a backtest result folder safely."""
    try:
        config = current_app.config
        base_dir = os.path.join(config['RESULTS_FOLDER'], 'backtests')
        target_dir = os.path.join(base_dir, result_id)

        if os.path.commonpath([os.path.abspath(target_dir), os.path.abspath(base_dir)]) != os.path.abspath(base_dir):
            return jsonify({'error': 'Invalid path'}), 400

        if not os.path.exists(target_dir):
            return jsonify({'error': 'Not found'}), 404

        shutil.rmtree(target_dir)
        logger.info(f"Deleted backtest result: {result_id}")
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f"DELETE BACKTEST FAILED: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/results/optimization/<result_id>')
def view_optimization_result(result_id):
    """View detailed optimization results plus top backtest runs."""
    config = current_app.config
    result_dir = os.path.join(config['RESULTS_FOLDER'], 'optimizations', result_id)
    
    summary_file = os.path.join(result_dir, 'optimization_results_summary.json')
    results_file = os.path.join(result_dir, 'optimization_results.json')
    
    results = None
    if os.path.exists(summary_file):
        try:
            with open(summary_file, 'r') as f:
                results = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    # If we loaded the summary but critical fields are missing, fall back to the full results file
    # Critical fields for charts: all_results, top_results, best_metrics, best_parameters
    needs_full = False
    if results:
        if not results.get('all_results') or not results.get('top_results'):
            needs_full = True
        if not results.get('best_metrics') or not results.get('best_parameters'):
            needs_full = True
    
    if not results or needs_full:
        if not os.path.exists(results_file):
            return "Results not found", 404
        
        try:
            with open(results_file, 'r') as f:
                full_results = json.load(f)
                # If we previously loaded a summary, merge missing fields from full_results
                if results:
                    for key, val in full_results.items():
                        if key not in results or results.get(key) in (None, [], {}):
                            results[key] = val
                else:
                    results = full_results
        except (json.JSONDecodeError, IOError) as e:
            return f"Failed to load results: {str(e)}", 500

    # Build top_runs list from top_run_folders data
    top_runs = []
    recorded_runs = results.get('top_run_folders', []) or []
    
    # Load equity curves from backtest results
    backtests_dir = os.path.join(result_dir, 'backtests')
    
    for run_info in recorded_runs:
        run_entry = {
            'rank': run_info.get('rank'),
            'folder': run_info.get('folder'),
            'parameters': run_info.get('parameters', {}),
            'metrics': run_info.get('metrics', {}),
            'url': f"/results/optimization/{result_id}/rank/{run_info.get('folder', '')}",
            'equity_curve': []  # Default empty
        }
        
        # Try to load equity curve from backtest results.json
        if os.path.exists(backtests_dir):
            backtest_results_file = os.path.join(backtests_dir, run_info.get('folder', ''), 'results.json')
            if os.path.exists(backtest_results_file):
                try:
                    with open(backtest_results_file, 'r') as f:
                        backtest_data = json.load(f)
                        run_entry['equity_curve'] = backtest_data.get('equity_curve', [])
                except (json.JSONDecodeError, IOError):
                    pass  # Use empty list if load fails
        
        top_runs.append(run_entry)

    meta = parse_result_metadata(result_id, results.get('strategy_name', ''))
    display_title = f"{meta['strategy']} — {meta['date']}" if meta.get('date') else meta['strategy']

    return render_template('optimization_detail.html', result_id=result_id, results=results, top_runs=top_runs, display_title=display_title)


@bp.route('/results/optimization/<result_id>/rank/<rank_folder>')
def view_optimization_rank_backtest(result_id, rank_folder):
    """View a specific top-run backtest stored inside an optimization result."""
    config = current_app.config
    base_dir = os.path.join(config['RESULTS_FOLDER'], 'optimizations', result_id)
    # Rank backtests are stored in backtests/ subdirectory
    target_dir = os.path.join(base_dir, 'backtests', rank_folder)

    if os.path.commonpath([os.path.abspath(target_dir), os.path.abspath(base_dir)]) != os.path.abspath(base_dir):
        return "Invalid path", 400
    
    results_file = os.path.join(target_dir, 'results.json')
    if not os.path.exists(results_file):
        return "Results not found", 404
    
    with open(results_file, 'r') as f:
        results = json.load(f)
    
    # Ensure all required metrics exist (fallback for older result files)
    required_metrics = {
        'initial_capital': 100000,
        'final_equity': results.get('final_equity', results.get('initial_capital', 100000)),
        'total_return': 0.0,
        'win_rate': 0.0,
        'total_trades': 0,
        'winning_trades': 0,
        'losing_trades': 0,
        'avg_win': 0.0,
        'avg_loss': 0.0,
        'avg_rr': 0.0,
        'profit_factor': 0.0,
        'sharpe_ratio': 0.0,
        'max_drawdown': 0.0,
        'max_drawdown_points': 0.0,
        'realized_points': 0.0,
        'total_commissions': 0.0,
        'max_consecutive_wins': 0,
        'max_consecutive_losses': 0,
        'unique_entries': 0,
    }
    for key, default_value in required_metrics.items():
        if key not in results:
            results[key] = default_value

    if 'exit_reason_stats' not in results and 'trades' in results:
        exit_reason_stats = {}
        for trade in results['trades']:
            reason = trade.get('exit_reason', 'UNKNOWN')
            exit_reason_stats[reason] = exit_reason_stats.get(reason, 0) + 1
        results['exit_reason_stats'] = exit_reason_stats

    display_id = f"{result_id}/{rank_folder}"
    return render_template('backtest_detail.html', result_id=display_id, results=results)


@bp.route('/results/optimization/delete/<result_id>', methods=['POST'])
def delete_optimization_result(result_id):
    """Delete an optimization result folder safely."""
    try:
        config = current_app.config
        base_dir = os.path.join(config['RESULTS_FOLDER'], 'optimizations')
        target_dir = os.path.join(base_dir, result_id)

        if os.path.commonpath([os.path.abspath(target_dir), os.path.abspath(base_dir)]) != os.path.abspath(base_dir):
            return jsonify({'error': 'Invalid path'}), 400

        if not os.path.exists(target_dir):
            return jsonify({'error': 'Not found'}), 404

        shutil.rmtree(target_dir)
        logger.info(f"Deleted optimization result: {result_id}")
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f"DELETE OPTIMIZATION FAILED: {str(e)}")
        return jsonify({'error': str(e)}), 500


# Background job worker function
def _execute_optimization_job(job_id: str, config: dict):
    """Background worker function for optimization execution."""
    # Import here to avoid circular imports and get the current app instance
    from flask import current_app
    from app.app import app as flask_app
    
    # Set up application context for background thread
    with flask_app.app_context():
        job_manager = flask_app.job_manager
        job = job_manager.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return
        
        try:
            job.status = 'running'
            job.started_at = datetime.now().isoformat()
            job.progress = 5
            job_manager._save_job(job)
            
            logger.info("=" * 60)
            logger.info(f"OPTIMIZATION JOB {job_id} STARTED")
            logger.info(f"Strategy: {config['strategy']}")
            logger.info(f"Data file: {config['data_file']}")
            
            # Load data
            data_file = config['data_file']
            data_path = get_data_file_path(data_file)
            data = CSVDataLoader.load_csv(data_path)
            logger.info(f"Price data loaded: {len(data)} rows")
            job_manager.update_job(job_id, progress=20)
            
            # Load optional scores
            scores_data = None
            scores_file = config.get('scores_file')
            
            if scores_file and scores_file.strip():
                logger.info(f"Attempting to load scores from: {scores_file}")
                db_paths = [
                    os.path.join(flask_app.config['UPLOAD_FOLDER'], scores_file),
                    os.path.join(os.path.dirname(os.path.dirname(flask_app.config['UPLOAD_FOLDER'])), 'db', scores_file),
                ]
                
                scores_path = None
                for path in db_paths:
                    if os.path.exists(path):
                        scores_path = path
                        logger.info(f"✓ Found at: {scores_path}")
                        break
                
                if scores_path:
                    is_valid = ScoreDataLoader.validate_database(scores_path)
                    
                    if is_valid:
                        try:
                            start_date_raw = data[0].get('timestamp') if data else None
                            end_date_raw = data[-1].get('timestamp') if data else None
                            
                            start_date = None
                            end_date = None
                            if start_date_raw:
                                try:
                                    dt = datetime.strptime(start_date_raw, '%d/%m/%Y %H:%M:%S')
                                    start_date = dt.strftime('%Y-%m-%dT%H:%M:%S')
                                except:
                                    pass
                            if end_date_raw:
                                try:
                                    dt = datetime.strptime(end_date_raw, '%d/%m/%Y %H:%M:%S')
                                    end_date = dt.strftime('%Y-%m-%dT%H:%M:%S')
                                except:
                                    pass
                            
                            scores_data = ScoreDataLoader.load_scores(
                                scores_path,
                                channel_name=config.get('channel_name'),
                                start_date=start_date,
                                end_date=end_date
                            )
                            logger.info(f"✓ Scores data loaded: {len(scores_data)} records")
                        except Exception as score_err:
                            logger.error(f"Failed to load scores: {score_err}")
            
            # Load strategy
            strategy_name = config['strategy']
            strategy_path = resolve_strategy_path(strategy_name)
            
            spec = importlib.util.spec_from_file_location(strategy_name, strategy_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            strategy_class_name = snake_to_pascal_case(strategy_name)
            strategy_class = getattr(module, strategy_class_name)
            job_manager.update_job(job_id, progress=25)
            
            # Get parameter ranges
            param_ranges = config.get('param_ranges', {})

            # Static params
            base_params = {
                'instrument_type': config.get('instrument_type'),
                'position_size': config.get('position_size'),
                'point_value': config.get('point_value'),
                'tick_size': config.get('tick_size')
            }
            base_params = {k: v for k, v in base_params.items() if v is not None}

            # Run optimization
            optimizer = StrategyOptimizer(
                strategy_class=strategy_class,
                data=data,
                param_ranges=param_ranges,
                initial_capital=config.get('initial_capital', 100000),
                commission=config.get('commission', 0),
                slippage_ticks=config.get('slippage_ticks', 0),
                max_workers=config.get('max_workers', 4),
                max_bars_back=config.get('max_bars_back', 100),
                scores_data=scores_data,
                base_params=base_params,
                strategy_path=strategy_path
            )
            
            results = optimizer.run_optimization(
                metric=config.get('metric', 'total_return'),
                top_n=config.get('top_n', 10),
                verbose=True,
                progress_callback=lambda pct: job_manager.update_job(
                    job_id,
                    progress=min(95, int(10 + (pct * 0.8)))
                )
            )

            # Save results
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            folder_name = build_result_folder('optimization', strategy_name, timestamp=timestamp)
            result_dir = os.path.join(flask_app.config['RESULTS_FOLDER'], 'optimizations', folder_name)
            logger.info(f"Saving results to: {result_dir}")
            
            with open(strategy_path, 'r', encoding='utf-8') as f:
                strategy_code = f.read()
            
            run_settings = {
                'data_file': data_file,
                'metric': config.get('metric', 'total_return'),
                'top_n': config.get('top_n', 10),
                'initial_capital': config.get('initial_capital', 100000),
                'commission': config.get('commission', 0),
                'slippage_ticks': config.get('slippage_ticks', 0),
                'max_workers': config.get('max_workers', 4),
                'scores_file': config.get('scores_file'),
                'channel_name': config.get('channel_name'),
                'instrument_type': base_params.get('instrument_type'),
                'position_size': base_params.get('position_size'),
                'point_value': base_params.get('point_value'),
                'tick_size': base_params.get('tick_size')
            }
            results['run_settings'] = run_settings
            results['base_params'] = base_params
            
            optimizer.save_results(results, result_dir, strategy_code, run_settings=run_settings, base_params=base_params, save_individual_backtests=True)
            
            logger.info("Optimization completed!")
            logger.info(f"Total combinations tested: {results.get('total_combinations', 0)}")
            
            # Update job
            job.status = 'completed'
            job.completed_at = datetime.now().isoformat()
            job.result_id = folder_name
            job.progress = 100
            job_manager._save_job(job)
            logger.info(f"Job {job_id} completed successfully")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.exception(f"OPTIMIZATION JOB {job_id} FAILED: {str(e)}")
            job.status = 'failed'
            job.error = str(e)
            job.completed_at = datetime.now().isoformat()
            job.progress = 100
            job_manager._save_job(job)
            logger.error("=" * 60)

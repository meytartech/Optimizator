"""
Optimization Engine

Runs parameter grid search for strategy optimization.
Supports parallel execution and comprehensive result tracking.
"""

import itertools
import json
import os
import multiprocessing
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
import copy


def _run_single_backtest(args):
    """Module-level function for multiprocessing compatibility.
    
    On Windows, we can't pickle strategy classes from Flask's dynamic imports.
    Instead, we pass the strategy file path and class name as strings, then reload
    the strategy module in the worker process using the same method as the web app.
    """
    strategy_path, strategy_class_name, params, base_params, data, initial_capital, commission, slippage_ticks, max_bars_back = args
    
    import importlib.util
    import os
    from core.backtester import GenericBacktester
    
    # Load strategy from file path (same method as web app)
    strategy_module_name = os.path.splitext(os.path.basename(strategy_path))[0]
    spec = importlib.util.spec_from_file_location(strategy_module_name, strategy_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    strategy_class = getattr(module, strategy_class_name)
    
    merged_params = {**base_params, **params}
    strategy = strategy_class(merged_params)
    backtester = GenericBacktester(
        initial_capital=initial_capital,
        commission_per_trade=commission,
        slippage_ticks=slippage_ticks,
        max_bars_back=max_bars_back,
        verbose=False
    )
    result = backtester.run(strategy, data)
    return {
        'parameters': params,
        'metrics': {
            'total_return': result.total_return,
            'sharpe_ratio': result.sharpe_ratio,
            'max_drawdown': result.max_drawdown,
            'win_rate': result.win_rate,
            'profit_factor': result.profit_factor,
            'total_trades': result.total_trades,
            'avg_win': result.avg_win,
            'avg_loss': result.avg_loss,
            'avg_rr': result.avg_rr,
            'final_equity': result.final_equity
        }
    }


class StrategyOptimizer:
    """Strategy parameter optimization engine.
    
    Features:
    - Grid search optimization
    - Parallel execution
    - Result ranking and filtering
    - Full statistics and strategy code capture
    """
    
    def __init__(self, 
                 strategy_class,
                 data: List[Dict[str, Any]],
                 param_ranges: Dict[str, tuple],
                 initial_capital: float = 100000.0,
                 commission: float = 0.0,
                 slippage_ticks: int = 0,
                 max_workers: int = 0,
                 max_bars_back: int = 100,
                 base_params: Optional[Dict[str, Any]] = None,
                 strategy_path: Optional[str] = None):
        """Initialize optimizer.
        
        Args:
            strategy_class: Strategy class (not instance)
            data: Unified historical data with embedded scores
            param_ranges: Dict mapping param names to (min, max, step) tuples
            initial_capital: Starting capital for each run
            commission: Commission per trade
            slippage_ticks: Slippage in ticks
            max_workers: Number of parallel workers
            max_bars_back: Maximum bars to pass to on_bar (0 = all)
            base_params: Static params applied to every run (instrument specs, sizing, etc.)
            strategy_path: File path to strategy .py file (for multiprocessing)
        """
        self.strategy_class = strategy_class
        self.strategy_path = strategy_path
        self.data = data
        self.param_ranges = param_ranges
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage_ticks = slippage_ticks
        self.max_bars_back = max_bars_back
        # Auto-detect CPU cores if max_workers not specified (0 = auto)
        if max_workers <= 0:
            self.max_workers = min(multiprocessing.cpu_count(), 16)  # Cap at 16 to avoid resource exhaustion
        else:
            self.max_workers = max(1, min(max_workers, multiprocessing.cpu_count()))
        # Static params applied to every run (instrument specs, sizing, etc.)
        self.base_params = base_params or {}
    
    def generate_param_combinations(self) -> List[Dict[str, Any]]:
        """Generate all parameter combinations from ranges.
        
        Returns:
            List of parameter dictionaries
        """
        param_names = list(self.param_ranges.keys())
        param_values = []
        
        for name in param_names:
            min_val, max_val, step = self.param_ranges[name]
            values = []
            val = min_val
            while val <= max_val:
                values.append(val)
                val += step
            param_values.append(values)
        
        combinations = []
        for combo in itertools.product(*param_values):
            param_dict = dict(zip(param_names, combo))
            combinations.append(param_dict)
        
        return combinations
    
    def run_optimization(self, 
                        metric: str = 'total_return',
                        top_n: int = 10,
                        verbose: bool = True,
                        progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """Run optimization across all parameter combinations.
        
        Args:
            metric: Metric to optimize ('total_return', 'sharpe_ratio', 'profit_factor', etc.)
            top_n: Number of top results to return
            verbose: Print progress
            
        Returns:
            Dictionary with optimization results
        """
        combinations = self.generate_param_combinations()
        
        if verbose:
            print(f"Starting optimization for {self.strategy_class.__name__}")
            print(f"Total combinations: {len(combinations)}")
            print(f"Metric: {metric}")
            print(f"Workers: {self.max_workers}\n")
        
        results = []
        completed = 0

        # Prepare arguments for multiprocessing
        # Pass strategy file path + class name to avoid pickle issues on Windows
        strategy_class_name = self.strategy_class.__name__
        
        backtest_args = [
            (self.strategy_path, strategy_class_name, params, self.base_params, self.data,
             self.initial_capital, self.commission, self.slippage_ticks, self.max_bars_back)
            for params in combinations
        ]

        # Use sequential execution for single worker to avoid multiprocessing issues
        if self.max_workers == 1:
            for i, args in enumerate(backtest_args):
                try:
                    result = _run_single_backtest(args)
                    results.append(result)
                except Exception as exc:
                    if verbose:
                        print(f"Combination failed: {exc}")
                completed += 1
                if progress_callback and combinations:
                    pct = (completed / len(combinations)) * 100
                    progress_callback(pct)
                if verbose and completed % 10 == 0:
                    print(f"Progress: {completed}/{len(combinations)} ({completed/len(combinations)*100:.1f}%)")
        else:
            # Use ProcessPoolExecutor for true parallelism (not limited by GIL)
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                future_map = {executor.submit(_run_single_backtest, args): args[1] for args in backtest_args}
                for future in as_completed(future_map):
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        if verbose:
                            print(f"Combination failed: {exc}")
                    completed += 1
                    if progress_callback and combinations:
                        pct = (completed / len(combinations)) * 100
                        progress_callback(pct)
                    if verbose and completed % 10 == 0:
                        print(f"Progress: {completed}/{len(combinations)} ({completed/len(combinations)*100:.1f}%)")
        
        if verbose:
            print(f"Optimization completed: {completed} combinations processed")
        
        # Sort by metric
        results.sort(key=lambda x: x['metrics'].get(metric, 0), reverse=True)
        
        # Get top N
        top_results = results[:top_n]

        if progress_callback:
            progress_callback(100.0)
        
        if not results:
            return {
                'strategy_name': self.strategy_class.__name__,
                'optimization_date': datetime.now().isoformat(),
                'total_combinations': 0,
                'optimization_metric': metric,
                'best_parameters': {},
                'best_metrics': {},
                'top_results': [],
                'all_results': [],
                'base_params': self.base_params,
                'run_settings': {
                    'initial_capital': self.initial_capital,
                    'commission': self.commission,
                    'slippage_ticks': self.slippage_ticks,
                    'max_workers': self.max_workers,
                    'instrument_type': self.base_params.get('instrument_type'),
                    'position_size': self.base_params.get('position_size'),
                    'point_value': self.base_params.get('point_value'),
                    'tick_size': self.base_params.get('tick_size')
                }
            }

        if verbose:
            print(f"\n✅ Optimization complete!")
            print(f"Top result - {metric}: {top_results[0]['metrics'][metric]:.4f}")
            print(f"Best parameters: {top_results[0]['parameters']}")
        
        return {
            'strategy_name': self.strategy_class.__name__,
            'optimization_date': datetime.now().isoformat(),
            'total_combinations': len(combinations),
            'optimization_metric': metric,
            'best_parameters': top_results[0]['parameters'],
            'best_metrics': top_results[0]['metrics'],
            'top_results': top_results,
            'all_results': results,
            'base_params': self.base_params,
            'run_settings': {
                'initial_capital': self.initial_capital,
                'commission': self.commission,
                'slippage_ticks': self.slippage_ticks,
                'max_workers': self.max_workers,
                'instrument_type': self.base_params.get('instrument_type'),
                'position_size': self.base_params.get('position_size'),
                'point_value': self.base_params.get('point_value'),
                'tick_size': self.base_params.get('tick_size')
            }
        }
    
    def save_results(self, results: Dict[str, Any], output_dir: str, 
                     strategy_code: str = None,
                     run_settings: Optional[Dict[str, Any]] = None,
                     base_params: Optional[Dict[str, Any]] = None,
                     save_individual_backtests: bool = True):
        """Save optimization results to directory.
         todo: when modifying the code next - round the results to 2 after decimal point and rm this comment line.
        Args:
            results: Optimization results dictionary
            output_dir: Output directory path
            strategy_code: Source code of the strategy (optional)
            run_settings: Non-optimized execution settings (capital, slippage, instrument)
            base_params: Static params applied to every run (instrument specs, sizing)
            save_individual_backtests: If True, creates individual backtest folders for top N results
        """
        os.makedirs(output_dir, exist_ok=True)
        
        # Create individual backtests for top results if requested
        top_run_folders = []
        if save_individual_backtests and results.get('top_results'):
            print(f"💾 Creating individual backtest folders for top {len(results['top_results'])} results...")
            backtests_dir = os.path.join(output_dir, 'backtests')
            os.makedirs(backtests_dir, exist_ok=True)
            
            for rank, result in enumerate(results['top_results'], 1):
                rank_folder = f"rank_{rank:02d}"
                rank_dir = os.path.join(backtests_dir, rank_folder)
                os.makedirs(rank_dir, exist_ok=True)
                
                # Re-run this specific parameter combination to get full backtest data
                params = result['parameters']
                merged_params = {**(base_params or {}), **params}
                strategy = self.strategy_class(merged_params)
                
                from core.backtester import GenericBacktester
                backtester = GenericBacktester(
                    initial_capital=self.initial_capital,
                    commission_per_trade=self.commission,
                    slippage_ticks=self.slippage_ticks,
                    max_bars_back=self.max_bars_back,
                    verbose=False
                )
                
                # Run full backtest to get trades, equity curve, etc.
                backtest_result = backtester.run(strategy, self.data)
                
                # Save individual backtest results (same format as normal backtests)
                backtest_json = {
                    'strategy_name': self.strategy_class.__name__,
                    'parameters': params,
                    'total_return': backtest_result.total_return,
                    'sharpe_ratio': backtest_result.sharpe_ratio,
                    'max_drawdown': backtest_result.max_drawdown,
                    'win_rate': backtest_result.win_rate,
                    'profit_factor': backtest_result.profit_factor,
                    'total_trades': backtest_result.total_trades,
                    'avg_win': backtest_result.avg_win,
                    'avg_loss': backtest_result.avg_loss,
                    'avg_rr': backtest_result.avg_rr,
                    'final_equity': backtest_result.final_equity,
                    'trades': [trade.__dict__ for trade in backtest_result.trades],
                    'equity_curve': backtest_result.equity_curve,
                    'session_stats': backtest_result.session_stats,
                    'exit_reason_stats': backtest_result.exit_reason_stats
                }
                
                # Save backtest results
                results_path = os.path.join(rank_dir, 'results.json')
                with open(results_path, 'w') as f:
                    json.dump(backtest_json, f, indent=2)
                
                # Note: config.json removed - configuration saved in results.json
                
                # Save strategy code
                if strategy_code:
                    code_path = os.path.join(rank_dir, 'strategy_code.txt')
                    with open(code_path, 'w', encoding='utf-8') as f:
                        f.write(strategy_code)
                
                # Generate equity curve chart
                try:
                    from core.equity_plotter import EquityPlotter
                    chart_path = os.path.join(rank_dir, 'equity_curve.png')
                    EquityPlotter.plot_equity_curve(backtest_result.equity_curve, chart_path, 
                                                  title=f"Rank {rank} - {self.strategy_class.__name__}")
                except Exception as e:
                    print(f"⚠️ Could not generate equity chart for rank {rank}: {e}")
                
                top_run_folders.append({
                    'rank': rank,
                    'folder': rank_folder,
                    'parameters': params,
                    'metrics': result['metrics']
                })
            
            # Update results with folder information
            results['top_run_folders'] = top_run_folders
        
        # Save summary with all_results for visualization in HTML
        summary_data = {
            'strategy_name': results['strategy_name'],
            'optimization_date': results['optimization_date'],
            'total_combinations': results['total_combinations'],
            'optimization_metric': results['optimization_metric'],
            'best_parameters': results['best_parameters'],
            'best_metrics': results['best_metrics'],
            'top_results': results.get('top_results', []),
            'all_results': results.get('all_results', []),  # Include all results for distribution and parameter charts
            'top_run_folders': results.get('top_run_folders', []),
            'run_settings': run_settings or results.get('run_settings', {}),
            'base_params': base_params or results.get('base_params', {})
        }
        
        results_path = os.path.join(output_dir, 'optimization_results.json')
        with open(results_path, 'w') as f:
            json.dump(summary_data, f, indent=2)
        
        # Save detailed results with all combinations (optional, for analysis)
        detailed_path = os.path.join(output_dir, 'all_combinations_detail.json')
        with open(detailed_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        # Save top combinations as CSV
        csv_path = os.path.join(output_dir, 'top_combinations.csv')
        with open(csv_path, 'w') as f:
            top_results = results.get('top_results', [])
            if top_results:
                # Header
                param_names = list(top_results[0]['parameters'].keys())
                metric_names = list(top_results[0]['metrics'].keys())
                header = ','.join(['rank'] + param_names + metric_names)
                f.write(header + '\n')
                
                # Data rows
                for rank, result in enumerate(top_results, 1):
                    params = [str(result['parameters'][p]) for p in param_names]
                    metrics = [str(result['metrics'][m]) for m in metric_names]
                    row = ','.join([str(rank)] + params + metrics)
                    f.write(row + '\n')
        
        # Save strategy code if provided
        if strategy_code:
            code_path = os.path.join(output_dir, 'strategy_code.py')
            with open(code_path, 'w') as f:
                f.write(strategy_code)
        
        # Save summary
        summary_path = os.path.join(output_dir, 'summary.txt')
        with open(summary_path, 'w') as f:
            f.write(f"Strategy Optimization Summary\n")
            f.write(f"{'='*60}\n\n")
            f.write(f"Strategy: {results['strategy_name']}\n")
            f.write(f"Date: {results['optimization_date']}\n")
            f.write(f"Total Combinations Tested: {results['total_combinations']}\n")
            f.write(f"Optimization Metric: {results['optimization_metric']}\n\n")
            f.write(f"Best Parameters:\n")
            for key, val in results['best_parameters'].items():
                f.write(f"  {key}: {val}\n")
            f.write(f"\nBest Metrics:\n")
            for key, val in results['best_metrics'].items():
                f.write(f"  {key}: {val:.4f}\n")
        
        print(f"\n💾 Results saved to: {output_dir}")

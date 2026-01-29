#!/usr/bin/env python3
"""Simple standalone backtest runner for testing strategies.

This runner is intentionally lightweight: it attaches a minimal engine
to a strategy, executes pending orders at the next bar open, and
iterates through the combined unified data. Its purpose is to
verify that `on_bar()` runs without exceptions and that `buy()`/
`sell_short()` calls route to the engine correctly.

Usage:
    python scripts/backtest_standalone.py --strategy og_mnq_strategy --data app/db/mnq.db
"""
import argparse
import traceback
import sys
import os
from typing import List, Dict, Any

# Ensure project root is on sys.path so `core` and `app` imports resolve
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.score_loader import ScoreDataLoader

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--strategy', required=True)
    parser.add_argument('--data', required=True)
    args = parser.parse_args()

    # Dynamically import the strategy module
    strategy_module_path = f"app.strategies.{args.strategy}"
    try:
        mod = __import__(strategy_module_path, fromlist=['*'])
    except Exception:
        print(f"Failed to import strategy module: {strategy_module_path}")
        traceback.print_exc()
        return

    # Strategy class name mapping: snake_to_pascal (as project expects)
    cls_name = ''.join(part.upper() if len(part) <= 3 else part.capitalize() for part in args.strategy.split('_'))
    StrategyCls = getattr(mod, cls_name, None)
    if StrategyCls is None:
        print(f"Strategy class '{cls_name}' not found in module {strategy_module_path}")
        return

    # Load combined DB
    try:
        data = ScoreDataLoader.load_combined_db(args.data)
    except Exception as e:
        print(f"Failed to load combined DB: {e}")
        traceback.print_exc()
        return

    # Minimal engine to satisfy BaseStrategy expectations
    class MinimalEngine:
        def __init__(self):
            self.pending_order = None
            self._trade_direction = 0
            self._entry_price = 0.0
            self._position_size = 0
            self.trades = []

        @property
        def position_size(self):
            return self._position_size

        def place_order(self, action: str, quantity: int = 1, exit_type: str = '', reason: str = ''):
            # store pending order, to be executed at next bar open
            self.pending_order = dict(action=action, quantity=quantity, exit_type=exit_type, reason=reason)

    engine = MinimalEngine()

    # Instantiate strategy
    strat = StrategyCls()
    strat.engine = engine

    # Runner state
    executed_orders = 0
    errors = []

    # Iterate bars and run strategy
    for i, bar in enumerate(data):
        ts = bar.get('timestamp')
        open_price = bar.get('open', bar.get('close'))

        # Execute pending order from previous bar (next-bar fill)
        po = engine.pending_order
        if po:
            try:
                action = po.get('action')
                qty = int(po.get('quantity', 1))
                reason = po.get('reason', '')

                if engine._trade_direction == 0:
                    # open position
                    if action == 'buy':
                        engine._trade_direction = 1
                        engine._entry_price = open_price
                        engine._position_size = qty
                    elif action == 'sell':
                        engine._trade_direction = -1
                        engine._entry_price = open_price
                        engine._position_size = qty
                else:
                    # treat as exit if reason looks like an exit
                    if reason.upper() in ('TP1','TP2','TP3','SL','EXIT','FORCE_CLOSE_EOD','EARLY_CLOSE','BREAKEVEN'):
                        # reduce position
                        engine._position_size = max(0, engine._position_size - qty)
                        if engine._position_size == 0:
                            engine._trade_direction = 0
                executed_orders += 1
            except Exception:
                errors.append((i, 'execute_pending', traceback.format_exc()))
            finally:
                engine.pending_order = None

        # Build bars_slice (pass all history up to current)
        bars_slice = data[:i+1]

        # Build scores slice from embedded data
        scores_slice: List[Dict[str, Any]] = bars_slice  # All data includes embedded scores

        try:
                # Call strategy.on_bar with the appropriate signature.
                # Some strategies expect only `data`, others accept `data, scores_data`.
                import inspect
                sig = inspect.signature(strat.on_bar)
                params = len(sig.parameters)
                # For bound methods, parameters typically exclude 'self', so params==1 means only data
                if params >= 2:
                    strat.on_bar(bars_slice, scores_slice)
                else:
                    strat.on_bar(bars_slice)
        except Exception:
            errors.append((i, 'on_bar', traceback.format_exc()))
            # Continue to next bar to collect more errors

    # Summary
    print(f"Backtest run complete. Bars processed: {len(data)}")
    print(f"Pending orders executed: {executed_orders}")
    print(f"Final position size: {engine._position_size}, direction: {engine._trade_direction}")
    if errors:
        print(f"Encountered {len(errors)} error(s) during run:")
        for idx, phase, tb in errors:
            print(f"- Bar #{idx} phase={phase}\n{tb}")
        raise SystemExit(2)
    else:
        print("No errors detected in strategy execution.")

if __name__ == '__main__':
    main()

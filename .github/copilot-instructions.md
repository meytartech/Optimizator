# Copilot Instructions for Backtesting & Optimization System

## Project Overview
This is a Flask-based backtesting and parameter optimization platform for trading strategies. It supports both stocks (dollar-based) and futures (point/tick-based) with dual-dataset capabilities (price + optional external indicators).

**Key Architectural Pattern**: Generic strategy engine that decouples strategy logic from backtesting mechanics through an **event-driven order placement** API (as of January 20, 2026).

---

## Core Architecture

### Three-Layer Design
1. **Web Layer** (`app/app.py`): Flask routes for data/strategy management, backtest/optimization execution
2. **Core Engine** (`core/`): Reusable backtester, optimizer, and data loaders independent of the web layer
3. **Strategy Layer** (`app/strategies/`): User-written strategy classes inheriting `BaseStrategy`

### Data Flow (Event-Driven Pattern)
```
CSV/Combined DB → CSVDataLoader/ScoreDataLoader → prices_data + scores_data (List[Dict])
                ↓
GenericBacktester.run(strategy, data, scores)
    ↓ (for each bar)
    Strategy.on_bar(price_bars, scores_data)
        ↓ (place orders)
        strategy.buy(quantity, reason) / strategy.sell_short(quantity, reason)
            ↓ (execute next bar open)
            Unified execute_exit() → update position, record trade
                ↓
                BacktestResult
                    ↓
Save to app/results/{backtests,optimizations}/ + equity_curve.png
```

### Dual-Dataset Pattern (Critical Feature)

### Data Input Pattern (Unified Combined DB Only)
**As of January 2026, the ONLY supported data input is a single combined SQLite .db file with the following schema:**

- **Table:** `combined_market_data`
- **Columns:**
    - `id` (INTEGER, primary key)
    - `timestamp` (DATETIME, required)
    - `score_1m` (FLOAT, required)
    - `score_5m` (FLOAT, required)
    - `score_15m` (FLOAT, required)
    - `score_60m` (FLOAT, required)
    - `open` (FLOAT, required)
    - `high` (FLOAT, required)
    - `low` (FLOAT, required)
    - `close` (FLOAT, required)

**No CSV or legacy score DBs are supported.**

- Each row represents a single price bar and its associated multi-timeframe scores.
- The system extracts both price and score data from this table for all backtests and optimizations.
- Strategies receive both `price_bars` and `scores_data` in `on_bar()` as before, but all data is sourced from this unified table.

See `sources/STRATEGY_DEV_RULES.md` for usage patterns and code examples.

---

## Development Standards & Rules
**write me which rules you use when executing it**
### Rule 1: Markdown Files Organization
**Root directory may only contain `README.md`.** No temporary or permanent documentation files should reside in the root directory.

**File Organization**:
- **Temporary markdown files**: Must be deleted after use (never saved to disk)
- **Permanent documentation**: Must be organized in `./sources/` folder (e.g., `sources/STRATEGY_GUIDE.md`, `sources/OPTIMIZATION_PROCESS.md`)
- **Root level**: Only `README.md` for project overview; all other docs go to `sources/`

**Why**: Keeps project root clean, prevents documentation clutter, and provides a single documentation hub in `sources/` for all non-temporary project information.

### Rule 2: Scripts Location & Lifecycle
**All production scripts must reside in `./scripts/` folder.** Only keep non-temporary, reusable scripts. Temporary test scripts must be deleted after execution(e.g verification, db tests...).

**Script Classification**:
- **Production/Reusable Scripts** (keep in `./scripts/`): CLI tools, data loaders, validators, recurring test utilities (e.g., `backtest_standalone.py`, `test_scores_loading.py`)
- **Temporary Test Scripts** (delete after use): One-off debug scripts, single-iteration tests, exploration scripts (e.g., `test_quick_debug.py`, `temp_check.py`) — **do not commit or save long-term**
- **Never save temporary scripts**: If testing locally, delete them immediately after verification; do not commit to repository

**Why**: Centralizes production automation and testing logic, prevents accumulation of stale debug scripts, and makes it clear which scripts are part of the ongoing workflow vs. temporary experimentation.

### Rule 3: Web + CLI Dual Interface Pattern (Critical Architecture)
**The project has two interfaces sharing the same core:**
- **Web Interface** (`app/app.py` + Flask routes): User-facing web UI for backtesting and optimization
- **CLI Interface** (`scripts/` based): Developer tool for testing and log inspection

Both interfaces call the same `core/` modules (backtester, optimizer, data loaders) but with different UX layers.

**Testing Workflow**: When modifying any `core/` file, **always test via CLI** to verify functionality before web integration. Use CLI to inspect logs and ensure expected behavior.

**Why**: Decouples interface from logic; allows rapid testing without web server overhead; CLI logs reveal detailed execution flow for debugging.

### Rule 4: CSS Organization
**CSS must follow a strict folder structure:**
- `app/static/css/theme.css` - Global theme and variables (colors, fonts, spacing)
- `app/static/css/<page_name>.css` - Page-specific styles for each page/feature
- Each page CSS imports theme.css for consistency

**Why**: Prevents CSS duplication, enables theme-wide changes, makes page-specific styling isolated and maintainable.

### Rule 5: Summary Document Creation
**Never create a summary document (.md) after completing tasks.** All relevant information should be documented in existing files or within the appropriate sections of the project documentation.

**Why**: This prevents unnecessary clutter and maintains focus on essential documentation, ensuring that all information is consolidated and easily accessible.

## Essential Conventions

For complete strategy development guidelines including filename/class mapping, strategy interface definition, and code templates, see [sources/STRATEGY_DEV_RULES.md](../sources/STRATEGY_DEV_RULES.md).

**Quick Reference - Event-Driven Order Placement:**
```python
# Strategy logic in on_bar() method
def on_bar(self, price_bars, scores_data=None):
    current_bar = price_bars[-1]  # Current bar
    
    # Entry (if flat)
    if self.position == 0:
        self.buy(quantity=3, reason='ENTRY')  # Long entry
        # OR
        self.sell_short(quantity=3, reason='ENTRY')  # Short entry
    
    # Partial exits (if in position)
    if self.position > 0:
        self.sell_short(quantity=1, reason='TP1')  # Exit 1 contract
        self.buy(quantity=1, reason='TP2')  # Exit 1 contract (short position)
    
    # Full exit (close all remaining)
    if self.position > 0:
        self.sell_short(quantity=self.position, reason='SL')  # Close all (long)
        self.buy(quantity=self.position, reason='EXIT')  # Close all (short)
```

**Position Management:**
- `self.position` is READ-ONLY (returns `self.engine.position_size`)
- Never manually set `self.position` - automatically updated by engine
- Track direction with `self._position_direction` (1=long, -1=short, 0=flat)

---
## Project Structure & Key Files

| Path | Purpose |
|------|---------|
| `app/app.py` | Main Flask app; routes for upload, backtest, optimize, results |
| `app/strategies/` | User strategy files (e.g., `simple_ma_strategy.py`, `mnq_strategy.py`) |
| `app/results/backtests/` | Backtest outputs: `results.json`, `strategy_code.txt`, `equity_curve.png`, `trades.csv` |
| `app/results/optimizations/` | Optimization outputs with best parameter sets |
| `app/db/` | CSV data files uploaded via web UI |
| `app/templates/` | Flask Jinja2 templates for web UI pages |
| `app/static/css/` | CSS stylesheets: `theme.css` (global) + page-specific files |
| `app/static/js/` | JavaScript for interactive components |
| `core/base_strategy.py` | Abstract `BaseStrategy` class and `TradeSignal` dataclass |
| `core/backtester.py` | `GenericBacktester`: runs strategy, tracks trades, computes metrics |
| `core/optimizer.py` | `StrategyOptimizer`: grid search over parameter ranges |
| `core/data_loader.py` | `CSVDataLoader`: multi-format CSV parsing (OHLCV, simplified, angle-bracket) |
| `core/score_loader.py` | `ScoreDataLoader`: loads SQLite score data OR combined .db (OHLC+scores in one file) |
| `core/equity_plotter.py` | `EquityPlotter`: matplotlib-based equity curve + drawdown visualization |
| `scripts/` | Reusable CLI scripts for testing, validation, and standalone execution |
| `sources/` | Non-temporary documentation (STRATEGY_GUIDE.md, SCORE_DATA_INTEGRATION.md, etc.) |
| `requirements.txt` | Flask, matplotlib, SQLAlchemy, numpy, pandas, etc. |

---

## Common Development Tasks

### Create a New Strategy
1. Create file `app/strategies/your_strategy.py` with class `YourStrategy(BaseStrategy)` (snake_case filename → PascalCase classname)
2. Implement `setup()`, `on_bar()`, `get_parameter_ranges()`
3. Use web UI "Strategy Template" generator for boilerplate
4. Test via Backtest page (select strategy, upload combined .db file, run)

### Debug Strategy Issues
- Check **timestamp matching**: ensure all signals' timestamps exist in prices_data
- Use `bar.get('timestamp')`, `bar.get('close', bar.get('price'))` for field access (fallbacks)
- Log intermediate calculations in `on_bar()` to `stdout` (visible in server logs)
- Review saved `strategy_code.txt` in results folder to confirm code was executed

### Add Optimization Parameters
1. Update `setup()` to extract parameters from `self.params` with defaults
2. Return tuples in `get_parameter_ranges()`: `'param_name': (min, max, step)`
3. Optimizer grid-searches all combinations; backtester scores each

### Access Web UI
```bash
python run_server.py
# Open http://localhost:5000
```

---

## Backtester Mechanics

### Core Loop (`backtester.py`)
- Iterates each bar in `prices_data` (chronological order)
- Looks up signal by matching bar timestamp in signal map (exact string match required)
- If signal exists: opens position, respects stop_loss, take_profits, and breakeven_trigger
- On bar progression: evaluates position against TP levels, SL, and breakeven trigger
- Tracks cumulative equity and drawdown for all open/closed positions
- On position exit (TP/SL hit or new signal): records Trade object with PnL

### Metrics Computed
- **total_return**: (final_equity - initial_capital) / initial_capital * 100%
- **sharpe_ratio**: (mean_daily_return - risk_free_rate) / std(daily_returns)
- **max_drawdown**: (peak_equity - trough_equity) / peak_equity * 100%
- **win_rate**: winning_trades / total_trades * 100%
- **profit_factor**: sum(wins) / sum(losses)
- **avg_trade**: total_return / number_of_trades (average PnL per trade)
- **consecutive_wins**: longest streak of winning trades
- **consecutive_losses**: longest streak of losing trades

### Equity Curve Format
The equity curve array in `results.json` tracks position state at each bar:
```json
{
  "timestamp": "2024-01-15 09:35:00",
  "equity": 50350.00,
  "tradeDirection": 1  // 1=long, -1=short, 0=flat
}
```
**Note**: Prior to January 28, 2026, this field was named `position` - now standardized as `tradeDirection`.

### Instrument Types
Configure in strategy `setup()` via `self.params['instrument_type']`:
- **Stocks**: `instrument_type='stock'`, `point_value=1.0`, PnL = (exit_price - entry_price) * quantity
- **Futures**: `instrument_type='futures'`, `point_value=2.0` (ES) or similar per contract specs
  - PnL = (exit_price - entry_price) * point_value * quantity
  - E.g., MNQ: point_value=2 (one point = $2), ES: point_value=50 (one point = $50)

Example:
```python
def setup(self):
    self.instrument_type = self.params.get('instrument_type', 'futures')
    self.point_value = self.params.get('point_value', 2.0)
```

---

## Common Pitfalls & Solutions

| Issue | Solution |
|-------|----------|
| "Signal timestamp not in data" | Ensure signal timestamp exactly matches a bar's `timestamp` field; check date formats |
| Strategy class not found | Verify filename→classname mapping (e.g., `my_strat.py` → `MyStrat`), not `MyStrat_` |
| Scores not loading | Check `.db` file path, validate schema with `ScoreDataLoader.validate_database()` |
| Equity curve not generated | Review `equity_plotter.py` dependencies (matplotlib); check result folder permissions |
| Parameters not optimizing | Confirm `get_parameter_ranges()` returns dict of tuples `(min, max, step)`, not lists |

---

## Testing & Validation

### CLI-Based Testing
When modifying any `core/` module (backtester, optimizer, data loaders), test via CLI scripts:

```bash
# Standalone backtest (outside web server)
python scripts/backtest_standalone.py

# Test score data loading
python scripts/test_scores_loading.py <path_to.db>

# View trade execution and debug
python scripts/trade_viewer_app.py

# Validate CSV format
python scripts/test_csv_format.py <file.csv>
```

### Web Interface Testing
- Start server: `python run_server.py` in a separate terminal
- Navigate to http://localhost:5000 to test UI workflows
- Check Flask server logs for strategy execution output and errors
- Use browser developer tools (F12) to verify frontend logic

### Job Monitoring
- Active/completed jobs tracked in `app/jobs/` as JSON files
- Review job status and results through web UI "Jobs" page
- For debugging, inspect raw JSON: `cat app/jobs/backtest_<timestamp>_<strategy>.json`

### Best Practices
- **Test core changes via CLI first** before deploying to web (Rule 3)
- Log intermediate calculations to `stdout` in strategy code; visible in CLI output and server logs
- Use `print()` statements in `generate_signal()` for signal-by-signal debugging
- Validate timestamp matching manually: signal timestamps must exactly match bar timestamps

### Backtest Result Inspection
- **Results**: Check `app/results/backtests/<timestamp>_<strategy>/results.json` for metrics and configuration
- **Equity curve**: View `equity_curve.png` in results folder (matplotlib-generated PNG)
- **Strategy code**: Review `strategy_code.txt` to confirm which code was executed
- **Trades list**: Review `trades.csv` for entry/exit timestamps, reasons, and PnL
- **Data source**: Results include `data_file` path to original .db for dynamic loading

---
## Timezone & Session Definitions

### Trading Sessions (in Chicago Timezone)

**Use MNQ (Micro E-mini Nasdaq-100) as the canonical instrument for all backtests and optimizations.**

| Session | Market | Local Time | Chicago Time (CT) |
| --- | --- | --- | --- |
| **Asia** | Tokyo | 09:00–15:00 JST | 6:00 PM (prev) – 12:00 AM | 
| **Europe** | London | 08:00–16:30 GMT/BST | 2:00 AM – 10:30 AM | 
| **New York** | NYSE/NASDAQ | 09:30–16:00 EST/EDT | 8:30 AM – 3:00 PM | 
| **Extended** | US Futures | 17:00 (prev) – 16:00 | 5:00 PM (prev) – 4:00 PM |

---


## Integration Points & External Data


**Data Input:**
- Only the combined .db format is supported. The required schema is:
    - `id`, `timestamp`, `score_1m`, `score_5m`, `score_15m`, `score_60m`, `open`, `high`, `low`, `close`
- No CSV, legacy score DB, or other formats are accepted.
- Each row contains all price and score data for a single bar.

**Data Loading Patterns:**
- **Full Dataset**: `ScoreDataLoader.load_combined_db(db_path)` - Load entire dataset for backtests
- **Date Range**: `ScoreDataLoader.load_combined_db_range(db_path, start_timestamp, end_timestamp, buffer_bars=50)` - Load specific date range with context buffer for trade viewer
- **Storage**: Backtest results include `data_file` path to .db; no prices_data.json saved (eliminates redundancy)
- **Trade Viewer**: Dynamically loads data from .db using date range query instead of storing full dataset

---

## Quick Reference: File Paths in App Routes

The app supports **dual resolution** for compatibility (legacy + current):
- **Data files**: prefer `app/db/`, fallback to `../data/db/`
- **Strategies**: prefer `app/strategies/`, fallback to `../data/strategies/`
- **Results**: always `app/results/backtests/` or `app/results/optimizations/`
- **Score files**: search in `app/db/`, `../db/`, then absolute path

Use `get_data_file_path()`, `resolve_strategy_path()` helpers in app.py for resolution logic.

---

## Recommended Reading Order
1. **README.md** – Project features and quick start
2. **sources/STRATEGY_DEV_RULES.md** – Strategy development guidelines with examples
3. **core/base_strategy.py** – Interface definition
4. **core/backtester.py** – How trades are executed and metrics computed
5. **core/score_loader.py** – Score data and combined DB loading patterns



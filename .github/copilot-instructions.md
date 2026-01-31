# Copilot Instructions for Backtesting & Optimization System

## Project Overview
This is a Flask-based backtesting and parameter optimization platform for trading strategies.

**Key Architectural Pattern**: Generic strategy engine that decouples strategy logic from backtesting mechanics through an **event-driven order placement**

---

## Core Architecture

### Three-Layer Design
1. **Web Layer** (`app/app.py`): Flask routes for data/strategy management, backtest/optimization execution
2. **Core Engine** (`core/`): Reusable backtester, optimizer, and data loaders independent of the web layer
3. **Strategy Layer** (`app/strategies/`): User-written strategy classes inheriting `BaseStrategy`

### Data Flow (Event-Driven Pattern)
```
DB → ScoreDataLoader → data(List[Dict])
                ↓
GenericBacktester.run(strategy, data)
    ↓ (for each bar)
        ↓ (place orders)
            ↓
            BacktestResult
                ↓
                Save to app/results
```

### Dual-Dataset Pattern (Critical Feature)

### Data Input Pattern (Unified Combined DB Only)
**ONLY supported data input is a SQLite .db file with the following schema:**

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

- Each row represents a single price bar and its associated multi-timeframe scores.
- The system extracts both price and score data from this table for all backtests and optimizations.

---

## Development Standards & Rules
**write me which rules you use when executing it**
### Rule 1: Markdown Files Organization
**Root directory may only contain `README.md`.** No temporary or permanent documentation files should reside in the root directory.

**File Organization**:
- **Temporary markdown files**: Must be deleted after use (never saved to disk)
- **Permanent documentation**: Must be organized in `./sources/` folder (e.g., `sources/STRATEGY_GUIDE.md`, `sources/OPTIMIZATION_PROCESS.md`)
- **Root level**: Only `README.md` for project overview; all other docs go to `sources/`

### Rule 2: Scripts Location & Lifecycle
**All scripts must reside in `./scripts/` folder.** Only keep non-temporary, reusable scripts. Temporary test scripts must be deleted after execution(e.g verification, db tests...).

**Script Classification**:
- **Temporary Test Scripts** (delete after use): One-off debug scripts, single-iteration tests, exploration scripts (e.g., `test_quick_debug.py`, `temp_check.py`) — **do not commit or save long-term**
- **Never save temporary scripts**: If testing locally, delete them immediately after verification; do not commit to repository

### Rule 3: Web + CLI Dual Interface Pattern (Critical Architecture)
**The project has two interfaces sharing the same core:**
- **Web Interface** (`app/app.py` + Flask routes): User-facing web UI for backtesting and optimization
- **CLI Interface** (`scripts/` based): Developer tool for testing and log inspection

Both interfaces call the same `core/` modules (backtester, optimizer, data loaders) but with different UX layers.

**Testing Workflow**: When modifying any `core/` file, **always test via CLI** to verify functionality before web integration. Use CLI to inspect logs and ensure expected behavior.

### Rule 4: CSS Organization
**CSS must follow a strict folder structure:**
- `app/static/css/theme.css` - Global theme and variables (colors, fonts, spacing)
- `app/static/css/<page_name>.css` - Page-specific styles for each page/feature
- Each page CSS imports theme.css for consistency

## Essential Conventions

For complete strategy development guidelines including filename/class mapping, strategy interface definition, and code templates, see [sources/STRATEGY_DEV_RULES.md](../sources/STRATEGY_DEV_RULES.md).

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
| `app/db/` | .db data files uploaded via web UI |
| `app/templates/` | Flask Jinja2 templates for web UI pages |
| `app/static/css/` | CSS stylesheets: `theme.css` (global) + page-specific files |
| `app/static/js/` | JavaScript for interactive components |
| `core/base_strategy.py` | Abstract `BaseStrategy` class and `TradeSignal` dataclass |
| `core/backtester.py` | `GenericBacktester`: runs strategy, tracks trades, computes metrics |
| `core/optimizer.py` | `StrategyOptimizer`: grid search over parameter ranges |
| `core/score_loader.py` | `ScoreDataLoader`: loads SQLite score data OR combined .db (OHLC+scores in one file) |
| `core/equity_plotter.py` | `EquityPlotter`: matplotlib-based equity curve + drawdown visualization |
| `scripts/` | Reusable CLI scripts for testing, validation, and standalone execution |
| `sources/` | Non-temporary documentation (STRATEGY_GUIDE.md, SCORE_DATA_INTEGRATION.md, etc.) |
| `requirements.txt` | Flask, matplotlib, SQLAlchemy, numpy, pandas, etc. |

---

## Common Development Tasks

### Create a New Strategy
1. Create file `app/strategies/your_strategy.py` with class `YourStrategy(BaseStrategy)` (../sources/STRATEGY_DEV_RULES.md)
2. Use web UI "Strategy Template" generator for boilerplate
3. Test via Backtest page (select strategy, upload combined .db file, run)

### Access Web UI
```bash
python run_server.py
# Open http://localhost:5000
```
---


## Testing & Validation

### CLI-Based Testing
When modifying any `core/` module (backtester, optimizer, data loaders), test via CLI scripts:

```bash
# Standalone backtest (outside web server)
python scripts/backtest_standalone.py

```
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

## Recommended Reading Order
1. **sources/STRATEGY_DEV_RULES.md** – Strategy development guidelines with examples
2. **core/base_strategy.py** – Interface definition
3. **core/backtester.py** – How trades are executed and metrics computed
4. **core/score_loader.py** – Score data and combined DB loading patterns
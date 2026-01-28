# Strategy Development Rules for AI Assistant

**Last Updated:** January 28, 2026
**Purpose:** Guidelines for AI-assisted strategy development, testing, and optimization in the backtesting platform.

---

## Core Architecture: Event-Driven Order Placement with Unified Data Structure

**Primary Mode: Event-Driven Execution**
- Strategies override `on_bar(self, data)` method - receives unified OHLCV+score bars
- Each bar contains: `timestamp`, `open`, `high`, `low`, `close`, `volume`, `score_1m`, `score_5m`, `score_15m`, `score_60m`
- Place orders via `self.buy(quantity, reason)` and `self.sell_short(quantity, reason)`
- Orders execute at **next bar's open** (realistic one-bar delay)
- No look-ahead bias - only see data up to current bar

**Unified Data Structure (January 28, 2026):**
```python
def on_bar(self, data: List[Dict[str, Any]]):
    """Receives unified bars with OHLCV + embedded scores."""
    current_bar = data[-1]  # Current bar
    close = current_bar['close']
    score_1m = current_bar.get('score_1m')  # Score directly in bar
    
    # Access previous bars for indicator calculation
    if len(data) >= 20:
        sma = sum(bar['close'] for bar in data[-20:]) / 20
```

**Order Execution Model:**
```python
# Bar N: Strategy logic runs
if condition:
    self.buy(quantity=3, reason='ENTRY')  # Order placed

# Bar N+1: Order executes at open price
# Position becomes 3 contracts long
```

**Legacy Mode (NOT RECOMMENDED):**
- Batch signal generation via `generate_signal()` - return empty list for event-driven strategies

---

## Core Principle: Use `core/` Modules, Don't Touch `app/`

### What You MUST Use
- **Core Backtesting Engine:** `core/backtester.py` (`GenericBacktester`)
- **Data Loading:** `core/data_loader.py` (`CSVDataLoader`)
- **Score Loading:** `core/score_loader.py` (`ScoreDataLoader`)
- **Base Strategy:** `core/base_strategy.py` (`BaseStrategy`, `TradeSignal`)
- **Optimizer:** `core/optimizer.py` (`StrategyOptimizer`)

### What You CANNOT Change
- **Web Application:** `app/app.py` - Flask routes, web logic, HTML rendering
- **Templates:** `app/templates/*.html` - Web UI templates
- **JavaScript/CSS:** `app/static/js/`, `app/static/css/` (unless explicitly requested)
- **Core Module Interfaces:** Don't break `core/` module APIs; strategies depend on them

### What You CAN Modify
- **Strategy Files:** `app/strategies/*.py` - This is your primary workspace
- **Test Scripts:** `scripts/*.py` - CLI test harnesses (follow cleanup rules)
- **Documentation:** `sources/*.md` - Strategy guides, process docs

---

## Strategy Development Workflow

### 0. Filename & Class Name Mapping (CRITICAL)

**Rule:** File → Class name conversion is mandatory for discovery
- File: `snake_case_strategy.py` → Class: `SnakeCaseStrategy`
- **Parts ≤ 3 characters:** Convert to ALL CAPS (e.g., `sma`, `mnq`, `atr` → `SMA`, `MNQ`, `ATR`)
- **Parts > 3 characters:** Capitalize first letter only (e.g., `simple`, `strategy` → `Simple`, `Strategy`)

**Examples:**
- `simple_sma_strategy.py` → `class SimpleSMAStrategy(BaseStrategy)` ✅
- `mnq_threshold_cross.py` → `class MNQThresholdCross(BaseStrategy)` ✅  
- `og_mnq_strategy.py` → `class OGMNQStrategy(BaseStrategy)` ✅
- `mnq_strategy.py` → `class MNQStrategy(BaseStrategy)` ✅

**Common Mistakes:**
- `mnq_strategy.py` with `class MnqStrategy` ❌ (should be `MNQStrategy`)
- `simple_sma_strategy.py` with `class SimpleSmaStrategy` ❌ (should be `SimpleSMAStrategy`)

**Why:** The web app uses `snake_to_pascal_case()` for automatic class loading:
```python
def snake_to_pascal_case(name):
    parts = name.split('_')
    return ''.join(part.upper() if len(part) <= 3 else part.capitalize() for part in parts)
```

**Verify:** Mismatch causes "Strategy class not found" errors

#### Order Placement API

**Buy Order (Long Entry or Short Exit):**
```python
self.buy(quantity=1, reason='ENTRY', exit_type='')
```
- `quantity`: Number of contracts/shares to buy
- `reason`: Exit reason label (e.g., 'TP1', 'TP2', 'SL', 'ENTRY', 'FORCE_CLOSE_EOD')
- `exit_type`: Optional tag for exit management (e.g., 'ATR')

**Sell Order (Short Entry or Long Exit):**
```python
self.sell_short(quantity=1, reason='EXIT', exit_type='')
```
- `quantity`: Number of contracts/shares to sell
- `reason`: Exit reason label
- `exit_type`: Optional tag

**CRITICAL Rules:**
- Orders execute at **next bar's open** (one-bar delay)
- Use named `reason` for all exits: 'TP1', 'TP2', 'TP3', 'SL', 'BREAKEVEN', 'FORCE_CLOSE_EOD'
- **Never use 'ENTRY' as exit reason** - causes logic errors

---

### 1. Use the Canonical CLI Test Harness

**Primary Testing Script:** `scripts/backtest_standalone.py`
- Mimics the web backtest process exactly
- Supports all web form parameters
- Uses `core/` modules directly
- Command-line interface for rapid iteration

**Usage Example (ONLY supported format):**
```bash
python scripts/backtest_standalone.py \
    --strategy mnq_threshold_cross \
    --data combined_market_data.db \
    --capital 50000 \
    --commission 0.0 \
    --slippage 0 \
```

### 2. Strategy File Structure

**Location:** `app/strategies/<strategy_name>.py`

**Required Components:**
```python
from core.base_strategy import BaseStrategy
from typing import List, Dict, Any, Optional

class MyStrategy(BaseStrategy):
    def setup(self):
        """Initialize parameters (called by __init__)."""
        # Extract parameters with defaults
        self.sma_period = self.params.get('sma_period', 20)
        
        # Internal state tracking
        self._entry_price = None
        self._position_direction = 0  # 1=long, -1=short, 0=flat
        
    def on_bar(self, price_bars: List[Dict[str, Any]], scores_data: Optional[List[Dict[str, Any]]] = None):
        """Event-driven logic called on every bar.
        
        Args:
            price_bars: OHLCV bars up to current timestamp (use price_bars[-1] for current)
            scores_data: Optional score records up to current timestamp (pre-filtered to 1m)
        """
        # 1. Guard: Need enough data
        if len(price_bars) < self.sma_period:
            return
            
        # 2. Get current bar
        current_bar = price_bars[-1]
        close = current_bar['close']
        timestamp = current_bar['timestamp']
        
        # 3. Calculate indicators on available data (NO LOOK-AHEAD)
        sma = sum(bar['close'] for bar in price_bars[-self.sma_period:]) / self.sma_period
        
        # 4. Entry logic (if flat)
        if self.position == 0:  # self.position tracks open contracts
            if close > sma:
                self.buy(quantity=1, reason='ENTRY')
                self._entry_price = close
                self._position_direction = 1
                
        # 5. Exit logic (if in position)
        elif self.position > 0:
            if close < sma:
                # Full exit
                if self._position_direction == 1:
                    self.sell_short(quantity=self.position, reason='EXIT')
                else:
                    self.buy(quantity=self.position, reason='EXIT')
                
                self._position_direction = 0
            
            # Force-close at session end
            if self.is_session_end(timestamp, early_close=False):
                if self._position_direction == 1:
                    self.sell_short(quantity=self.position, reason='FORCE_CLOSE_EOD')
                else:
                    self.buy(quantity=self.position, reason='FORCE_CLOSE_EOD')

    def generate_signal(self, prices_data, scores_data=None):
        """Legacy batch mode - return empty list for event-driven strategies."""
        return []
        
    def get_parameter_ranges(self):
        """Define optimization grid."""
        return {'sma_period': (10, 50, 5)}
```

### 3. Critical Strategy Requirements

#### Position Tracking Pattern

**Engine Position State (Single Source of Truth):**
- `self.engine.position`: Direction (0=flat, 1=long, -1=short)
- `self.position`: **READ-ONLY property** that returns `self.engine.position_size` (number of open contracts/shares)
- **NEVER manually set `self.position`** - it auto-updates via the engine

**Strategy Position State:**
```python
def setup(self):
    self._position_direction = 0  # Track direction: 1=long, -1=short, 0=flat
    self._entry_price = None      # Track entry price for exit logic
    self._tp1_hit = False          # Track partial exit flags
    # Note: self.position is automatically managed by the engine
```

**Key Change (January 20, 2026):**
- `self.position` is now a **@property** that reads from the engine
- Strategies should ONLY read `self.position`, never assign to it
- The backtester's unified `execute_exit` function handles all position updates

**Position State Transitions:**
```python
# Entry: Flat → Long (3 contracts)
if self.position == 0:
    self.buy(quantity=3, reason='ENTRY')
    self._position_direction = 1
    # After next bar: self.position automatically becomes 3

# Partial Exit: Long 3 → Long 2
if self.position == 3:
    self.sell_short(quantity=1, reason='TP1')
    # After next bar: self.position automatically becomes 2

# Full Exit: Long 2 → Flat
if self.position == 2:
    self.sell_short(quantity=self.position, reason='EXIT')  # Close all remaining
    self._position_direction = 0
    # After next bar: self.position automatically becomes 0
```

**CRITICAL: Do NOT manually set `self.position`**
- `self.position` is a read-only property (as of Jan 20, 2026)
- The engine automatically updates position size after each order execution
- Strategies only need to call `self.buy()` or `self.sell_short()` with the desired quantity

#### Position Sizing
- **Rule:** `get_position_size()` returns the total position size from params
- **Do NOT:** Multiply position size by number of TP levels
- **Why:** Backtester automatically splits position across TP levels

#### Exit Handling Patterns

**Pattern 1: Full Exit (Close Entire Position)**
```python
if exit_condition and self.position > 0:
    if self._position_direction == 1:  # Long position
        self.sell_short(quantity=self.position, reason='SL')
    else:  # Short position
        self.buy(quantity=self.position, reason='SL')
```

**Pattern 2: Partial Exits (Multiple TP Levels)**
```python
def setup(self):
    # Track which TP levels have been hit
    self._tp1_hit = False
    self._tp2_hit = False
    self._tp3_hit = False
    
    # Store TP levels (calculated at entry)
    self._tp1_level = 0.0
    self._tp2_level = 0.0
    self._tp3_level = 0.0

def on_bar(self, price_bars, scores_data):
    # Entry: 3 contracts
    if self.position == 0 and entry_condition:
        self.buy(quantity=3, reason='ENTRY')
        self._tp1_level = entry_price + 60  # Calculate TPs
        self._tp2_level = entry_price + 35
        self._tp3_level = entry_price + 25
        self._tp1_hit = False  # Reset flags
        self._tp2_hit = False
        self._tp3_hit = False
    
    # Exit: 1 contract at each TP level
    if self.position > 0 and self._position_direction == 1:
        high = current_bar['high']
        
        # Check TP1
        if high >= self._tp1_level and not self._tp1_hit:
            self.sell_short(quantity=1, reason='TP1')
            self._tp1_hit = True
        
        # Check TP2
        if high >= self._tp2_level and not self._tp2_hit:
            self.sell_short(quantity=1, reason='TP2')
            self._tp2_hit = True
        
        # Check TP3
        if high >= self._tp3_level and not self._tp3_hit:
            self.sell_short(quantity=1, reason='TP3')
            self._tp3_hit = True
```

**Pattern 3: Stop Loss Check**
```python
if self.position > 0:
    if self._position_direction == 1:  # Long
        if low <= self._sl_level:
            self.sell_short(quantity=self.position, reason='SL')
    else:  # Short
        if high >= self._sl_level:
            self.buy(quantity=self.position, reason='SL')
```

#### Score Data Usage Patterns

**Combined DB Format (ONLY Supported):**
- The system only accepts a single SQLite .db file as data input.
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
- Each row contains all price and score data for a single bar.
- The backtester extracts both price and score data from this table for all backtests and optimizations.
- Strategies receive both `price_bars` and `scores_data` in `on_bar()` as before, but all data is sourced from this unified table.

#### Session Management & Force-Close

**MNQ Trading Session (Sunday–Friday):**
- **Session Hours:** 5:00 PM Sunday to 4:00 PM Friday CT
- **Daily Halt:** 4:00 PM to 5:00 PM CT (no trading)
- **Force-Close Time:** 3:45 PM CT (regular), 12:00 PM CT (early close days)

**Implementation Pattern:**
```python
def on_bar(self, price_bars, scores_data):
    current_bar = price_bars[-1]
    timestamp = current_bar['timestamp']
    
    # Force-close at session end (if in position)
    if self.position > 0 and self.is_session_end(timestamp, early_close=False):
        if self._position_direction == 1:
            self.sell_short(quantity=self.position, reason='FORCE_CLOSE_EOD')
        else:
            self.buy(quantity=self.position, reason='FORCE_CLOSE_EOD')
```

**Helper Methods:**
- `self.is_session_end(timestamp, early_close)` - Returns True at force-close time
- `self.is_outside_session(timestamp)` - Returns True outside trading hours

**Early Close Detection:**
- Backtester automatically detects early close days (holidays)
- Forces position close at 11:55 AM CT on early close days
- Exit reason: 'EARLY_CLOSE'

#### Dynamic Indicator Calculation

**ATR Example (from og_mnq_strategy):**
```python
def _calculate_atr(self, data: List[Dict[str, Any]]) -> float:
    """Calculate Simple ATR for the current slice."""
    if len(data) <= self.atr_length:
        return 0.0
        
    true_ranges = []
    for i in range(len(data) - self.atr_length, len(data)):
        curr = data[i]
        prev = data[i-1]
        
        tr = max(
            curr['high'] - curr['low'],
            abs(curr['high'] - prev['close']),
            abs(curr['low'] - prev['close'])
        )
        true_ranges.append(tr)
        
    return sum(true_ranges) / len(true_ranges)

def on_bar(self, price_bars, scores_data):
    # Calculate ATR on available data
    atr_val = self._calculate_atr(price_bars)
    if atr_val <= 0:
        return
    
    # Use ATR for TP/SL calculation
    self._sl_level = entry_price - atr_val * self.sl_multiplier
    self._tp1_level = entry_price + atr_val * self.tp1_multiplier
```

---

## Complete Working Example: Simple SMA Crossover Strategy

```python
\"\"\"
Simple SMA Crossover Strategy
Entry: Price crosses above/below SMA
Exit: Opposite cross or session end
\"\"\"
from core.base_strategy import BaseStrategy
from typing import List, Dict, Any, Optional

class SimpleSMAStrategy(BaseStrategy):
    def setup(self):
        \"\"\"Initialize strategy parameters.\"\"\"
        # Parameters
        self.sma_period = int(self.params.get('sma_period', 20))
        
        # Position tracking
        self._position_direction = 0  # 1=long, -1=short, 0=flat
        self._entry_price = None
    
    def on_bar(self, price_bars: List[Dict[str, Any]], scores_data: Optional[List[Dict[str, Any]]] = None):
        \"\"\"Main strategy logic called on every bar.\"\"\"
        # Guard: Need enough data
        if len(price_bars) < self.sma_period + 1:
            return
        
        # Get current bar
        current_bar = price_bars[-1]
        close = current_bar['close']
        timestamp = current_bar['timestamp']
        
        # Calculate SMA on available data (no look-ahead)
        sma = sum(bar['close'] for bar in price_bars[-self.sma_period:]) / self.sma_period
        prev_close = price_bars[-2]['close']
        prev_sma = sum(bar['close'] for bar in price_bars[-self.sma_period-1:-1]) / self.sma_period
        
        # Entry logic (if flat)
        if self.position == 0:
            # Cross above SMA -> Long entry
            if prev_close <= prev_sma and close > sma:
                self.buy(quantity=1, reason='ENTRY')
                self._position_direction = 1
                self._entry_price = close
            
            # Cross below SMA -> Short entry
            elif prev_close >= prev_sma and close < sma:
                self.sell_short(quantity=1, reason='ENTRY')
                self._position_direction = -1
                self._entry_price = close
        
        # Exit logic (if in position)
        elif self.position > 0:
            # Long exit: Cross below SMA
            if self._position_direction == 1 and prev_close >= prev_sma and close < sma:
                self.sell_short(quantity=self.position, reason='EXIT')
                self._position_direction = 0
            
            # Short exit: Cross above SMA
            elif self._position_direction == -1 and prev_close <= prev_sma and close > sma:
                self.buy(quantity=self.position, reason='EXIT')
                self._position_direction = 0
            
            # Force-close at session end
            if self.is_session_end(timestamp, early_close=False):
                if self._position_direction == 1:
                    self.sell_short(quantity=self.position, reason='FORCE_CLOSE_EOD')
                else:
                    self.buy(quantity=self.position, reason='FORCE_CLOSE_EOD')
                self._position_direction = 0
    
    def generate_signal(self, prices_data, scores_data=None):
        \"\"\"Legacy batch mode - not used.\"\"\"
        return []
    
    def get_parameter_ranges(self):
        \"\"\"Parameter ranges for optimization.\"\"\"
        return {
            'sma_period': (10, 50, 5)
        }
```

**Key Features Demonstrated:**
1. ✓ Position tracking with `_position_direction`
2. ✓ Entry detection with crossover logic
3. ✓ Exit on opposite cross
4. ✓ Force-close at session end
5. ✓ Named exit reasons ('EXIT', 'FORCE_CLOSE_EOD')
6. ✓ No look-ahead bias (only uses available data)

---

## Testing & Validation Protocol

### Phase 1: CLI Development Testing
1. **Modify strategy file:** `app/strategies/<strategy>.py`
2. **Run CLI test:**
    ```bash
    python scripts/backtest_standalone.py --strategy <strategy> --data combined_market_data.db
    ```
3. **Check results:** Total trades, WR%, RR, return, max DD
4. **Iterate:** Adjust parameters, re-test via CLI

### Phase 2: Full-Dataset Optimization
1. **Use optimizer script:**
   ```python
   from core.optimizer import StrategyOptimizer
   optimizer = StrategyOptimizer(strategy_class, param_ranges)
   best_params = optimizer.optimize(prices, scores, initial_capital)
   ```
2. **Grid search:** Test parameter combinations via CLI
3. **Document results:** Best configs, performance metrics

### Phase 3: Production Deployment
1. **Update strategy defaults:** Set optimized parameters in `setup()`
2. **Update docstring:** Document entry/exit logic, performance targets
3. **Verify web interface:** Final web backtest with production config
4. **Document web form config:** Provide user with exact parameters to enter, e.g contracts, init equity...

---

## Performance Targets

### Current Project Goals
- **Win Rate (WR):** ≥ 55%
- **Risk/Reward Ratio (RR):** ≥ 1.0 (avg_win / avg_loss)
- **No Overnight Holding:** Force-close positions at configured session end
- **Drawdown:** Minimize max_drawdown while meeting WR/RR targets

### Metrics Calculation
- **WR:** `winning_trades / total_trades * 100%`
- **RR:** `avg_win / avg_loss` (from trade PnL)
- **Profit Factor:** `sum(wins) / sum(losses)`
- **Sharpe Ratio:** `(mean_return - risk_free_rate) / std_deviation_returns`

---

## Script Management Rules (from copilot-instructions.md)

### Temporary vs. Permanent Scripts
- **Keep (Permanent):**
  - `backtest_standalone.py` - Main CLI test harness
  - `test_no_overnight.py` - Session filter validation
  - `validate_strategy.py` - Comprehensive validation
  - `test_scores_loading.py` - Score data integration test
  
- **Delete (Temporary):**
  - One-off debug scripts (e.g., `debug_*.py`, `temp_*.py`)
  - Single-iteration tests (e.g., `test_quick_check.py`)
  - Exploration scripts after use (e.g., `optimize_full_dataset.py`)

### Cleanup Protocol
- **After each session:** Delete temporary test scripts
- **Never commit:** Temporary markdown files, debug outputs to repo root
- **Document permanent scripts:** Add docstrings explaining purpose and usage

---
## Optimization Best Practices

### Grid Search Strategy
1. **Start narrow:** Test 2-3 values per parameter (e.g., threshold: [92, 94, 96])
2. **Expand selectively:** Focus on parameters with largest impact
3. **Avoid combinatorial explosion:** 5 params × 5 values each = 3,125 tests
4. **Use full dataset:** Optimize on complete historical data, not subsets

### Parameter Selection
- **Entry Parameters:** Threshold, momentum bars, session filters
- **Exit Parameters:** SL points, TP1/TP2/TP3 points, breakeven trigger
- **Risk Parameters:** Position size, max drawdown limit

### Validation Protocol
1. **In-Sample:** Optimize on training period (e.g., 70% of data)
2. **Out-of-Sample:** Validate on test period (remaining 30%)
3. **Walk-Forward:** Rolling optimization windows to avoid overfitting
4. **Robustness Check:** Parameters should perform well across different market conditions

### Overfitting Detection Checklist

**Red Flags (High Overfitting Probability):**
- ❌ In-sample return **≫** out-of-sample return (e.g., 80% vs. 5%)
- ❌ In-sample Sharpe **>** 2.5 with out-of-sample Sharpe **< 0.5**
- ❌ Parameter sensitivity extreme (1-point change kills profitability)
- ❌ Win rate **> 80%** in-sample, **< 40%** out-of-sample
- ❌ Max drawdown **< 5%** in-sample, **> 50%** out-of-sample
- ❌ Strategy works **only on specific symbols/timeframes**, fails on others
- ❌ Optimal parameters at grid boundaries (suggests incomplete search)
- ❌ Too many parameters optimized relative to trades (param count > trades / 30)

**Green Flags (Low Overfitting Probability):**
- ✅ In-sample return ≈ out-of-sample return (within 10-20%)
- ✅ In-sample Sharpe ≈ out-of-sample Sharpe (both > 1.0 or both < 0.5)
- ✅ Win rate **50-65%** both periods (consistent)
- ✅ Max drawdown similar both periods (within 2-3x range)
- ✅ Parameter robustness: ±10% parameter change ≈ ±5-10% return change
- ✅ Strategy logic **generalizable** to new data/symbols
- ✅ Optimal parameters in **middle of grid** (room to adjust)
- ✅ Parameter count << number of trades

**Quantitative Overfitting Score (0-100, higher = more overfitting):**
```
Score = (IS_Sharpe / OOS_Sharpe) + 
        abs(IS_WinRate - OOS_WinRate) * 0.5 + 
        (OOS_MaxDD / IS_MaxDD) * 10

Interpretation:
0-20:   Low overfitting ✅ (production-ready)
20-50:  Moderate overfitting ⚠️  (needs validation)
50+:    High overfitting ❌ (likely curve-fitted, avoid production)
```

**How to Test:**
1. **Split data:** 70% training, 30% testing (chronological, no overlap)
2. **Optimize on 70%:** Run optimizer on training period only
3. **Test best params on 30%:** Apply winning parameters to test period
4. **Compare metrics:** Calculate overfitting score above
5. **Robustness test:** Shift data forward/backward 1-2 weeks, reoptimize
   - If best parameters change drastically → overfitted
   - If best parameters stable → robust

**Example Comparison:**
| Metric | In-Sample | Out-of-Sample | Overfitting Risk |
|--------|-----------|---------------|------------------|
| Return | 45% | 12% | 🔴 HIGH |
| Sharpe | 2.1 | 0.3 | 🔴 HIGH |
| Win Rate | 72% | 44% | 🔴 HIGH |
| Max DD | 8% | 35% | 🔴 HIGH |
| **Verdict** | — | — | **❌ NOT PRODUCTION READY** |

---

## File Organization

### Strategy Development
```
app/strategies/
├── mnq_threshold_cross.py    # Current strategy under development
├── mnq_momentum.py            # Alternative strategy (momentum-based)
└── mnq_strategy.py            # Legacy strategy

scripts/
├── backtest_standalone.py     # Main CLI test harness (USE THIS)
├── test_no_overnight.py       # Session filter validation
├── validate_strategy.py       # Comprehensive validation
└── test_scores_loading.py     # Score data integration test

sources/
├── STRATEGY_GUIDE.md          # User-facing strategy development guide
├── STRATEGY_DEV_RULES.md      # This file (AI development rules)
└── SCORE_DATA_INTEGRATION.md  # Dual-dataset pattern documentation
```

### Results Storage
```
app/results/backtests/         # Permanent web backtest results
app/temp_results/              # Temporary web results for comparison
```

---

## AI Assistant Workflow Summary

1. **Receive Request:** User asks to modify or optimize strategy
2. **Identify Scope:** What needs to change in `app/strategies/<strategy>.py`
3. **CLI Test First:** Run `scripts/backtest_standalone.py` to validate changes
4. **Compare Results:** Check CLI output vs. `app/temp_results/` JSON
5. **Iterate:** Adjust strategy code, re-test via CLI
6. **Document:** Update strategy docstring and this rules file if patterns change
7. **Cleanup:** Delete temporary test scripts, keep only reusable ones
8. **Report:** Provide user with final parameters and web form configuration

---

## Quick Reference: CLI Testing Commands

**Basic backtest (ONLY supported format):**
```bash
python scripts/backtest_standalone.py --strategy mnq_threshold_cross --data combined_market_data.db
```

**Custom parameters:**
```bash
python scripts/backtest_standalone.py \
    --strategy mnq_threshold_cross \
    --data combined_market_data.db \
    --capital 50000 \
    --commission 0.0 \
    --slippage 0 \
    --instrument futures \
    --point-value 2.0 \
    --tick-size 0.25
```

**Session filter test:**
```bash
python scripts/test_no_overnight.py
```

**Full validation:**
```bash
python scripts/validate_strategy.py
```

---
# Backtesting & Optimization System

A professional, modern web-based backtesting and optimization platform for trading strategies. Built with Flask and Python, designed for both stocks ($) and futures (points/ticks) trading with advanced analysis and parameter optimization capabilities.

## 🚀 Features

### Core Engine Features
- **Generic Architecture**: Works seamlessly with stocks and futures
- **Multiple Take-Profit Levels**: Up to 3 TP levels with partial position exits
- **Advanced Stop-Loss**: Configurable stops with slippage simulation and breakeven management
- **Parameter Optimization**: Automated grid search across parameter ranges
- **Comprehensive Metrics**: Sharpe ratio, max drawdown, profit factor, win rate, and more
- **Real Equity Curve Tracking**: Visualize account growth over time

### Web Interface
- **Modern Dark Theme**: Professional blue/deep blue color scheme
- **Responsive Design**: Works on desktop and tablet
- **Data Management**: Upload and manage multiple CSV data files
- **Strategy Management**: Upload, view, and test custom strategies
- **Backtest Runner**: Configure and run backtests with detailed reporting
- **Optimization Runner**: Grid search parameter optimization with visualization
- **Results Viewer**: Browse, compare, and analyze all results
- **Interactive Charts**: Equity curves, parameter impact analysis with Chart.js

### Data Format Support
- **Standard OHLCV**: `timestamp, open, high, low, close, volume`
- **Simplified Format**: `timestamp, price`
- **Trading Platform Format**: `<Date>, <Time>, <Open>, <High>, <Low>, <Close>, <Volume>`

## 📁 Project Structure

```
optimisation/
├── data/                             # Data directory
│   ├── app/                         # Flask web application
│   │   ├── templates/               # HTML templates (9 pages)
│   │   ├── static/
│   │   │   ├── css/                # Dark theme CSS
│   │   │   └── js/                 # JavaScript utilities
│   │   └── app.py                  # Main Flask application
│   ├── strategies/                  # Trading strategies
│   │   ├── mnq_strategy.py         # Example MNQ strategy
│   │   └── simple_ma_strategy.py   # Simple MA crossover example
│   └── db/               # User-uploaded CSV files
├── core/                            # Core engine (generic)
│   ├── base_strategy.py            # Abstract strategy interface
│   ├── backtester.py              # Generic backtesting engine
│   ├── optimizer.py                # Grid search optimizer
│   ├── data_loader.py              # Multi-format data loader
│   └── __init__.py
├── results/                         # Results storage
│   ├── backtests/                  # Backtest result JSON files
│   └── optimizations/              # Optimization result JSON files
├── db/                              # Legacy database files (optional)
├── run_server.py                    # Start Flask server
├── start_server.bat                 # Windows batch launcher
├── test_csv_format.py              # CSV format validation test
├── requirements.txt                 # Python dependencies
└── README.md                        # This file
```

## 🔧 Installation & Setup

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

**If requirements.txt is missing, install manually:**
```bash
pip install Flask==3.0.0 Werkzeug==3.0.0
```

### Step 2: Start the Web Server

**Command line (any OS):**
```bash
python run_server.py
```

### Step 3: Open in Browser
Navigate to: **http://localhost:5000**

You should see the modern blue-themed dashboard.

## 📖 Quick Start Guide

### 1. Upload Data

1. Click on **Data** in the navigation menu
2. Click "Choose File" and select your CSV
3. Supported formats:
   - Standard: `timestamp, open, high, low, close, volume`
   - Simplified: `timestamp, price`
   - Platform: `<Date>, <Time>, <Open>, <High>, <Low>, <Close>, <Volume>`
4. Click "Upload CSV"
5. View preview to confirm data loaded correctly

### 2. Create or Upload Strategy

**Option A - Upload existing strategy:**
1. Create a Python file inheriting from `BaseStrategy`
2. Go to **Strategies** page
3. Upload your `.py` file

**Option B - Use example strategy:**
- Pre-loaded `mnq_strategy.py` available by default
- Or `simple_ma_strategy.py` for learning

### 3. Run a Backtest

1. Go to **Backtest** page
2. Select your CSV file from dropdown
3. Select strategy from dropdown
4. Configure parameters:
   - **Start Date** / **End Date**: Period to test
   - **Initial Capital**: Starting account balance
   - **Commission %**: Per-trade cost
   - **Position Size**: Shares/contracts per trade
5. For **Futures**:
   - Set "Point Value" (e.g., $50 per point for MNQ)
   - Set "Tick Size" (e.g., 0.25 for MNQ)
6. Click "Run Backtest"
7. View results with equity curve and trade log

### 4. Optimize Parameters

1. Go to **Optimize** page
2. Select CSV file and strategy
3. Define parameter ranges to test:
   - Example: `fast_ma_period` from 10 to 30 (step 5)
4. Select optimization metric (return, Sharpe ratio, etc.)
5. Set maximum combinations to test
6. Click "Start Optimization"
7. View top parameter combinations and scatter plots

### 5. View & Compare Results

1. Go to **Results** page
2. Browse all backtest and optimization runs
3. Click any result to view:
   - Detailed performance metrics
   - Equity curve visualization
   - Trade-by-trade log
   - Best parameter combinations (for optimizations)
4. Compare results across different configurations

## 🎯 Creating Your Own Strategy

### Basic Structure

```python
from core.base_strategy import BaseStrategy, TradeSignal
from typing import Dict, Any

class MyStrategy(BaseStrategy):
    
    def generate_signal(self, current_price: float, history: list) -> TradeSignal:
        """
        Generate trading signals.
        
        Args:
            current_price: Current bar's close price
            history: List of previous bars (dict with ohlcv)
        
        Returns:
            TradeSignal with action, entry_price, tp_prices, sl_price
        """
        if len(history) < 20:
            return TradeSignal(action='HOLD')
        
        # Your logic here
        ma_short = sum([h['close'] for h in history[-10:]]) / 10
        ma_long = sum([h['close'] for h in history[-20:]]) / 20
        
        if ma_short > ma_long:
            return TradeSignal(
                action='BUY',
                entry_price=current_price,
                tp_prices=[current_price * 1.02, current_price * 1.04],
                sl_price=current_price * 0.98
            )
        
        return TradeSignal(action='HOLD')
    
    def get_parameter_ranges(self) -> Dict[str, Dict[str, Any]]:
        """Define parameters that can be optimized."""
        return {
            'ma_short': {'min': 5, 'max': 20, 'step': 5},
            'ma_long': {'min': 20, 'max': 50, 'step': 10},
            'tp_pct': {'min': 1.0, 'max': 5.0, 'step': 1.0},
            'sl_pct': {'min': 0.5, 'max': 2.0, 'step': 0.5}
        }
    
    def get_position_size(self, **kwargs) -> float:
        """Return position size in shares/contracts."""
        return kwargs.get('position_size', 1.0)
    
    def get_info(self) -> Dict[str, str]:
        """Strategy metadata."""
        return {
            'name': 'My Strategy',
            'version': '1.0',
            'description': 'Custom trading strategy'
        }
```

### Key Points
- Inherit from `BaseStrategy`
- Implement `generate_signal()` - returns `TradeSignal`
- Implement `get_parameter_ranges()` - for optimization
- Use `TradeSignal` with:
  - `action`: 'BUY', 'SELL', or 'HOLD'
  - `entry_price`: Entry level
  - `tp_prices`: List of take-profit levels (1-3)
  - `sl_price`: Stop-loss level

## 📊 Understanding Results

### Backtest Result Metrics
- **Total Return %**: Overall profit/loss percentage
- **Sharpe Ratio**: Risk-adjusted return (higher is better)
- **Max Drawdown %**: Largest peak-to-valley decline
- **Win Rate %**: Percentage of winning trades
- **Profit Factor**: Gross profit / gross loss
- **Avg Win/Loss**: Average gain vs average loss
- **Total Trades**: Number of trades executed

### Optimization Results
- **Top Combinations**: Best parameter sets ranked by metric
- **Parameter Impact**: See which parameters matter most
- **Performance Distribution**: Scatter plot of all results
- Exportable as JSON and CSV

## 🔍 Data Formats in Detail

### Format 1: Standard OHLCV
```csv
timestamp,open,high,low,close,volume
2026-01-16 01:01:00,22782.75,22783.75,22771.75,22772.5,1215
2026-01-16 01:02:00,22772.75,22786.5,22772.75,22781.25,1073
```

### Format 2: Simplified
```csv
timestamp,price
2026-01-16 01:01:00,22772.5
2026-01-16 01:02:00,22781.25
```

### Format 3: Trading Platform
```csv
<Date>,<Time>,<Open>,<High>,<Low>,<Close>,<Volume>
16/01/2026,01:01:00,22782.75,22783.75,22771.75,22772.5,1215
16/01/2026,01:02:00,22772.75,22786.5,22772.75,22781.25,1073
```

The system auto-detects the format and handles parsing automatically.

## ⚙️ Configuration

### For Stocks
```python
config = {
    'instrument_type': 'stock',
    'initial_capital': 100000,
    'commission_pct': 0.001,  # 0.1%
    'position_size': 100,  # shares
}
```

### For Futures (Example: MNQ - Micro Nasdaq)
```python
config = {
    'instrument_type': 'futures',
    'point_value': 2,  # $2 per point
    'tick_size': 0.25,  # Minimum price move
    'initial_capital': 50000,
    'commission_pct': 0.0005,
    'position_size': 1,  # contracts
}
```

## 🧪 Testing

To verify the CSV loader works with your format:
```bash
python test_csv_format.py
```

This loads `db/@MNQ_1M.csv` and validates:
- ✓ Data loads successfully
- ✓ All OHLCV fields present
- ✓ Proper data types
- ✓ Timestamps parsed correctly

## 🎨 Web Interface Features

### Dark Mode Theme
- Deep blue and cyan color scheme
- Easy on the eyes for extended use
- Modern, professional appearance
- Responsive layout for all screen sizes

### Interactive Elements
- **Drag & Drop**: Upload files easily
- **Real-time Forms**: Instant validation
- **Interactive Charts**: Zoom, pan, hover for details
- **Table Pagination**: Browse large datasets
- **Modal Previews**: View data before upload

### Navigation
- **Dashboard**: Overview and quick stats
- **Data**: Manage CSV files
- **Strategies**: View and upload trading strategies
- **Backtest**: Configure and run backtests
- **Optimize**: Set up parameter optimization runs
- **Results**: Browse all historical results

## 📈 Example Workflow

1. **Prepare data** → Upload `@MNQ_1M.csv` to Data page
2. **Choose strategy** → Select `mnq_strategy.py` from dropdown
3. **Configure backtest** → Set capital, dates, position size
4. **Run backtest** → Click "Run Backtest" and wait for results
5. **Review results** → View equity curve and metrics
6. **Optimize** → Go to Optimize, set parameter ranges
7. **View top params** → See winning parameter combinations
8. **Compare** → View multiple optimization results side-by-side

## 🚀 Advanced Features

### Multi Time-Frame Analysis
- Strategies can analyze multiple data streams
- Example: 1-minute entry signal with 5-minute confirmation

### Position Management
- Multiple take-profit levels with partial exits
- Stop-loss with configurable slippage
- Breakeven management for risk-free trading
- Maximum position sizing

### Optimization Features
- Grid search across parameter space
- Multiple ranking metrics (return, Sharpe, profit factor, etc.)
- Top-N result filtering
- Results persistence and comparison

### Data Validation
- Automatic format detection
- Data quality checks
- Missing value handling
- Timestamp validation

## 🔐 Security & Limitations

### Safety Features
- File upload validation and sanitization
- Secure filename handling
- Maximum file size limits (100MB)
- Sandboxed strategy execution

### Limitations
- Single-threaded (backtests run sequentially)
- In-memory data loading (good for <500K bars)
- No database persistence (use file exports)
- Local development mode (not production-ready)

## 📝 File Organization

### Adding New Strategies
1. Create Python file in `data/strategies/`
2. Inherit from `BaseStrategy`
3. Implement required methods
4. Upload via web interface
5. Use in backtests and optimizations

### Storing Data
- Upload CSVs via web interface
- Files saved to `data/db/`
- Can also copy files directly to folder
- Web interface auto-detects new files

### Results Storage
- Backtest results: `results/backtests/`
- Optimization results: `results/optimizations/`
- Each result is JSON for programmatic access
- Use Results page to browse and compare

## 🐛 Troubleshooting

### Server won't start
```bash
# Check Python is installed
python --version

# Try explicit port
python -c "from data.app.app import app; app.run(port=8000)"
```

### CSV upload fails
- Verify column headers match supported formats
- Check file size (max 100MB)
- Ensure no special characters in filenames
- Try with simple test CSV first

### Strategy upload fails
- Verify inheritance from `BaseStrategy`
- Check method signatures match interface
- Run strategy file directly to test imports
- Review error message in browser console

### Slow performance
- Reduce optimization parameter combinations
- Use shorter date ranges
- Check if other programs using system resources
- Try smaller CSV file first

### Charts not displaying
- Verify browser supports Chart.js
- Check browser console for JavaScript errors
- Ensure results data loaded successfully
- Try different browser

## � Documentation

### System Documentation
- **[CALLBACK_SYSTEM_GUIDE.md](CALLBACK_SYSTEM_GUIDE.md)** - Complete callback API reference, helper functions, and usage patterns
- **[CALLBACK_IMPLEMENTATION_SUMMARY.md](CALLBACK_IMPLEMENTATION_SUMMARY.md)** - Summary of callback system implementation and changes

### Strategy Development
- **[sources/STRATEGY_GUIDE.md](sources/STRATEGY_GUIDE.md)** - Comprehensive guide to writing strategies
- **[sources/SCORE_DATA_INTEGRATION.md](sources/SCORE_DATA_INTEGRATION.md)** - Integration with external score/indicator data
- **[sources/OPTIMIZATION_PROCESS.md](sources/OPTIMIZATION_PROCESS.md)** - Parameter optimization workflow

### Testing & Validation
- **scripts/comprehensive_system_test.py** - Full integration test
- **scripts/test_callback_sl_tp.py** - Callback system tests
- **scripts/demo_callback_exits.py** - Callback exit logic demo
- **scripts/test_mnq_threshold_cross.py** - Real-world strategy test

## 📚 Additional Resources

### Code Examples
- `app/strategies/mnq_strategy.py` - Full featured example
- `app/strategies/mnq_momentum.py` - Momentum strategy with ATR
- `app/strategies/mnq_threshold_cross.py` - Score-based threshold strategy
- `sources/STRATEGY_GUIDE.md` - Simple learning examples

### Architecture Documentation
The core system design:
- **BaseStrategy**: Abstract interface all strategies implement
- **GenericBacktester**: Engine that simulates trades
- **StrategyOptimizer**: Grid search parameter optimization
- **CSVDataLoader**: Multi-format data loader
- **callback_helpers**: Reusable callback factories for exit logic

### Design Patterns
- **Strategy Pattern**: For pluggable strategies
- **Template Method**: Backtester guides strategy execution
- **Factory Pattern**: Dynamic strategy loading + callback factories
- **Callback Pattern**: Flexible exit condition evaluation

## 🎓 Learning Path

1. **Start**: Read this README
2. **Try**: Run example with pre-loaded data
3. **Explore**: Check out `simple_ma_strategy.py`
4. **Experiment**: Create simple strategy variation
5. **Optimize**: Use optimization page to find best parameters
6. **Build**: Create your own strategy from scratch

## 🔮 Future Enhancements

Potential additions:
- [ ] Database backend (PostgreSQL/MongoDB)
- [ ] User authentication and accounts
- [ ] Walk-forward optimization
- [ ] Monte Carlo simulation
- [ ] Portfolio analysis (multiple strategies)
- [ ] Risk metrics (VaR, Sortino, Calmar)
- [ ] Paper trading integration
- [ ] Live trading gateways
- [ ] Export to Excel/PDF reports
- [ ] Cloud deployment options

## 💪 Summary

You now have a professional backtesting and optimization platform that:
- ✅ Supports stocks and futures
- ✅ Provides advanced parameter optimization
- ✅ Offers a modern, easy-to-use web interface
- ✅ Generates comprehensive trading analytics
- ✅ Allows unlimited strategy customization
- ✅ Stores and compares multiple results

**Ready to trade? Start the server and upload your data!**

---

## 📞 Support

For issues or questions:
1. Check the Troubleshooting section above
2. Review strategy implementation in `data/strategies/`
3. Check browser console for errors (F12)
4. Review Flask server output for errors
5. Verify Python version (3.8+) and packages

---
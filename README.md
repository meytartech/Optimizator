# Backtesting & Optimization System

A professional, modern web-based backtesting and optimization platform for trading strategies. Built with Flask and Python, designed for futures (points/ticks) trading with advanced analysis and parameter optimization capabilities.

## 🚀 Features

### Core Engine Features
- **Generic Architecture**: Works seamlessly with stocks and futures
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
│   │   └── app.py                  # Main Flask application
│   ├── strategies/                  # Trading strategies
│   │   ├── mnq_strategy.py         # Example MNQ strategy
│   │   └── simple_ma_strategy.py   # Simple MA crossover example
│   └── db/ 
├── core/                            # Core engine (generic)
│   ├── base_strategy.py            # Abstract strategy interface
│   ├── backtester.py              # Generic backtesting engine
│   ├── optimizer.py                # Grid search optimizer
│   ├── data_loader.py              # Multi-format data loader
│   └── __init__.py
├── results/                         # Results storage
│   ├── backtests/                  # Backtest result JSON files
│   └── optimizations/              # Optimization result JSON files
├── run_server.py                    # Start Flask server
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

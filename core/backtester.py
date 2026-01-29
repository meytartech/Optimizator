"""
Generic Backtesting Engine

Supports:
- Stocks (dollar-based) and Futures (point/tick-based)
- Multiple take-profit levels with partial exits
- Breakeven stop management
- Commission and slippage
- Comprehensive performance metrics
"""

from typing import Dict, List, Any, Optional, Callable, Tuple, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime, time
import json
import pytz

@dataclass
class Trade:
    """Represents a completed trade or partial exit."""
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    direction: int  # 1 for long, -1 for short
    quantity: int  # contracts or shares
    pnl: float
    pnl_percent: float
    is_win: bool
    exit_reason: str  # 'TP1', 'TP2', 'TP3', 'SL', 'SIGNAL', 'BREAKEVEN'
    stop_loss: Optional[float] = None  # Stop loss level for this trade
    take_profits: Optional[List[float]] = None  # Take profit levels for this trade
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class BacktestResult:
    """Complete backtest results with performance metrics."""
    # Configuration
    strategy_name: str
    start_date: str
    end_date: str
    initial_capital: float
    
    # Performance metrics
    final_equity: float
    total_return: float
    max_drawdown: float
    sharpe_ratio: float
    
    # Trade statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    avg_rr: float = 0.0
    unique_entries: int = 0
    total_commissions: float = 0.0
    
    # Time series data
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    trades: List[Trade] = field(default_factory=list)
    
    # Additional metrics
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    
    # Point-based metrics
    realized_points: float = 0.0
    max_drawdown_points: float = 0.0
    
    # Session analysis (IL timezone: Asia 01-10, Europe 10-16, NY 16-23)
    session_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Hourly analysis
    hourly_stats: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    
    # Exit reason statistics
    exit_reason_stats: Dict[str, int] = field(default_factory=dict)
    
    # Price data for trade chart viewer
    prices_data: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result['trades'] = [self._round_trade_dict(trade.to_dict()) for trade in self.trades]
        # NEVER include prices_data in serialized results (too large, loaded on-demand)
        result['prices_data'] = []
        result['prices_data_excluded'] = True
        # Round all numeric values to 2 decimal places
        return self._round_dict(result)
    
    @staticmethod
    def _round_dict(d: Dict, decimals: int = 2) -> Dict:
        """Recursively round all float values in dict to N decimal places."""
        if not isinstance(d, dict):
            return d
        
        rounded = {}
        for key, value in d.items():
            if isinstance(value, float):
                rounded[key] = round(value, decimals)
            elif isinstance(value, dict):
                rounded[key] = BacktestResult._round_dict(value, decimals)
            elif isinstance(value, list):
                rounded[key] = [BacktestResult._round_dict(item, decimals) if isinstance(item, dict) else (round(item, decimals) if isinstance(item, float) else item) for item in value]
            else:
                rounded[key] = value
        return rounded
    
    @staticmethod
    def _round_trade_dict(trade_dict: Dict, decimals: int = 2) -> Dict:
        """Round trade dictionary values to N decimal places."""
        rounded = {}
        for key, value in trade_dict.items():
            if isinstance(value, float):
                rounded[key] = round(value, decimals)
            elif isinstance(value, list) and value and isinstance(value[0], (int, float)):
                rounded[key] = [round(v, decimals) if isinstance(v, float) else v for v in value]
            else:
                rounded[key] = value
        return rounded
    
    def to_dict_lightweight(self, max_equity_points: int = 1000) -> Dict:
        """Convert to lightweight dictionary with sampled equity curve.
        
        Args:
            max_equity_points: Maximum equity curve points to include (0 = exclude entirely)
        
        Returns:
            Dictionary with sampled/excluded equity curve for faster serialization
        """
        result = asdict(self)
        result['trades'] = [self._round_trade_dict(trade.to_dict()) for trade in self.trades]
        
        # Sample equity curve if too large
        if max_equity_points > 0 and len(self.equity_curve) > max_equity_points:
            step = len(self.equity_curve) // max_equity_points
            result['equity_curve'] = self.equity_curve[::step]
            result['equity_curve_sampled'] = True
            result['equity_curve_original_length'] = len(self.equity_curve)
        elif max_equity_points == 0:
            # Exclude equity curve entirely for optimization runs
            result['equity_curve'] = []
            result['equity_curve_excluded'] = True
            result['equity_curve_original_length'] = len(self.equity_curve)
        
        # NEVER include prices_data in serialized results (too large, loaded on-demand)
        result['prices_data'] = []
        result['prices_data_excluded'] = True
        
        # Round all numeric values to 2 decimal places
        return self._round_dict(result)
    
    def save_to_json(self, filepath: str, lightweight: bool = False, max_equity_points: int = 1000):
        """Save results to JSON file.
        
        Args:
            filepath: Output file path
            lightweight: If True, use sampled equity curve
            max_equity_points: Max equity points when lightweight=True
        """
        with open(filepath, 'w', encoding='utf-8') as f:
            if lightweight:
                json.dump(self.to_dict_lightweight(max_equity_points), f, indent=2)
            else:
                json.dump(self.to_dict(), f, indent=2)


class GenericBacktester:
    """Generic backtesting engine for stocks and futures.
    
    Features:
    - Supports any strategy implementing BaseStrategy interface
    - Handles multiple take-profit levels with partial exits
    - Breakeven stop management
    - Commission and slippage modeling
    - Comprehensive performance tracking
    """
    
    def __init__(self, 
                 initial_capital: float = 100000.0,
                 commission_per_trade: float = 0.0,
                 slippage_ticks: int = 0,
                 max_bars_back: int = 100,
                 verbose: bool = False):
        """Initialize backtester.
        
        Args:
            initial_capital: Starting capital
            commission_per_trade: Commission per contract/share traded
            slippage_ticks: Slippage in ticks (applied to entries/exits)
            max_bars_back: Maximum number of bars to pass to on_bar (0 = all bars)
            verbose: Print progress messages
        """
        self.initial_capital = initial_capital
        self.commission_per_trade = commission_per_trade
        self.slippage_ticks = slippage_ticks
        self.max_bars_back = max_bars_back
        self.verbose = verbose
        
        # Engine state for strategies (TradeStation-style variables)
        self.pending_order = None
        self._trade_direction = 0  # 0=flat, 1=long, -1=short (like MarketPosition)
        self._entry_price = 0.0
        self._position_size = 0
        
    @property
    def position(self):
        """Current position direction (0=flat, 1=long, -1=short).
        
        Equivalent to TradeStation's MarketPosition variable.
        """
        return self._trade_direction
    
    @property
    def entry_price(self):
        """Price at which current position was entered.
        
        Returns 0.0 if no position is open.
        """
        return self._entry_price
    
    @property
    def position_size(self):
        """Number of contracts/shares in current position."""
        return self._position_size
    
    def _apply_slippage(self, price: float, direction: int, strategy) -> float:
        """Apply slippage to entry/exit price.
        
        Args:
            price: Base price (open/close)
            direction: 1 for long, -1 for short
            strategy: Strategy instance with tick_size attribute
            
        Returns:
            Price adjusted for slippage
        """
        if self.slippage_ticks == 0:
            return price
        
        tick_size = getattr(strategy, 'tick_size', 0.01)
        slippage_amount = self.slippage_ticks * tick_size
        
        # Buy orders suffer positive slippage (higher price)
        # Sell orders suffer negative slippage (lower price)
        return price + (slippage_amount * direction)

    def place_order(self, action: str, quantity: int = 1, exit_type: str = '', reason: str = ''):
        """Place an order to be executed on next bar.
        
        Args:
            action: 'buy' or 'sell'
            quantity: Position size
            exit_type: Exit management type (e.g., 'ATR', 'FIXED_POINTS')
        """
        self.pending_order = {
            'action': action, 
            'quantity': quantity,
            'exit_type': exit_type,
            'reason': reason
        }

    
    @staticmethod
    def _parse_datetime(time_str: str) -> Optional[datetime]:
        """Parse datetime from format: DD/MM/YYYY HH:MM:SS"""
        if not time_str:
            return None
        # Try multiple common formats including DB format with microseconds
        formats = [
            '%d/%m/%Y %H:%M:%S',
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S.%f%z',
            '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%S%z',
            '%Y-%m-%dT%H:%M:%S'
        ]
        for fmt in formats:
            try:
                return datetime.strptime(time_str, fmt)
            except Exception:
                continue

        # Fallback: try fromisoformat (handles many ISO variants and space-separated)
        try:
            return datetime.fromisoformat(time_str)
        except Exception:
            return None
    
    @staticmethod
    def _normalize_timestamp_for_comparison(timestamp: str) -> str:
        """Normalize timestamp to YYYY-MM-DD HH:MM:SS format for consistent string comparison.
        
        Handles both:
        - DD/MM/YYYY HH:MM:SS (price bars)
        - YYYY-MM-DDTHH:MM:SS-TZ:TZ or 2026-01-16T17:01:00-06:00 (ISO 8601 score data)
        
        Args:
            timestamp: Raw timestamp string in either format
            
        Returns:
            Normalized timestamp string in YYYY-MM-DD HH:MM:SS format for lexicographic comparison
        """
        if not timestamp:
            return ""

        # Try parsing with common formats (including microseconds and ISO variants)
        formats = [
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S.%f%z',
            '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%S%z',
            '%Y-%m-%dT%H:%M:%S',
            '%d/%m/%Y %H:%M:%S'
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(timestamp, fmt)
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                continue

        # Fallback to fromisoformat for some ISO-like variants
        try:
            dt = datetime.fromisoformat(timestamp)
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return timestamp
    
    def _detect_early_close_dates(self, data: List[Dict]) -> Dict[str, str]:
        """Detect dates with early market closes by finding last bar per date.
        
        Optimized: Iterates backwards to find last bar per date quickly,
        only parsing timestamps for last bars (not all 100K+ bars).
        
        Returns:
            Dict mapping YYYY-MM-DD -> last_bar_time (HH:MM) for early close dates
            (dates where last bar is before 4:00 PM CT, indicating early session close)
        """
        if not data:
            return {}
        
        early_close_dates = {}  # YYYY-MM-DD -> HH:MM
        seen_dates = set()
        
        # Iterate backwards - data is chronologically sorted, so we hit last bar of each date first
        for bar in reversed(data):
            timestamp = bar.get('timestamp', '')
            if not timestamp:
                continue
            
            # Extract date string without conversion (DD/MM/YYYY from "DD/MM/YYYY HH:MM:SS")
            try:
                parts = timestamp.split(' ')
                date_str = parts[0]  # "DD/MM/YYYY"
                time_str = parts[1] if len(parts) > 1 else ""  # "HH:MM:SS"
                if date_str.count('/') != 2:
                    continue
            except:
                continue
            
            # Skip if we've already processed this date
            if date_str in seen_dates:
                continue
            
            seen_dates.add(date_str)
            
            # Parse only this timestamp to check if it's an early close
            bar_dt = self._parse_datetime(timestamp)
            if bar_dt:
                # Early close: last bar is before 4:00 PM CT (16:00)
                if bar_dt.hour < 16 or (bar_dt.hour == 16 and bar_dt.minute == 0):
                    # Store as YYYY-MM-DD -> HH:MM
                    date_key = bar_dt.strftime('%Y-%m-%d')
                    time_key = bar_dt.strftime('%H:%M')
                    early_close_dates[date_key] = time_key
        
        return early_close_dates
    
    def run(self, strategy, data: List[Dict[str, Any]]) -> BacktestResult:
        """Run backtest using event-driven mode.
        
        Args:
            strategy: Strategy instance (must inherit from BaseStrategy)
            data: List of unified bars with embedded score fields
                  (timestamp, open, high, low, close, score_1m, score_5m, score_15m, score_60m)
        Returns:
            BacktestResult with complete performance metrics
        """
        # Inject engine into strategy
        strategy.engine = self
        
        if self.verbose:
            print(f"Starting backtest: {strategy.name}")
            print(f"Execution mode: Event-Driven (on_bar)")
            print(f"Initial Capital: ${self.initial_capital:,.2f}")
            print(f"Data points: {len(data)}")
            print(f"Max bars back: {self.max_bars_back if self.max_bars_back > 0 else 'all'}")
        
        # Detect early close dates (holiday early closes) to force close positions earlier
        early_close_dates = self._detect_early_close_dates(data)
        if self.verbose and early_close_dates:
            print(f"Detected {len(early_close_dates)} early close dates")
            for date_key, close_time in sorted(early_close_dates.items())[:5]:
                print(f"  {date_key}: last bar at {close_time}")
        
        # Initialize state
        equity = self.initial_capital
        equity_curve = []
        trades = []
        
        # Position tracking
        self._trade_direction = 0
        self._entry_price = 0.0
        position_size = 0
        entry_time = None
        remaining_quantity = 0
        exit_type = ''
        
        # Statistics
        wins = []
        losses = []
        consecutive_wins = 0
        consecutive_losses = 0
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        unique_entries = 0
        total_commissions = 0.0
        peak_equity = equity
        max_drawdown = 0.0
        
        # Clear any pending orders
        self.pending_order = None
        
        equity_curve.append({
                    'timestamp': "",
                    'equity': equity,
                    'tradeDirection': 0
                })

        # -------------------------------------------------------------------------
        # Helper: Unified Exit Logic (Partial & Full)
        # -------------------------------------------------------------------------
        def execute_exit(qty_to_close: int, exit_price: float, exit_reason: str, ts: str):
            """Execute an exit trade (partial or full) and update state."""
            nonlocal equity, total_commissions, remaining_quantity, entry_time
            nonlocal consecutive_wins, consecutive_losses, max_consecutive_wins, max_consecutive_losses
            
            # 1. Calculate PnL and Commission
            pnl = self._calculate_pnl(self._entry_price, exit_price, qty_to_close, self._trade_direction, strategy)
            pnl_percent = ((exit_price - self._entry_price) / self._entry_price) * self._trade_direction * 100
            
            exit_commission = self.commission_per_trade * qty_to_close
            total_commissions += exit_commission
            equity += pnl

            # 2. Record Trade
            trade = Trade(
                entry_time=entry_time,
                exit_time=ts,
                entry_price=self._entry_price,
                exit_price=exit_price,
                direction=self._trade_direction,
                quantity=qty_to_close,
                pnl=pnl,
                pnl_percent=pnl_percent,
                is_win=pnl > 0,
                exit_reason=exit_reason,
                stop_loss=None,    
                take_profits=None 
            )
            trades.append(trade)

            # 3. Update Statistics
            if trade.is_win:
                wins.append(trade.pnl)
                consecutive_wins += 1
                consecutive_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, consecutive_wins)
            else:
                losses.append(abs(trade.pnl))
                consecutive_losses += 1
                consecutive_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)

            # 4. Update Position State (The "One Case For All" Logic)
            remaining_quantity -= qty_to_close
            self._position_size = remaining_quantity
            # strategy.position is now a property referencing self._position_size
            
            # If fully closed, reset engine state
            if remaining_quantity <= 0:
                self._trade_direction = 0
                self._entry_price = 0.0
                self._position_size = 0
                entry_time = None
                remaining_quantity = 0 # Ensure no negative
                if self.verbose:
                    # Optional: Log full closure
                    pass

        for i, bar in enumerate(data):
            # Cache bar fields to avoid repeated dict.get() calls (3-5x per bar)
            timestamp =  bar["timestamp"]
            open_price = bar["open"]

            # Convert timestamp string to datetime (only if needed for session checks)
            bar_dt = None
            bar_time = None
            bar_date = None
            
            # Lazy timestamp parsing: only parse if we need it for session logic
            # Skip parsing if no position and no pending order (most common case)
            if self._trade_direction != 0 or self.pending_order:
                bar_dt = self._parse_datetime(timestamp)
                bar_time = bar_dt.time() if bar_dt else None
                bar_date = bar_dt.strftime('%Y-%m-%d') if bar_dt else None
            
            # Check if today is an early close day (holiday)
            is_early_close_day = bar_date in early_close_dates
            
            # Dynamic force-close time: 1 minute before the last bar time
            force_close_time = None
            trading_halt_time = None
            
            if is_early_close_day and bar_date in early_close_dates:
                # Get the last bar time (e.g., "11:55")
                last_bar_time_str = early_close_dates[bar_date]  # HH:MM
                try:
                    lh, lm = map(int, last_bar_time_str.split(':'))
                    force_close_time = time(lh, lm)
                    
                    # No new trades 15 minutes before close (e.g., if close is 11:55, block after 11:40)
                    if lm >= 15:
                        trading_halt_time = time(lh, lm - 15)
                    else:
                        trading_halt_time = time(lh - 1, lm + 60 - 15)
                except:
                    pass
            
            # EARLY CLOSE: Force-close all positions at 1 minute before close time on early close days
            if force_close_time and is_early_close_day and bar_time and bar_time >= force_close_time and self._trade_direction != 0 and remaining_quantity > 0:
                # UNIFIED EXIT: Close entire remaining quantity
                if self.verbose:
                    print(f"EARLY CLOSE: Forced position close at {timestamp} on holiday")
                execute_exit(remaining_quantity, open_price, 'EARLY_CLOSE', timestamp)
            
            # Block new trades based on market session
            is_new_trade_allowed = False
            if is_early_close_day and trading_halt_time:
                # Block new trades 15 min before early close
                is_new_trade_allowed = bar_time and bar_time >= trading_halt_time
            else:
                # Normal trading hours: block new trades from 15:40 to 17:00 CT (daily halt 16:00-17:00)
                is_new_trade_allowed = bar_time and time(15, 40) <= bar_time < time(17, 0)
            
            # ===================================================
            # PHASE 1: FILL PENDING ORDERS (Next-Bar Execution)
            # ===================================================
            # Allow opposite-direction exit orders during restricted sessions
            is_exit_order = False
            if self.pending_order and self._trade_direction != 0:
                act = self.pending_order.get('action')
                if (act == 'buy' and self._trade_direction == -1) or (act == 'sell' and self._trade_direction == 1):
                    is_exit_order = True
            can_execute = self.pending_order is not None and (not is_new_trade_allowed or is_exit_order)

            if self.pending_order and len(trades) < 5:
                # Debug logging removed
                pass

            if can_execute:
                action = self.pending_order.get('action')
                qty = self.pending_order.get('quantity', 1)
                exit_type = self.pending_order.get('exit_type', '')
                reason = self.pending_order.get('reason', '')
                
                # Execution Logic
                if action in ('buy', 'sell') and self._trade_direction != 0:
                    # Check if this is an exit order (TP/SL/etc) or an entry order
                    is_exit_reason = reason in ('TP1', 'TP2', 'TP3', 'SL', 'BREAKEVEN', 'EXIT', 'FORCE_CLOSE_EOD')
                    desired_dir = 1 if action == 'buy' else -1
                    
                    # Process exits (both opposite and same direction), ignore new entries
                    if is_exit_reason:
                        # This is a legitimate exit order - process it (opposite OR same direction)
                        qty_to_close = max(0, min(qty, remaining_quantity))
                        if qty_to_close > 0:
                            # UNIFIED EXIT: Close specific quantity
                            execute_exit(qty_to_close, open_price, reason, timestamp)
                    else:
                        # New entry signal while in position - IGNORE (no reversals, no scale-in)
                        pass

                elif action in ('buy', 'sell'):
                    desired_dir = 1 if action == 'buy' else -1
                    if self._trade_direction == 0:
                        # Open New Position
                        self._trade_direction = desired_dir
                        
                        # Apply slippage
                        exec_price = self._apply_slippage(open_price, desired_dir, strategy)
                        self._entry_price = exec_price
                        entry_time = timestamp
                        
                        # Update position size
                        current_qty = qty if qty > 0 else strategy.get_position_size(equity, exec_price)
                        position_size = int(current_qty)
                        remaining_quantity = position_size
                        self._position_size = position_size
                        # strategy.position automatically reflects position_size
                        
                        # Commission
                        entry_commission = self.commission_per_trade * position_size
                        equity -= entry_commission
                        total_commissions += entry_commission
                        unique_entries += 1
                        
                        if self.verbose and len(trades) % 10 == 0:
                            print(f"Trade #{len(trades)+1} Entry: {timestamp} {action.upper()} @ {exec_price}")

                self.pending_order = None

            # ===================================================
            # PHASE 2: No implicit exits; strategy must place exit orders
            # ===================================================
            
            if self._trade_direction != 0 and remaining_quantity <= 0:
                self._trade_direction = 0
                self._entry_price = 0.0
                self._position_size = 0
                # strategy.position auto-updates
                position_size = 0
                entry_time = None
                exit_type = ''

            # ===================================================
            # PHASE 3: STRATEGY LOGIC
            # ===================================================
            # Pass ONLY data up to current bar (no look-ahead)
            
            if not is_new_trade_allowed or self._trade_direction != 0:
                # Slice data to last max_bars_back bars (0 = all bars)
                if self.max_bars_back > 0:
                    bars_slice = data[max(0, i+1-self.max_bars_back):i+1]
                else:
                    bars_slice = data[:i+1]
                
                # Pass unified data list to strategy (contains price + score columns)
                strategy.on_bar(bars_slice)
            elif self.verbose and i < 100:
                # Log when on_bar is skipped due to no_new_trades filter
                print(f"DEBUG: Skipping on_bar at {timestamp} (no_new_trades={is_new_trade_allowed}, position={self._trade_direction})")
                
            # ===================================================
            # PHASE 4: UPDATE METRICS & EQUITY CURVE
            # ===================================================
            last_point = equity_curve[-1]
            if last_point.get('equity') != equity or last_point.get('tradeDirection') != self._trade_direction:
                equity_curve.append({
                    'timestamp': timestamp,
                    'equity': equity,
                    'tradeDirection': self._trade_direction
                })
            
            peak_equity = max(peak_equity, equity)
            drawdown = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0
            max_drawdown = max(max_drawdown, drawdown * 100)


        # Calculate final metrics
        equity_curve = equity_curve[1:]
        total_return = (equity - self.initial_capital) / self.initial_capital * 100
        win_rate = (len(wins) / len(trades) * 100) if trades else 0
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        
        sum_losses = sum(losses)
        if sum_losses > 0:
            profit_factor = min(sum(wins) / sum_losses, 999.0)
        else:
            profit_factor = 999.0 if wins else 0.0
        
        # Calculate avg_rr as average reward/risk ratio across all trades
        # Use actual trade PnL to derive reward/risk from wins and losses
        avg_rr = (avg_win / avg_loss) if (avg_loss > 0 and avg_win > 0) else (avg_win / max(avg_loss, 0.01))
        
        realized_points = 0.0
        max_dd_points = 0.0
        peak_points = 0.0
        
        for trade in trades:
            qty = trade.quantity if getattr(trade, 'quantity', 0) else 1
            if strategy.instrument_type == 'futures':
                denom = max(strategy.point_value * qty, 1e-9)
                points = trade.pnl / denom
            else:
                points = trade.pnl / qty
            realized_points += points
            
            peak_points = max(peak_points, realized_points)
            dd_points = peak_points - realized_points
            max_dd_points = max(max_dd_points, dd_points)
        
        session_stats = self._calculate_session_stats(trades)
        hourly_stats = self._calculate_hourly_stats(trades)
        
        exit_reason_stats = {}
        for trade in trades:
            reason = trade.exit_reason
            exit_reason_stats[reason] = exit_reason_stats.get(reason, 0) + 1
        
        returns = []
        for i in range(1, len(equity_curve)):
            ret = (equity_curve[i]['equity'] - equity_curve[i-1]['equity']) / equity_curve[i-1]['equity']
            returns.append(ret)
        
        if returns:
            avg_return = sum(returns) / len(returns)
            std_return = (sum((r - avg_return)**2 for r in returns) / len(returns))**0.5
            sharpe_ratio = (avg_return / std_return * (252**0.5)) if std_return > 0 else 0
        else:
            sharpe_ratio = 0
        
        start_date = data[0].get('timestamp', '') if data else ''
        end_date = data[-1].get('timestamp', '') if data else ''
        
        result = BacktestResult(
            strategy_name=strategy.name,
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_equity=equity,
            total_return=total_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            total_trades=len(trades),
            unique_entries=unique_entries,
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            avg_rr=avg_rr,
            equity_curve=equity_curve,
            trades=trades,
            total_commissions=total_commissions,
            max_consecutive_wins=max_consecutive_wins,
            max_consecutive_losses=max_consecutive_losses,
            largest_win=max(wins) if wins else 0,
            largest_loss=max(losses) if losses else 0,
            realized_points=realized_points,
            max_drawdown_points=max_dd_points,
            session_stats=session_stats,
            hourly_stats=hourly_stats,
            exit_reason_stats=exit_reason_stats,
            prices_data=data
        )
        
        if self.verbose:
            print(f"\n" + "="*70)
            print(f"BACKTEST COMPLETE")
            print(f"="*70)
            print(f"Final Equity: ${equity:,.2f}")
            print(f"Total Return: {total_return:.2f}%")
            print(f"Total Trades: {len(trades)}")
            print(f"Win Rate: {win_rate:.2f}%")
            print(f"Max Drawdown: {max_drawdown:.2f}%")
            print(f"Profit Factor: {profit_factor:.2f}")
            print(f"="*70)
        
        return result
    
    def _calculate_pnl(self, entry_price, exit_price, quantity, position, strategy):
        """Calculate PnL for a trade."""
        price_diff = (exit_price - entry_price) * position
        
        if strategy.instrument_type == 'futures':
            # Futures: PnL = (price difference in points) * point value * quantity
            pnl = price_diff * strategy.point_value * quantity
        else:
            # Stocks: PnL = price difference * quantity
            pnl = price_diff * quantity
        
        # Subtract commission (tracking is done separately in run method)
        pnl -= self.commission_per_trade * quantity
        
        return pnl
    
    def _calculate_session_stats(self, trades: List[Trade]) -> Dict[str, Dict[str, Any]]:
        """Calculate statistics by trading session (Chicago timezone - MNQ session times).
        
        Sessions (Chicago Time):
        - Asia: 18:00-00:00 CT (6:00 PM to midnight)
        - Europe: 02:00- 08:30 CT (2:00 AM to 8:30 AM)
        - New York: 08:30-15:00 CT (8:30 AM to 3:00 PM)
        """
        sessions = {
            'Asia': {'trades': [], 'wins': 0, 'losses': 0},
            'Europe': {'trades': [], 'wins': 0, 'losses': 0},
            'New York': {'trades': [], 'wins': 0, 'losses': 0}
        }
        
        
        for trade in trades:
            try:
                # Parse entry time - normalize commas to spaces first
                time_str = trade.entry_time.replace(',', ' ')
                
                dt = None
                for fmt in ['%d/%m/%Y %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S']:
                    try:
                        dt = datetime.strptime(time_str, fmt)
                        break
                    except:
                        continue
                
                if not dt:
                    continue
                
                
                hour = dt.hour
                minute = dt.minute
                
                # Classify by session (Chicago time)
                # Asia: 18:00-00:00 CT (6 PM - midnight)
                # Europe: 02:00-08:30 CT (2 AM - 8:30 AM)
                # New York: 08:30-15:00 CT (8:30 AM - 3 PM)
                if 18 <= hour < 24:
                    session = 'Asia'
                elif 2 <= hour < 8 or (hour == 8 and minute < 30):
                    session = 'Europe'
                elif (hour == 8 and minute >= 30) or (9 <= hour < 15):
                    session = 'New York'
                else:
                    continue
                
                sessions[session]['trades'].append(trade)
                if trade.is_win:
                    sessions[session]['wins'] += 1
                else:
                    sessions[session]['losses'] += 1
            except:
                continue
        
        # Calculate win rates and remove non-serializable trade lists
        result = {}
        for session in sessions:
            total = len(sessions[session]['trades'])
            wins = sessions[session]['wins']
            losses = sessions[session]['losses']
            result[session] = {
                'total': total,
                'wins': wins,
                'losses': losses,
                'win_rate': (wins / total * 100) if total > 0 else 0
            }
        
        return result
    
    def _calculate_hourly_stats(self, trades: List[Trade]) -> Dict[int, Dict[str, Any]]:
        """Calculate success rate by hour of day (Chicago timezone)."""
        hourly = {}
        chicago_tz = pytz.timezone('America/Chicago')
        
        for trade in trades:
            try:
                # Parse entry time - normalize commas to spaces first
                time_str = trade.entry_time.replace(',', ' ')
                
                dt = None
                for fmt in ['%d/%m/%Y %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S']:
                    try:
                        dt = datetime.strptime(time_str, fmt)
                        break
                    except:
                        continue
                
                if not dt:
                    continue
                
                # Assume UTC and convert to Chicago time
                dt_utc = pytz.UTC.localize(dt)
                dt_chicago = dt_utc.astimezone(chicago_tz)
                hour = dt_chicago.hour
                
                if hour not in hourly:
                    hourly[hour] = {'trades': 0, 'wins': 0, 'losses': 0}
                
                hourly[hour]['trades'] += 1
                if trade.is_win:
                    hourly[hour]['wins'] += 1
                else:
                    hourly[hour]['losses'] += 1
            except:
                continue
        
        # Calculate win rates
        for hour in hourly:
            total = hourly[hour]['trades']
            wins = hourly[hour]['wins']
            hourly[hour]['win_rate'] = (wins / total * 100) if total > 0 else 0
        
        return hourly

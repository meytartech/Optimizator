"""
Base Strategy Interface

All trading strategies must inherit from BaseStrategy and implement required methods.
Supports stocks ($) and futures (points/ticks) with configurable multi-TP/SL/breakeven.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Callable, Union, Tuple
from dataclasses import dataclass


# ============================================================
# Callback Function Signature Template
# ============================================================
# 
# All SL/TP callbacks must follow this signature:
#
#   def callback(bar: Dict[str, Any], 
#                entry_price: float, 
#                position: int, 
#                idx: Optional[int]) -> Union[bool, Tuple[bool, float]]:
#       # Return False if not hit
#       # Return True if hit (backtester uses conservative fill)
#       # Return (True, price) if hit at specific price
#
# Each strategy implements the specific callbacks it needs.
# ============================================================

@dataclass
class TradeSignal:
    """Represents a trading signal with entry and exit rules.
    
    Stop loss, take profits, and breakeven trigger must be callback functions with signature:
    fn(bar: Dict, entry_price: float, position: int, idx: Optional[int]) -> Union[bool, Tuple[bool, float]]
    
    Callbacks should return:
    - False -> not hit
    - True -> hit, backtester uses conservative fill (bar.low for long SL, bar.high for short SL, etc.)
    - (True, price) -> hit and use provided exit price
    """
    signal: int  # 1 for long, -1 for short, 0 for no signal
    entry_price: float
    timestamp: str  # ISO format timestamp when this signal should be executed
    stop_loss: Optional[Callable[[Dict[str, Any], float, int, Optional[int]], Union[bool, Tuple[bool, float]]]] = None
    take_profits: Optional[List[Callable[[Dict[str, Any], float, int, Optional[int]], Union[bool, Tuple[bool, float]]]]] = None
    breakeven_trigger: Optional[Callable[[Dict[str, Any], float, int, Optional[int]], Union[bool, Tuple[bool, float]]]] = None


class BaseStrategy(ABC):
    """Base class for all trading strategies.
    
    Key Features:
    - Generic for stocks and futures
    - Support for multiple take-profit levels
    - Breakeven management
    - Flexible parameter configuration
    - Metadata tracking
    """
    
    def __init__(self, params: Optional[Dict[str, Any]] = None):
        """Initialize strategy with parameters.
        
        Args:
            params: Dictionary of strategy parameters for optimization/configuration
        """
        self.params = params or {}
        self.name = self.__class__.__name__
        
        # Generic contract specifications (override in subclass)
        self.point_value = self.params.get('point_value', 1.0)  # $ per point (futures) or 1.0 for stocks
        self.tick_size = self.params.get('tick_size', 0.01)     # Minimum price movement
        self.instrument_type = self.params.get('instrument_type', 'stock')  # 'stock' or 'futures'
        
        # Engine reference (set by backtester)
        self.engine = None
        self.scores_data = None  # Set by backtester if available
        
        self.setup()
    
    @property
    def position(self) -> int:
        """Current position size (delegated to engine).
        
        Returns:
            Number of open contracts/shares.
        """
        if self.engine:
            return self.engine.position_size
        return 0
    
    @position.setter
    def position(self, value: int):
        """No-op setter to maintain backward compatibility with old code that tries to set self.position.
        
        The engine is the source of truth for position size.
        """
        pass
    
    def setup(self):
        """Initialize strategy-specific variables. Override in subclass."""
        pass

    def on_bar(self, data: List[Dict[str, Any]], scores_data: Optional[List[Dict[str, Any]]] = None):
        """Called on every bar with available data up to that point.
        
        This is the main entry point for event-driven strategy logic.
        The strategy only sees data up to the current bar (no look-ahead).
        
        Args:
            data: List of OHLCV bars up to and including current bar
            scores_data: Optional list of score records up to current timestamp
        
        Example:
            def on_bar(self, data, scores_data=None):
                if len(data) < 20:
                    return
                
                current_bar = data[-1]
                close = current_bar['close']
                
                # Calculate indicators using only data up to current bar
                sma = sum(bar['close'] for bar in data[-20:]) / 20
                
                # Optional: Use score data if available
                if scores_data:
                    current_score = scores_data[-1].get('score', 0)
                
                # Check position and place orders
                if close > sma and self.engine.position == 0:
                    self.buy(quantity=1)
                elif close < sma and self.engine.position == 1:
                    self.exit_position()
        """
        pass

    def buy(self, quantity: int = 1, reason: str = '', exit_type: str = ''):
        """Place a buy order for the next bar open.
        
        Automatically updates position tracking:
        - If flat: sets position = quantity (new long entry)
        - If short: reduces position by quantity (partial/full exit)
        - If long: reduces position by quantity (partial/full exit)

        Args:
            quantity: Number of contracts/shares
            reason: Named reason for action (e.g., 'TP1', 'SL', 'FORCE_CLOSE_EOD')
            exit_type: Optional exit management tag (e.g., 'ATR')
        """
        if hasattr(self, 'engine') and self.engine:
            # Position tracking is now handled automatically via the engine property
            # No manual update of self.position needed
            
            self.engine.place_order('buy', quantity, exit_type, reason)

    def sell_short(self, quantity: int = 1, reason: str = '', exit_type: str = ''):
        """Place a sell order for the next bar open.
        
        Automatically updates position tracking:
        - If flat: sets position = quantity (new short entry)
        - If long: reduces position by quantity (partial/full exit)
        - If short: reduces position by quantity (partial/full exit)

        Args:
            quantity: Number of contracts/shares
            reason: Named reason for action (e.g., 'TP1', 'SL', 'FORCE_CLOSE_EOD')
            exit_type: Optional exit management tag (e.g., 'ATR')
        """
        if hasattr(self, 'engine') and self.engine:
            # Position tracking is now handled automatically via the engine property
            # No manual update of self.position needed
            
            self.engine.place_order('sell', quantity, exit_type, reason)

    # Exits are expressed via buy/sell with quantity and named reasons.
    
    def is_session_end(self, timestamp: str, early_close: bool = False) -> bool:
        """Check if current time is session end (force close time).
        
        MNQ Session: 5:00 PM Sunday to 4:00 PM Friday CT
        Force close: 3:45 PM CT on regular days, 12:00 PM CT on early close days
        
        Args:
            timestamp: Bar timestamp (format: 'DD/MM/YYYY HH:MM:SS')
            early_close: True if today is an early close day
            
        Returns:
            True if at force close time
        """
        try:
            from datetime import datetime, time
            dt = datetime.strptime(timestamp, '%d/%m/%Y %H:%M:%S')
            bar_time = dt.time()
            
            if early_close:
                return bar_time == time(12, 0)  # 12:00 PM CT = noon
            else:
                return bar_time == time(15, 45)  # 3:45 PM CT
        except:
            return False
    
    def is_outside_session(self, timestamp: str) -> bool:
        """Check if current time is outside MNQ trading session.
        
        Trading session: 5:00 PM (17:00) Sunday to 4:00 PM (16:00) Friday CT
        Gap: 4:00 PM Friday to 5:00 PM Sunday
        
        Args:
            timestamp: Bar timestamp (format: 'DD/MM/YYYY HH:MM:SS')
            
        Returns:
            True if outside trading hours
        """
        try:
            from datetime import datetime
            dt = datetime.strptime(timestamp, '%d/%m/%Y %H:%M:%S')
            day_of_week = dt.weekday()  # 0=Monday, 6=Sunday
            hour = dt.hour
            
            # Friday after 4 PM to Sunday before 5 PM is outside session
            if day_of_week == 4 and hour >= 16:  # Friday 4 PM+
                return True
            if day_of_week == 5:  # Saturday all day
                return True
            if day_of_week == 6 and hour < 17:  # Sunday before 5 PM
                return True
            
            return False
        except:
            return False
    
    # Note: Partial and full exits should be expressed using buy/sell with quantity and a reason.
    
    def generate_signal(self, prices_data: List[Dict[str, Any]], scores_data: Optional[List[Dict[str, Any]]] = None) -> List[TradeSignal]:
        """Legacy batch mode - not used in event-driven architecture. Return empty list."""
        return []
    
    @abstractmethod
    def get_parameter_ranges(self) -> Dict[str, tuple]:
        """Return parameter ranges for optimization.
        
        Returns:
            Dictionary mapping parameter names to (min, max, step) tuples
            Example: {'stop_loss': (0.5, 3.0, 0.5), 'tp_ratio': (1.0, 5.0, 0.5)}
        """
        pass
    
    def get_position_size(self, capital: float, price: float) -> int:
        """Calculate position size based on available capital.
        
        Default: Fixed number of contracts/shares. Override for dynamic sizing.
        
        Args:
            capital: Available capital
            price: Entry price
            
        Returns:
            Number of contracts/shares to trade
        """
        default_size = self.params.get('position_size', 1)
        return default_size
    
    def update_stops(self, current_price: float, entry_price: float, 
                     current_sl: float, position: int) -> Optional[float]:
        """Update stop loss (e.g., trailing stop, breakeven).
        
        Override to implement custom stop management.
        
        Args:
            current_price: Current market price
            entry_price: Entry price
            current_sl: Current stop loss level
            position: 1 for long, -1 for short
            
        Returns:
            Updated stop loss or None to keep current
        """
        return None
    
    def get_info(self) -> Dict[str, Any]:
        """Return strategy information for display.
        
        Returns:
            Dictionary with strategy name, description, parameters, etc.
        """
        return {
            'name': self.name,
            'instrument_type': self.instrument_type,
            'point_value': self.point_value,
            'tick_size': self.tick_size,
            'parameters': self.params
        }

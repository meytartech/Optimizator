"""
MNQ Multi-Timeframe Strategy (Event-Driven)

Entry Rules:
- Long: 1m score crosses above 0 AND at least 2 other timeframes > threshold
- Short: 1m score crosses below 0 AND at least 2 other timeframes < threshold

Exit Rules:
- Stop Loss: Swing-based (last swing point) - moves to breakeven + 4 ticks after TP1
- Take Profits: Multiple levels based on ATR (TP1, TP2, TP3)

Trading Windows:
- Window 1: 10:00-11:30 CT
- Window 2: 16:30-18:00 CT
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.base_strategy import BaseStrategy
from typing import Dict, List, Any, Optional, Tuple


class MNQStrategy(BaseStrategy):
    """MNQ multi-timeframe strategy with swing-based stops and ATR take profits."""
    
    def __init__(self, params: Optional[Dict[str, Any]] = None, **kwargs) -> None:
        merged: Dict[str, Any] = {}
        if params:
            merged.update(params)
        if kwargs:
            merged.update(kwargs)
        super().__init__(params=merged)

    def setup(self):
        """Initialize strategy parameters."""
        # Get parameters with defaults
        self.required_confirmations = int(self.params.get('required_confirmations', 2))
        self.atr_length = int(self.params.get('atr_length', 15))
        self.atr_stop_multiplier = float(self.params.get('atr_stop_multiplier', 2.5))
        self.tp1_multiplier = float(self.params.get('tp1_multiplier', 1.5))
        self.tp2_multiplier = float(self.params.get('tp2_multiplier', 4.0))
        self.tp3_multiplier = float(self.params.get('tp3_multiplier', 4.5))
        self.score_threshold = float(self.params.get('score_threshold', 20.0))
        self.cross_level = float(self.params.get('cross_level', 0.0))
        self.swing_lookback = int(self.params.get('swing_lookback', 5))
        
        # Position tracking
        self._position_direction = 0  # 1=long, -1=short, 0=flat
        self._entry_price = None
        self._entry_atr = None
        self._sl_level = 0.0
        self._tp1_level = 0.0
        self._tp2_level = 0.0
        self._tp3_level = 0.0
        self._tp1_hit = False
        self._tp2_hit = False
        self._tp3_hit = False
    
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
    
    def _find_swing_points(self, prices_data: List[Dict[str, Any]], current_idx: int) -> Tuple[Optional[float], Optional[float]]:
        """Find swing low and swing high for stop loss placement."""
        if len(prices_data) < (self.swing_lookback * 2 + 1):
            return None, None
        
        swing_low = None
        swing_high = None
        
        start_search = min(current_idx, len(prices_data) - self.swing_lookback - 1)
        
        for i in range(start_search, self.swing_lookback, -1):
            bar = prices_data[i]
            h, l = bar['high'], bar['low']
            
            # Check Swing High
            if swing_high is None:
                if all(h >= prices_data[j]['high'] for j in range(i - self.swing_lookback, i + self.swing_lookback + 1)):
                    swing_high = h
                    
            # Check Swing Low
            if swing_low is None:
                if all(l <= prices_data[j]['low'] for j in range(i - self.swing_lookback, i + self.swing_lookback + 1)):
                    swing_low = l
                    
            if swing_low is not None and swing_high is not None:
                break
                
        return swing_low, swing_high
    
    def _parse_time_from_timestamp(self, timestamp: str) -> Tuple[int, int]:
        """Extract hour and minute from timestamp string."""
        try:
            if '/' in timestamp:
                parts = timestamp.split(' ')
                if len(parts) >= 2:
                    time_part = parts[1]
                    comps = time_part.split(':')
                    if len(comps) >= 2:
                        return int(comps[0]), int(comps[1])
            if '-' in timestamp and ' ' in timestamp:
                parts = timestamp.split(' ')
                if len(parts) >= 2:
                    time_part = parts[1]
                    comps = time_part.split(':')
                    if len(comps) >= 2:
                        return int(comps[0]), int(comps[1])
        except (IndexError, ValueError):
            pass
        return (0, 0)

    def on_bar(self, data: List[Dict[str, Any]]):
        """Event-driven logic called on every bar."""
        # Need at least atr_length + 1 bars for ATR
        if len(data) < self.atr_length + 1:
            return
        
        current_bar = data[-1]
        timestamp = current_bar.get('timestamp', '')
        close = current_bar['close']
        high = current_bar.get('high', close)
        low = current_bar.get('low', close)
        
        # Reset position direction when flat
        if self.position == 0 and self._position_direction != 0:
            self._position_direction = 0
        
        # Entry detection (if flat)
        if self.position == 0 and len(data) >= 2:
            # Get score_1m from last 2 bars (embedded in combined data)
            current_score_1m = data[-1].get('score_1m')
            previous_score_1m = data[-2].get('score_1m')
            
            if current_score_1m is not None and previous_score_1m is not None:
                current_score = current_score_1m
                previous_score = previous_score_1m
                
                crossed_up = previous_score <= self.cross_level and current_score > self.cross_level
                crossed_down = previous_score >= self.cross_level and current_score < self.cross_level
                
                if crossed_up or crossed_down:
                    # Entry confirmed if cross detected (no additional confirmations needed for now)
                    confirmations = 0  # Placeholder for future multi-timeframe logic
                    
                    if True:  # Always enter on cross for now
                        atr_val = self._calculate_atr(data)
                        if atr_val <= 0:
                            return
                        
                        self._entry_price = close
                        self._entry_atr = atr_val
                        
                        # Find swing points for stop loss
                        swing_low, swing_high = self._find_swing_points(data, len(data) - 1)
                        
                        # Calculate and store TP/SL levels
                        if crossed_up:
                            # Long entry
                            if swing_low is not None:
                                self._sl_level = swing_low - self.tick_size
                            else:
                                self._sl_level = close - atr_val * self.atr_stop_multiplier
                            
                            self._tp1_level = close + atr_val * self.tp1_multiplier
                            self._tp2_level = close + atr_val * self.tp2_multiplier
                            self._tp3_level = close + atr_val * self.tp3_multiplier
                            
                            self.buy(quantity=3, reason='ENTRY')
                            self._position_direction = 1
                        else:
                            # Short entry
                            if swing_high is not None:
                                self._sl_level = swing_high + self.tick_size
                            else:
                                self._sl_level = close + atr_val * self.atr_stop_multiplier
                            
                            self._tp1_level = close - atr_val * self.tp1_multiplier
                            self._tp2_level = close - atr_val * self.tp2_multiplier
                            self._tp3_level = close - atr_val * self.tp3_multiplier
                            
                            self.sell_short(quantity=3, reason='ENTRY')
                            self._position_direction = -1
                        
                        # Reset exit flags
                        self._tp1_hit = False
                        self._tp2_hit = False
                        self._tp3_hit = False
        
        # Exit handling (if in position)
        if self.position > 0 and self._position_direction != 0:
            # Long position exits
            if self._position_direction == 1:
                # Check TP1
                if high >= self._tp1_level and not self._tp1_hit:
                    self.sell_short(quantity=1, reason='TP1')
                    self._tp1_hit = True
                    # Move SL to breakeven + 4 ticks after TP1
                    self._sl_level = self._entry_price + self.tick_size * 4
                
                # Check TP2
                if high >= self._tp2_level and not self._tp2_hit:
                    self.sell_short(quantity=1, reason='TP2')
                    self._tp2_hit = True
                
                # Check TP3
                if high >= self._tp3_level and not self._tp3_hit:
                    self.sell_short(quantity=1, reason='TP3')
                    self._tp3_hit = True
                
                # Check SL
                if low <= self._sl_level and self.position > 0:
                    # Check if this is a breakeven stop
                    if self._tp1_hit and abs(self._sl_level - (self._entry_price + self.tick_size * 4)) < self.tick_size * 0.1:
                        self.sell_short(quantity=self.position, reason='BREAKEVEN')
                    else:
                        self.sell_short(quantity=self.position, reason='SL')
            
            # Short position exits
            elif self._position_direction == -1:
                # Check TP1
                if low <= self._tp1_level and not self._tp1_hit:
                    self.buy(quantity=1, reason='TP1')
                    self._tp1_hit = True
                    # Move SL to breakeven + 4 ticks after TP1
                    self._sl_level = self._entry_price - self.tick_size * 4
                
                # Check TP2
                if low <= self._tp2_level and not self._tp2_hit:
                    self.buy(quantity=1, reason='TP2')
                    self._tp2_hit = True
                
                # Check TP3
                if low <= self._tp3_level and not self._tp3_hit:
                    self.buy(quantity=1, reason='TP3')
                    self._tp3_hit = True
                
                # Check SL
                if high >= self._sl_level and self.position > 0:
                    # Check if this is a breakeven stop
                    if self._tp1_hit and abs(self._sl_level - (self._entry_price - self.tick_size * 4)) < self.tick_size * 0.1:
                        self.buy(quantity=self.position, reason='BREAKEVEN')
                    else:
                        self.buy(quantity=self.position, reason='SL')
            
            # Force-close at session end
            if self.is_session_end(timestamp):
                if self.position > 0:
                    if self._position_direction == 1:
                        self.sell_short(quantity=self.position, reason='FORCE_CLOSE_EOD')
                    else:
                        self.buy(quantity=self.position, reason='FORCE_CLOSE_EOD')

    def generate_signal(self, prices_data, scores_data=None):
        """Legacy batch mode - not used."""
        return []
    
    def get_parameter_ranges(self) -> Dict[str, Tuple[float, float, float]]:
        """Return parameter ranges for optimization."""
        return {
            'atr_length': (10, 30, 5),
            'atr_stop_multiplier': (1.5, 3.5, 0.5),
            'tp1_multiplier': (1.0, 3.0, 0.5),
            'tp2_multiplier': (2.0, 4.0, 0.5),
            'tp3_multiplier': (4.0, 8.0, 0.5),
            'required_confirmations': (0, 3, 1),
            'score_threshold': (10, 40, 10),
            'cross_level': (-5.0, 5.0, 0.5)
        }

import sys
import os
from typing import Dict, List, Any, Optional, Tuple

# Adding path to core modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.base_strategy import BaseStrategy, TradeSignal

class OGMNQStrategy(BaseStrategy):
    """
    Event-Driven OG MNQ strategy with 3-contract entries and 1-contract exits.
    
    Logic:
    - Entry: 1m score crosses cross_level (buys 3 contracts)
    - Exits: Sells 1 contract at each TP level (TP1, TP2, TP3)
    - ATR: Calculated dynamically for TP/SL calculation
    """
    
    def setup(self):
        """Initialize strategy parameters (called by __init__)."""
        # Entry parameters
        self.cross_level = float(self.params.get('cross_level', 0.0))
        self.require_confirmations = int(self.params.get('require_confirmations', 0))
        self.confirmation_threshold = float(self.params.get('confirmation_threshold', 25.0))
        
        # ATR parameters
        self.atr_length = int(self.params.get('atr_length', 14))
        
        # Multipliers for TP/SL (based on ATR)
        self.sl_multiplier = float(self.params.get('sl_multiplier', 2.0))
        self.tp1_multiplier = float(self.params.get('tp1_multiplier', 2.0))
        self.tp2_multiplier = float(self.params.get('tp2_multiplier', 4.0))
        self.tp3_multiplier = float(self.params.get('tp3_multiplier', 4.5))
        
        # Position tracking for partial exits
        self._entry_price = None
        self._entry_atr = None
        self._position_direction = 0  # 1 for long, -1 for short
        self._tp1_hit = False
        self._tp2_hit = False
        self._tp3_hit = False
        # Store TP/SL levels so they persist across bars
        self._sl_level = 0.0
        self._tp1_level = 0.0
        self._tp2_level = 0.0
        self._tp3_level = 0.0

    def _calculate_atr(self, data: List[Dict[str, Any]]) -> float:
        """Calculate Simple ATR for the current slice."""
        if len(data) <= self.atr_length:
            return 0.0
            
        true_ranges = []
        # We only need the last 'atr_length' bars to calculate current ATR
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

    def on_bar(self, price_bars: List[Dict[str, Any]], scores_data: Optional[List[Dict[str, Any]]] = None):
        """
        The main event loop called by the engine for every bar.
        - Entry: 3 contracts on 1m score cross above/below 0
        - Exits: 1 contract each at TP1, TP2, TP3 levels
        - ATR: Calculated dynamically for TP/SL calculation
        
        Args:
            price_bars: Price bars up to current timestamp
            scores_data: Optional score records up to current timestamp
        """
        # 1. Need at least 2 bars to detect a cross and 'atr_length' for ATR
        if len(price_bars) < max(self.atr_length + 1, 2):
            return

        # Get current bar (always available)
        current_bar = price_bars[-1]
        current_timestamp = current_bar.get('timestamp', '')
        
        # Reset position direction when flat
        if self.position == 0 and self._position_direction != 0:
            self._position_direction = 0
        
        # Entry detection (if flat)
        if self.position == 0 and scores_data and len(scores_data) >= 2:
            # Backtester pre-filters scores to 1m timeframe, so scores_data already contains only 1m scores
            # No need to filter again (massive performance improvement!)
            
            # Get last 2 unique timestamps for 1m scores
            # Handle multiple records per timestamp by grouping
            unique_timestamps = []
            seen_timestamps = set()
            for s in reversed(scores_data):
                ts = s['timestamp']
                if ts not in seen_timestamps:
                    unique_timestamps.append(s)
                    seen_timestamps.add(ts)
                if len(unique_timestamps) >= 2:
                    break
            
            if len(unique_timestamps) >= 2:
                current_score = unique_timestamps[0]['score']
                previous_score = unique_timestamps[1]['score']
                
                crossed_up = previous_score <= 0 and current_score > 0
                crossed_down = previous_score >= 0 and current_score < 0

                if crossed_up or crossed_down:
                    atr_val = self._calculate_atr(price_bars)
                    if atr_val <= 0: 
                        return

                    close_price = current_bar['close']
                    self._entry_price = close_price
                    self._entry_atr = atr_val
                    
                    # Calculate and store TP/SL levels for use in exit checks
                    self._sl_level = close_price - (1 if crossed_up else -1) * atr_val * self.sl_multiplier
                    self._tp1_level = close_price + (1 if crossed_up else -1) * atr_val * self.tp1_multiplier
                    self._tp2_level = close_price + (1 if crossed_up else -1) * atr_val * self.tp2_multiplier
                    self._tp3_level = close_price + (1 if crossed_up else -1) * atr_val * self.tp3_multiplier
                    
                    # Reset exit flags
                    self._tp1_hit = False
                    self._tp2_hit = False
                    self._tp3_hit = False
                    
                    # Entry: Buy/Sell 3 contracts
                    if crossed_up:
                        self.buy(quantity=3, reason='ENTRY')
                        self._position_direction = 1
                    else:  # crossed_down
                        self.sell_short(quantity=3, reason='ENTRY')
                        self._position_direction = -1
        
        # Exit handling (if in position)
        if self.position != 0 and self._position_direction != 0:
            high = current_bar.get('high', current_bar.get('close'))
            low = current_bar.get('low', current_bar.get('close'))
            
            # Long position exits
            if self._position_direction == 1:
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
                # Check SL
                if low <= self._sl_level and self.position > 0:
                    self.sell_short(quantity=self.position, reason='SL')
            
            # Short position exits
            elif self._position_direction == -1:
                # Check TP1
                if low <= self._tp1_level and not self._tp1_hit:
                    self.buy(quantity=1, reason='TP1')
                    self._tp1_hit = True
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
                    self.buy(quantity=self.position, reason='SL')
            
            # Force-close at session end
            if self.is_session_end(current_timestamp, early_close=False):
                if self.position > 0:
                    if self._position_direction == 1:
                        self.sell_short(quantity=self.position, reason='FORCE_CLOSE_EOD')
                    else:
                        self.buy(quantity=self.position, reason='FORCE_CLOSE_EOD')

    
    def get_parameter_ranges(self) -> Dict[str, Tuple[float, float, float]]:
        """Return parameter ranges for optimization."""
        return {
            'cross_level': (-5.0, 5.0, 1.0),
            'atr_length': (10, 20, 2),
            'sl_multiplier': (0.5, 2.0, 0.5),
            'tp1_multiplier': (0.5, 2.0, 0.5),
            'tp2_multiplier': (1.0, 3.0, 0.5),
            'tp3_multiplier': (2.0, 5.0, 0.5)
        }
    
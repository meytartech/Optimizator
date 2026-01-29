"""
Timezone utilities for Chicago-based trading sessions.

Handles timezone conversions and session time calculations.
"""

import pytz
from datetime import datetime, time
from typing import Optional, Tuple

# Chicago timezone
CHICAGO_TZ = pytz.timezone('America/Chicago')
UTC_TZ = pytz.UTC


def convert_to_timestamp(timestamp: str) -> str:
    """Normalize timestamp to match price data format.

    Args:
        timestamp: Timestamp string        
    Returns:
        Normalized timestamp in %Y-%m-%d %H:%M:%S%z  format
    """
    
    if not timestamp:
        return timestamp

    try:
        return datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S%z')
    except Exception:
        print(f"Error parsing timestamp in convert_to_timestamp: {timestamp}")
        return timestamp
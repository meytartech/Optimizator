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


def get_chicago_time(dt: datetime) -> datetime:
    """Convert datetime to Chicago timezone.
    
    Args:
        dt: Datetime object (can be naive or timezone-aware)
        
    Returns:
        Datetime in Chicago timezone
    """
    if dt.tzinfo is None:
        # Assume UTC if naive
        dt = UTC_TZ.localize(dt)
    return dt.astimezone(CHICAGO_TZ)


def parse_timestamp_to_chicago(timestamp_str: str) -> Optional[datetime]:
    """Parse timestamp string and convert to Chicago timezone.
    
    Supports multiple formats:
    - ISO format: 2026-01-16T01:00:00+00:00
    - DD/MM/YYYY HH:MM:SS
    - YYYY-MM-DD HH:MM:SS
    
    Args:
        timestamp_str: Timestamp string
        
    Returns:
        Datetime in Chicago timezone, or None if parsing fails
    """
    if not timestamp_str:
        return None
    
    # Try multiple formats
    formats = [
        '%d/%m/%Y %H:%M:%S',
        '%d/%m/%Y %H:%M',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(timestamp_str, fmt)
            # Assume UTC if no timezone info
            dt = UTC_TZ.localize(dt)
            return dt.astimezone(CHICAGO_TZ)
        except ValueError:
            continue
    
    # Try ISO format
    try:
        if 'T' in timestamp_str:
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = UTC_TZ.localize(dt)
            return dt.astimezone(CHICAGO_TZ)
    except ValueError:
        pass
    
    return None


def get_session_hour_minute(dt: datetime) -> Tuple[int, int]:
    """Get hour and minute from datetime in Chicago timezone.
    
    Args:
        dt: Datetime object
        
    Returns:
        Tuple of (hour, minute) in Chicago time
    """
    chicago_dt = get_chicago_time(dt) if dt.tzinfo else CHICAGO_TZ.localize(dt)
    return chicago_dt.hour, chicago_dt.minute


def is_in_session(dt: datetime, 
                 session_start: Tuple[int, int] = (13, 30),
                 session_end: Tuple[int, int] = (20, 0)) -> bool:
    """Check if datetime is within trading session (Chicago time).
    
    MNQ Session: 5:00 PM (17:00) to 4:00 PM (16:00) next day
    In Chicago time:
    - Market opens: 5:00 PM CT = 17:00
    - Market closes: 4:00 PM CT = 16:00 (next day)
    - Force close: 3:59 PM CT = 15:59
    
    Default: 1:30 PM (13:30) to 8:00 PM (20:00) for testing
    
    Args:
        dt: Datetime to check
        session_start: (hour, minute) tuple for session start
        session_end: (hour, minute) tuple for session end
        
    Returns:
        True if within session, False otherwise
    """
    chicago_dt = get_chicago_time(dt) if dt.tzinfo else CHICAGO_TZ.localize(dt)
    hour, minute = chicago_dt.hour, chicago_dt.minute
    
    start_min = session_start[0] * 60 + session_start[1]
    end_min = session_end[0] * 60 + session_end[1]
    current_min = hour * 60 + minute
    
    if start_min < end_min:
        # Same day session
        return start_min <= current_min < end_min
    else:
        # Session crosses midnight
        return current_min >= start_min or current_min < end_min


def is_force_close_time(dt: datetime) -> bool:
    """Check if datetime is at session force-close time (3:59 PM CT for MNQ).
    
    Args:
        dt: Datetime to check
        
    Returns:
        True if at 15:59 (3:59 PM) Chicago time
    """
    hour, minute = get_session_hour_minute(dt)
    return hour == 15 and minute == 59


# MNQ-Specific Session Times (Chicago Timezone)
MNQ_SESSION_OPEN = (17, 0)      # 5:00 PM CT (Sunday evening through Friday)
MNQ_SESSION_CLOSE = (16, 0)     # 4:00 PM CT (next day)
MNQ_FORCE_CLOSE = (15, 59)      # 3:59 PM CT (before market close)
MNQ_MAINTENANCE = ((16, 0), (17, 0))  # 4:00 PM to 5:00 PM CT (daily halt)


def is_in_mnq_session(dt: datetime) -> bool:
    """Check if datetime is within MNQ trading hours (Chicago time).
    
    MNQ trades Sunday 5:00 PM through Friday 4:00 PM CT.
    Excludes 4:00 PM - 5:00 PM CT daily maintenance window.
    
    Args:
        dt: Datetime to check
        
    Returns:
        True if within MNQ trading hours
    """
    chicago_dt = get_chicago_time(dt) if dt.tzinfo else CHICAGO_TZ.localize(dt)
    weekday = chicago_dt.weekday()  # 0=Monday, 6=Sunday
    hour, minute = chicago_dt.hour, chicago_dt.minute
    
    # Convert to minutes for easier comparison
    current_min = hour * 60 + minute
    open_min = MNQ_SESSION_OPEN[0] * 60 + MNQ_SESSION_OPEN[1]      # 1020 (17:00)
    close_min = MNQ_SESSION_CLOSE[0] * 60 + MNQ_SESSION_CLOSE[1]    # 960 (16:00)
    maint_start = MNQ_MAINTENANCE[0][0] * 60 + MNQ_MAINTENANCE[0][1]  # 960 (16:00)
    maint_end = MNQ_MAINTENANCE[1][0] * 60 + MNQ_MAINTENANCE[1][1]    # 1020 (17:00)
    
    # Sunday (6) through Friday (4)
    if weekday == 5:  # Saturday - fully closed
        return False
    
    if current_min >= maint_start and current_min < maint_end:
        # In maintenance window (4:00-5:00 PM CT)
        return False
    
    if weekday == 6:  # Sunday - open from 5:00 PM onwards
        return current_min >= open_min
    elif weekday < 4:  # Monday through Thursday - always within session
        return current_min >= close_min or True  # After 4:00 AM (previous day's close)
    else:  # Friday - close at 4:00 PM CT
        return current_min < close_min

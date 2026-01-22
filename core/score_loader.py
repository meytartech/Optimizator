"""
Score Data Loader for SQLite Database

Loads score/indicator data from SQLite database files structured
with ScoreMessage model (channel_name, timeframe, score, change, momentum, price, timestamp).
"""

import sqlite3
from typing import List, Dict, Any, Optional
from datetime import datetime
import os


class ScoreDataLoader:
    """Load score data from SQLite database files."""
    
    @staticmethod
    def normalize_timestamp(timestamp: str) -> str:
        """Normalize timestamp to match price data format.
        
        Converts ISO 8601 (2026-01-16T01:00:00+00:00) to DD/MM/YYYY HH:MM:00 format
        (seconds clamped to 00 to align with minute bars in CSV).
        
        Args:
            timestamp: Timestamp string in any format
            
        Returns:
            Normalized timestamp in DD/MM/YYYY HH:MM:SS format
        """
        try:
            # Try parsing ISO 8601 format
            if 'T' in timestamp:
                # ISO format: 2026-01-16T01:00:00+00:00
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return dt.replace(second=0).strftime('%d/%m/%Y %H:%M:%S')
            elif '/' in timestamp:
                # European format
                for fmt in ['%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M']:
                    try:
                        dt = datetime.strptime(timestamp, fmt)
                        return dt.replace(second=0).strftime('%d/%m/%Y %H:%M:%S')
                    except Exception:
                        continue
                # If parsing fails, return as-is
                return timestamp
            else:
                # Try other common formats
                for fmt in ['%Y-%m-%d %H:%M:%S', '%m/%d/%Y %H:%M:%S', '%d/%m/%Y %H:%M:%S']:
                    try:
                        dt = datetime.strptime(timestamp, fmt)
                        return dt.replace(second=0).strftime('%d/%m/%Y %H:%M:%S')
                    except:
                        continue
                return timestamp
        except Exception:
            return timestamp
    
    @staticmethod
    def _normalize_filter_value(value: Optional[str]) -> Optional[str]:
        """Normalize filter values (start/end) to ISO 'YYYY-MM-DDTHH:MM:SS'.
        
        Accepts a variety of timestamp string formats (ISO with 'T',
        'YYYY-MM-DD HH:MM:SS', or 'DD/MM/YYYY HH:MM[:SS]') and returns
        a consistent ISO string suitable for lexicographic comparison
        in SQLite where the 'timestamp' column stores ISO strings.
        """
        if value is None:
            return None
        try:
            # Already ISO-like
            if 'T' in value:
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                return dt.strftime('%Y-%m-%dT%H:%M:%S')
            # Space-separated ISO without 'T'
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
                try:
                    dt = datetime.strptime(value, fmt)
                    return dt.strftime('%Y-%m-%dT%H:%M:%S')
                except Exception:
                    pass
            # European format
            for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M'):
                try:
                    dt = datetime.strptime(value, fmt)
                    return dt.strftime('%Y-%m-%dT%H:%M:%S')
                except Exception:
                    pass
            # Fallback: return as-is (better to include than exclude)
            return value
        except Exception:
            return value

    @staticmethod
    def load_scores(db_path: str, channel_name: Optional[str] = None, 
                   timeframe: Optional[str] = None,
                   start_date: Optional[str] = None,
                   end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load score records from SQLite database.
        
        Args:
            db_path: Path to SQLite .db file
            channel_name: Filter by channel (e.g., 'mnq', 'es_1m'). None = all channels
            timeframe: Filter by timeframe (e.g., '1m', '5m', '15m', '60m'). None = all timeframes
            start_date: Filter records after this ISO timestamp
            end_date: Filter records before this ISO timestamp
            
        Returns:
            List of score records as dictionaries with keys:
            id, channel_name, timeframe, score, change, momentum, price, timestamp, created_at
        """
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database file not found: {db_path}")
        
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        cursor = conn.cursor()
        
        # Build query with filters
        query = "SELECT * FROM score_messages WHERE 1=1"
        params = []
        
        if channel_name:
            query += " AND channel_name = ?"
            params.append(channel_name)
        
        if timeframe:
            query += " AND timeframe = ?"
            params.append(timeframe)
        
        # Normalize filter values to ISO to match stored DB format
        norm_start = ScoreDataLoader._normalize_filter_value(start_date)
        norm_end = ScoreDataLoader._normalize_filter_value(end_date)

        if norm_start:
            query += " AND timestamp >= ?"
            params.append(norm_start)
        
        if norm_end:
            query += " AND timestamp <= ?"
            params.append(norm_end)
        
        query += " ORDER BY timestamp ASC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        # Convert to list of dicts
        records = []
        for row in rows:
            normalized_ts = ScoreDataLoader.normalize_timestamp(row['timestamp'])
            records.append({
                'id': row['id'],
                'channel_name': row['channel_name'],
                'timeframe': row['timeframe'],
                'score': float(row['score']) if row['score'] is not None else 0.0,
                'change': float(row['change']) if row['change'] is not None else None,
                'momentum': row['momentum'],
                'price': row['price'],
                'timestamp': normalized_ts,  # Use normalized timestamp
                'created_at': row['created_at']
            })
        
        return records
    
    @staticmethod
    def get_score_at_timestamp(scores: List[Dict[str, Any]], timestamp: str, 
                               timeframe: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get the most recent score record at or before a given timestamp.
        
        Args:
            scores: List of score records (must be sorted by timestamp)
            timestamp: ISO format timestamp to query
            timeframe: Optional timeframe filter
            
        Returns:
            Score record dict or None if no matching score found
        """
        if not scores:
            return None
        
        # Filter by timeframe if specified
        if timeframe:
            scores = [s for s in scores if s.get('timeframe') == timeframe]
        
        # Find most recent score <= timestamp
        result = None
        for score in scores:
            if score['timestamp'] <= timestamp:
                result = score
            else:
                break
        
        return result
    
    @staticmethod
    def get_data_info(db_path: str) -> Dict[str, Any]:
        """Get summary information about the score database.
        
        Args:
            db_path: Path to SQLite .db file
            
        Returns:
            Dictionary with database statistics
        """
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database file not found: {db_path}")
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get total records
        cursor.execute("SELECT COUNT(*) FROM score_messages")
        total_records = cursor.fetchone()[0]
        
        # Get unique channels
        cursor.execute("SELECT DISTINCT channel_name FROM score_messages")
        channels = [row[0] for row in cursor.fetchall()]
        
        # Get unique timeframes
        cursor.execute("SELECT DISTINCT timeframe FROM score_messages")
        timeframes = [row[0] for row in cursor.fetchall()]
        
        # Get date range
        cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM score_messages")
        date_range = cursor.fetchone()
        
        conn.close()
        
        return {
            'total_records': total_records,
            'channels': sorted(channels),
            'timeframes': sorted(timeframes),
            'start_date': date_range[0],
            'end_date': date_range[1]
        }
    
    @staticmethod
    def validate_database(db_path: str) -> bool:
        """Validate that database has correct schema.
        
        Args:
            db_path: Path to SQLite .db file
            
        Returns:
            True if valid, False otherwise
        """
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Check if score_messages table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='score_messages'")
            if not cursor.fetchone():
                conn.close()
                return False
            
            # Check required columns
            cursor.execute("PRAGMA table_info(score_messages)")
            columns = {row[1] for row in cursor.fetchall()}
            required = {'channel_name', 'timeframe', 'score', 'timestamp'}
            
            conn.close()
            return required.issubset(columns)
        
        except Exception:
            return False

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
    
    @staticmethod
    def is_valid_db(db_path: str) -> bool:
        """Check if database contains combined price + score data.
        
        A combined database must have a table with these columns:
        timestamp, score_1m, score_5m, score_15m, score_60m, high, low, open, close
        
        Args:
            db_path: Path to SQLite .db file
            
        Returns:
            True if database has combined format, False otherwise
        """
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Get all table names
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            required_columns = {'timestamp', 'score_1m', 'score_5m', 'score_15m', 'score_60m', 'high', 'low', 'open', 'close'}
            
            # Check each table for required columns
            for table_name in tables:
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = {row[1] for row in cursor.fetchall()}
                
                if required_columns.issubset(columns):
                    conn.close()
                    return True
            
            conn.close()
            return False
        
        except Exception:
            return False
    
    @staticmethod
    def load_combined_db(db_path: str, 
                        channel_name: Optional[str] = None,
                        start_date: Optional[str] = None,
                        end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load combined price + score data from a unified SQLite database.
        
        Expects a table with columns: timestamp, score_1m, score_5m, score_15m, score_60m, high, low, open, close
        Returns unified data array with embedded price + score fields.
        
        Args:
            db_path: Path to SQLite .db file
            channel_name: Filter by channel (if table has channel_name column)
            start_date: Filter records after this timestamp
            end_date: Filter records before this timestamp
            
        Returns:
            List of unified bars, each containing:
            {timestamp, open, high, low, close, score_1m, score_5m, score_15m, score_60m}
        """
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database file not found: {db_path}")
        
        if not ScoreDataLoader.is_valid_db(db_path):
            raise ValueError(f"Database does not have combined format. Required columns: timestamp, score_1m, score_5m, score_15m, score_60m, high, low, open, close")
        
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Find the table with required columns
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        required_columns = {'timestamp', 'score_1m', 'score_5m', 'score_15m', 'score_60m', 'high', 'low', 'open', 'close'}
        target_table = None
        
        for table_name in tables:
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = {row[1] for row in cursor.fetchall()}
            
            if required_columns.issubset(columns):
                target_table = table_name
                break
        
        if not target_table:
            conn.close()
            raise ValueError("No table found with required columns")
        
        # Build query with filters
        query = f"SELECT * FROM {target_table} WHERE 1=1"
        params = []
        
        # Check if channel_name column exists
        cursor.execute(f"PRAGMA table_info({target_table})")
        columns = {row[1] for row in cursor.fetchall()}
        
        if channel_name and 'channel_name' in columns:
            query += " AND channel_name = ?"
            params.append(channel_name)
        
        # Normalize filter values to ISO
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
        
        # Build unified data array with embedded scores
        unified_data = []
        
        for row in rows:
            normalized_ts = ScoreDataLoader.normalize_timestamp(row['timestamp'])
            
            # Create unified bar with embedded scores
            unified_data.append({
                'timestamp': normalized_ts,
                'open': float(row['open']) if row['open'] is not None else 0.0,
                'high': float(row['high']) if row['high'] is not None else 0.0,
                'low': float(row['low']) if row['low'] is not None else 0.0,
                'close': float(row['close']) if row['close'] is not None else 0.0,
                'score_1m': float(row['score_1m']) if row['score_1m'] is not None else None,
                'score_5m': float(row['score_5m']) if row['score_5m'] is not None else None,
                'score_15m': float(row['score_15m']) if row['score_15m'] is not None else None,
                'score_60m': float(row['score_60m']) if row['score_60m'] is not None else None
            })
        
        print(f"Loaded {len(unified_data)} unified bars with embedded data")
        
        return unified_data
    
    @staticmethod
    def load_combined_db_range(db_path: str, start_timestamp: str, end_timestamp: str, 
                                buffer_bars: int = 50) -> List[Dict[str, Any]]:
        """Load unified data for a specific timestamp range (useful for trade viewer).
        
        Args:
            db_path: Path to SQLite .db file
            start_timestamp: Start of range (ISO or DD/MM/YYYY HH:MM:SS format)
            end_timestamp: End of range (ISO or DD/MM/YYYY HH:MM:SS format)
            buffer_bars: Additional bars to load before/after range for context
            
        Returns:
            List of unified bars within the specified range (plus buffer)
        """
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database file not found: {db_path}")
        
        if not ScoreDataLoader.is_valid_db(db_path):
            raise ValueError(f"Database does not have combined format")
        
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Find the table with required columns
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        required_columns = {'timestamp', 'score_1m', 'score_5m', 'score_15m', 'score_60m', 'high', 'low', 'open', 'close'}
        target_table = None
        
        for table_name in tables:
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = {row[1] for row in cursor.fetchall()}
            
            if required_columns.issubset(columns):
                target_table = table_name
                break
        
        if not target_table:
            conn.close()
            raise ValueError("No table found with required columns")
        
        # Normalize timestamps
        norm_start = ScoreDataLoader._normalize_filter_value(start_timestamp)
        norm_end = ScoreDataLoader._normalize_filter_value(end_timestamp)
        
        # Simpler approach: Get range + buffer bars before and after
        # First, find timestamps at the edges of our range
        cursor.execute(f"""
            SELECT MIN(timestamp) as min_ts, MAX(timestamp) as max_ts
            FROM {target_table}
            WHERE timestamp >= ? AND timestamp <= ?
        """, (norm_start, norm_end))
        
        range_result = cursor.fetchone()
        if not range_result or not range_result[0]:
            # No data in range
            conn.close()
            return []
        
        range_min = range_result[0]
        range_max = range_result[1]
        
        # Now get buffer_bars before range_min and after range_max
        query = f"""
            WITH all_data AS (
                SELECT * FROM (
                    SELECT * FROM {target_table}
                    WHERE timestamp < ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                )
                UNION ALL
                SELECT * FROM {target_table}
                WHERE timestamp >= ? AND timestamp <= ?
                UNION ALL
                SELECT * FROM (
                    SELECT * FROM {target_table}
                    WHERE timestamp > ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                )
            )
            SELECT * FROM all_data
            ORDER BY timestamp ASC
        """
        
        cursor.execute(query, (range_min, buffer_bars, range_min, range_max, range_max, buffer_bars))
        rows = cursor.fetchall()
        conn.close()
        
        # Build unified data array
        unified_data = []
        for row in rows:
            normalized_ts = ScoreDataLoader.normalize_timestamp(row['timestamp'])
            unified_data.append({
                'timestamp': normalized_ts,
                'open': float(row['open']) if row['open'] is not None else 0.0,
                'high': float(row['high']) if row['high'] is not None else 0.0,
                'low': float(row['low']) if row['low'] is not None else 0.0,
                'close': float(row['close']) if row['close'] is not None else 0.0,
                'score_1m': float(row['score_1m']) if row['score_1m'] is not None else None,
                'score_5m': float(row['score_5m']) if row['score_5m'] is not None else None,
                'score_15m': float(row['score_15m']) if row['score_15m'] is not None else None,
                'score_60m': float(row['score_60m']) if row['score_60m'] is not None else None
            })
        
        return unified_data

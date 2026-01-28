"""
Data Loader

Handles loading OHLCV data from various sources (CSV, database, etc.)
"""

import csv
from typing import List, Dict, Any
from datetime import datetime


class CSVDataLoader:
    """Load OHLCV data from CSV files.
    
    Supports multiple formats:
    - Standard: timestamp, open, high, low, close, volume
    - Simplified: timestamp, price
    - Trading Platform: <Date>, <Time>, <Open>, <High>, <Low>, <Close>, <Volume>
    """
    
    @staticmethod
    def load_csv(filepath: str, 
                 date_column: str = None,
                 parse_dates: bool = True) -> List[Dict[str, Any]]:
        """Load data from CSV file with automatic format detection.
        
        Args:
            filepath: Path to CSV file
            date_column: Name of timestamp column (auto-detect if None)
            parse_dates: Whether to parse dates
            
        Returns:
            List of dictionaries with OHLCV data
        """
        data = []
        
        with open(filepath, 'r') as f:
            # Read first line to detect format
            first_line = f.readline()
            f.seek(0)
            
            # Detect if it's angle bracket format
            is_angle_bracket_format = '<Date>' in first_line or '<Time>' in first_line
            
            if is_angle_bracket_format:
                # Handle angle bracket format: <Date>, <Time>, <Open>, etc.
                import csv as csv_module
                reader = csv_module.DictReader(f)
                
                for row in reader:
                    # Clean up keys - remove angle brackets and spaces
                    cleaned_row = {}
                    for key, val in row.items():
                        clean_key = key.strip().strip('<>').lower() if key else key
                        
                        # Convert numeric fields
                        try:
                            if clean_key in ['open', 'high', 'low', 'close', 'volume']:
                                cleaned_row[clean_key] = float(val) if val else 0.0
                            else:
                                cleaned_row[clean_key] = val
                        except (ValueError, TypeError):
                            cleaned_row[clean_key] = val
                    
                    # Combine date and time into timestamp
                    if 'date' in cleaned_row and 'time' in cleaned_row:
                        cleaned_row['timestamp'] = f"{cleaned_row['date']} {cleaned_row['time']}"
                    elif 'timestamp' not in cleaned_row:
                        cleaned_row['timestamp'] = cleaned_row.get('date', '')
                    
                    # Ensure OHLC fields exist
                    if 'open' not in cleaned_row:
                        cleaned_row['open'] = cleaned_row.get('price', cleaned_row.get('close', 0.0))
                    if 'high' not in cleaned_row:
                        cleaned_row['high'] = cleaned_row.get('price', cleaned_row.get('close', 0.0))
                    if 'low' not in cleaned_row:
                        cleaned_row['low'] = cleaned_row.get('price', cleaned_row.get('close', 0.0))
                    if 'close' not in cleaned_row:
                        cleaned_row['close'] = cleaned_row.get('price', 0.0)
                    
                    # Add price field for compatibility
                    cleaned_row['price'] = cleaned_row.get('close', cleaned_row.get('price', 0.0))
                    
                    data.append(cleaned_row)
            else:
                # Handle standard format
                reader = csv.DictReader(f)
                for row in reader:
                    # Convert numeric fields
                    processed_row = {}
                    for key, val in row.items():
                        clean_key = key.strip().lower() if key else key
                        
                        if clean_key in ['timestamp', 'date', 'time']:
                            processed_row[clean_key] = val
                        else:
                            try:
                                processed_row[clean_key] = float(val) if val else 0.0
                            except (ValueError, TypeError):
                                processed_row[clean_key] = val
                    
                    # Normalize field names
                    normalized = {}
                    for k, v in processed_row.items():
                        normalized[k.lower().strip()] = v
                    
                    # Ensure timestamp exists
                    if 'timestamp' not in normalized:
                        if 'date' in normalized and 'time' in normalized:
                            normalized['timestamp'] = f"{normalized['date']} {normalized['time']}"
                        elif 'date' in normalized:
                            normalized['timestamp'] = normalized['date']
                        else:
                            normalized['timestamp'] = ''
                    
                    # Ensure OHLC fields exist
                    if 'open' not in normalized:
                        normalized['open'] = normalized.get('price', normalized.get('close', 0.0))
                    if 'high' not in normalized:
                        normalized['high'] = normalized.get('price', normalized.get('close', 0.0))
                    if 'low' not in normalized:
                        normalized['low'] = normalized.get('price', normalized.get('close', 0.0))
                    if 'close' not in normalized:
                        normalized['close'] = normalized.get('price', 0.0)
                    
                    # Add price for compatibility
                    normalized['price'] = normalized.get('close', normalized.get('price', 0.0))
                    
                    data.append(normalized)
        
        return data
    
    @staticmethod
    def validate_data(data: List[Dict[str, Any]]) -> bool:
        """Validate that data has required fields.
        
        Args:
            data: List of data dictionaries
            
        Returns:
            True if valid, False otherwise
        """
        if not data:
            return False
        
        required = ['timestamp']
        optional_sets = [
            ['open', 'high', 'low', 'close'],
            ['price']
        ]
        
        first_row = data[0]
        
        # Check required fields
        for field in required:
            if field not in first_row:
                return False
        
        # Check at least one optional set
        has_valid_set = False
        for opt_set in optional_sets:
            if all(field in first_row for field in opt_set):
                has_valid_set = True
                break
        
        return has_valid_set
    
    @staticmethod
    def get_data_info(data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get information about loaded data.
        
        Args:
            data: List of data dictionaries
            
        Returns:
            Dictionary with data information
        """
        if not data:
            return {}
        
        return {
            'rows': len(data),
            'columns': list(data[0].keys()),
            'start_date': data[0].get('timestamp', 'Unknown'),
            'end_date': data[-1].get('timestamp', 'Unknown'),
            'has_ohlc': all(k in data[0] for k in ['open', 'high', 'low', 'close'])
        }


class MultiTimeframeLoader:
    """Load and merge multiple timeframe data (for multi-TF strategies)."""
    
    @staticmethod
    def load_multiple_timeframes(filepaths: Dict[str, str]) -> Dict[str, List[Dict[str, Any]]]:
        """Load data from multiple timeframe CSV files.
        
        Args:
            filepaths: Dictionary mapping timeframe names to file paths
                      e.g., {'1m': 'path/to/1m.csv', '5m': 'path/to/5m.csv'}
        
        Returns:
            Dictionary mapping timeframe names to data lists
        """
        data_by_tf = {}
        
        for tf_name, filepath in filepaths.items():
            data = CSVDataLoader.load_csv(filepath)
            # Add timeframe identifier to each row
            for row in data:
                row['timeframe'] = tf_name
            data_by_tf[tf_name] = data
        
        return data_by_tf
    
    @staticmethod
    def merge_timeframes(data_by_tf: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Merge multiple timeframe data into single sorted list.
        
        Args:
            data_by_tf: Dictionary of timeframe data
            
        Returns:
            Single sorted list of all data points
        """
        all_data = []
        
        for tf_name, data_list in data_by_tf.items():
            all_data.extend(data_list)
        
        # Sort by timestamp
        all_data.sort(key=lambda x: x.get('timestamp', ''))
        
        return all_data

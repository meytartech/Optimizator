"""
Equity Curve Plotting Utility

Generates PNG/JPG charts of backtest equity curves and saves them to results folders.
"""

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for server environments
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from typing import List, Dict, Any
import os


class EquityPlotter:
    """Generate equity curve visualizations for backtest results."""
    
    @staticmethod
    def plot_equity_curve(equity_curve: List[Dict[str, Any]], 
                         output_path: str,
                         title: str = "Equity Curve",
                         initial_capital: float = 100000,
                         figsize: tuple = (12, 6),
                         dpi: int = 100) -> str:
        """Plot equity curve and save as image.
        
        Args:
            equity_curve: List of dicts with 'timestamp' and 'equity' keys
            output_path: Full path where to save the image (e.g., '/path/to/equity_curve.png')
            title: Chart title
            initial_capital: Starting capital for reference line
            figsize: Figure size (width, height) in inches
            dpi: Resolution in dots per inch
            
        Returns:
            Path to saved image file
        """
        if not equity_curve:
            raise ValueError("Equity curve data is empty")
        
        # Extract data
        timestamps = []
        equity_values = []
        
        for point in equity_curve:
            try:
                # Parse timestamp (handle various formats)
                ts_str = point.get('timestamp', '')
                if '/' in ts_str or '-' in ts_str:
                    # Try parsing date/time
                    for fmt in ['%d/%m/%Y,%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
                        try:
                            ts = datetime.strptime(ts_str.replace(',', ' '), fmt)
                            break
                        except:
                            continue
                    else:
                        # Fallback: use index
                        ts = datetime.fromtimestamp(len(timestamps))
                else:
                    ts = datetime.fromtimestamp(len(timestamps))
                
                # Convert equity to float
                equity_val = point.get('equity', initial_capital)
                try:
                    equity_val = float(equity_val)
                except (ValueError, TypeError):
                    equity_val = float(initial_capital)
                
                timestamps.append(ts)
                equity_values.append(equity_val)
            except:
                continue
        
        if not timestamps:
            raise ValueError("Could not parse any valid timestamps from equity curve")
        
        # Create figure
        fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
        
        # Plot equity curve
        ax.plot(timestamps, equity_values, linewidth=2, color='#2196F3', label='Equity')
        
        # Plot initial capital reference line
        ax.axhline(y=initial_capital, color='gray', linestyle='--', alpha=0.5, label='Initial Capital')
        
        # Calculate and display final return
        final_equity = float(equity_values[-1]) if equity_values else initial_capital
        total_return = ((final_equity - initial_capital) / initial_capital) * 100
        return_color = 'green' if total_return >= 0 else 'red'
        
        # Add return text box
        textstr = f'Final Equity: ${final_equity:,.2f}\nTotal Return: {total_return:+.2f}%'
        props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
        ax.text(0.02, 0.98, textstr, transform=ax.transAxes, fontsize=10,
                verticalalignment='top', bbox=props)
        
        # Formatting
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_xlabel('Time', fontsize=11)
        ax.set_ylabel('Equity ($)', fontsize=11)
        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper left')
        
        # Format x-axis dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d\n%H:%M'))
        fig.autofmt_xdate()
        
        # Tight layout
        plt.tight_layout()
        
        # Save figure
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        plt.savefig(output_path, dpi=dpi, bbox_inches='tight')
        plt.close(fig)
        
        return output_path
    
    @staticmethod
    def plot_drawdown(equity_curve: List[Dict[str, Any]], 
                     output_path: str,
                     title: str = "Drawdown Chart",
                     figsize: tuple = (12, 4),
                     dpi: int = 100) -> str:
        """Plot drawdown chart and save as image.
        
        Args:
            equity_curve: List of dicts with 'timestamp' and 'equity' keys
            output_path: Full path where to save the image
            title: Chart title
            figsize: Figure size (width, height) in inches
            dpi: Resolution in dots per inch
            
        Returns:
            Path to saved image file
        """
        if not equity_curve:
            raise ValueError("Equity curve data is empty")
        
        # Extract data and calculate drawdown
        timestamps = []
        drawdowns = []
        peak = 0
        
        for point in equity_curve:
            try:
                ts_str = point.get('timestamp', '')
                equity = point.get('equity', 0)
                
                # Parse timestamp
                for fmt in ['%d/%m/%Y,%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
                    try:
                        ts = datetime.strptime(ts_str.replace(',', ' '), fmt)
                        break
                    except:
                        continue
                else:
                    ts = datetime.fromtimestamp(len(timestamps))
                
                # Calculate drawdown
                peak = max(peak, equity)
                dd = ((equity - peak) / peak * 100) if peak > 0 else 0
                
                timestamps.append(ts)
                drawdowns.append(dd)
            except:
                continue
        
        if not timestamps:
            raise ValueError("Could not parse any valid timestamps from equity curve")
        
        # Create figure
        fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
        
        # Plot drawdown
        ax.fill_between(timestamps, drawdowns, 0, color='red', alpha=0.3)
        ax.plot(timestamps, drawdowns, linewidth=1.5, color='darkred', label='Drawdown')
        
        # Find max drawdown
        max_dd = min(drawdowns) if drawdowns else 0
        max_dd_idx = drawdowns.index(max_dd) if max_dd < 0 else 0
        
        if max_dd < 0:
            ax.scatter(timestamps[max_dd_idx], drawdowns[max_dd_idx], 
                      color='red', s=100, zorder=5, label=f'Max DD: {max_dd:.2f}%')
        
        # Formatting
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_xlabel('Time', fontsize=11)
        ax.set_ylabel('Drawdown (%)', fontsize=11)
        ax.grid(True, alpha=0.3)
        ax.legend(loc='lower left')
        
        # Format x-axis dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d\n%H:%M'))
        fig.autofmt_xdate()
        
        # Tight layout
        plt.tight_layout()
        
        # Save figure
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        plt.savefig(output_path, dpi=dpi, bbox_inches='tight')
        plt.close(fig)
        
        return output_path
    
    @staticmethod
    def plot_combined(equity_curve: List[Dict[str, Any]], 
                     output_path: str,
                     title: str = "Backtest Results",
                     initial_capital: float = 100000,
                     figsize: tuple = (12, 8),
                     dpi: int = 100) -> str:
        """Plot equity and drawdown in combined chart.
        
        Args:
            equity_curve: List of dicts with 'timestamp' and 'equity' keys
            output_path: Full path where to save the image
            title: Main chart title
            initial_capital: Starting capital
            figsize: Figure size (width, height) in inches
            dpi: Resolution in dots per inch
            
        Returns:
            Path to saved image file
        """
        if not equity_curve:
            raise ValueError("Equity curve data is empty")
        
        # Extract and parse data
        timestamps = []
        equity_values = []
        drawdowns = []
        peak = 0
        
        for point in equity_curve:
            try:
                ts_str = point.get('timestamp', '')
                equity_raw = point.get('equity', initial_capital)
                # Convert to float if it's a string
                try:
                    equity = float(equity_raw)
                except (ValueError, TypeError):
                    equity = float(initial_capital)
                
                # Parse timestamp
                for fmt in ['%d/%m/%Y,%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
                    try:
                        ts = datetime.strptime(ts_str.replace(',', ' '), fmt)
                        break
                    except:
                        continue
                else:
                    ts = datetime.fromtimestamp(len(timestamps))
                
                # Calculate drawdown
                peak = max(peak, equity)
                dd = ((equity - peak) / peak * 100) if peak > 0 else 0
                
                timestamps.append(ts)
                equity_values.append(equity)
                drawdowns.append(dd)
            except:
                continue
        
        if not timestamps:
            raise ValueError("Could not parse any valid timestamps")
        
        # Create subplots
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, dpi=dpi, 
                                        gridspec_kw={'height_ratios': [2, 1]})
        
        # Plot equity curve
        ax1.plot(timestamps, equity_values, linewidth=2, color='#2196F3', label='Equity')
        ax1.axhline(y=initial_capital, color='gray', linestyle='--', alpha=0.5, label='Initial Capital')
        
        final_equity = float(equity_values[-1]) if equity_values else initial_capital
        total_return = ((final_equity - initial_capital) / initial_capital) * 100
        
        textstr = f'Final: ${final_equity:,.2f}\nReturn: {total_return:+.2f}%'
        props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
        ax1.text(0.02, 0.98, textstr, transform=ax1.transAxes, fontsize=10,
                verticalalignment='top', bbox=props)
        
        ax1.set_title(title, fontsize=14, fontweight='bold')
        ax1.set_ylabel('Equity ($)', fontsize=11)
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc='upper left')
        
        # Plot drawdown
        ax2.fill_between(timestamps, drawdowns, 0, color='red', alpha=0.3)
        ax2.plot(timestamps, drawdowns, linewidth=1.5, color='darkred')
        
        max_dd = min(drawdowns) if drawdowns else 0
        ax2.set_ylabel('Drawdown (%)', fontsize=11)
        ax2.set_xlabel('Time', fontsize=11)
        ax2.grid(True, alpha=0.3)
        ax2.text(0.98, 0.05, f'Max DD: {max_dd:.2f}%', transform=ax2.transAxes,
                fontsize=10, verticalalignment='bottom', horizontalalignment='right',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        # Format x-axis dates
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d\n%H:%M'))
        fig.autofmt_xdate()
        
        # Tight layout
        plt.tight_layout()
        
        # Save figure
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        plt.savefig(output_path, dpi=dpi, bbox_inches='tight')
        plt.close(fig)
        
        return output_path

    @staticmethod
    def plot_enhanced_results(equity_curve: List[Dict[str, Any]],
                            trades: List[Any],
                            session_stats: Dict[str, Dict[str, Any]],
                            hourly_stats: Dict[int, Dict[str, Any]],
                            output_path: str,
                            title: str = "Backtest Results",
                            initial_capital: float = 100000,
                            figsize: tuple = (16, 12),
                            dpi: int = 120) -> str:
        """Plot comprehensive results with equity, drawdown, session analysis, and hourly analysis."""
        if not equity_curve:
            raise ValueError("Equity curve data is empty")
        
        # Ensure initial_capital is float
        initial_capital = float(initial_capital)
        
        # Filter equity curve to trade date range
        if trades:
            try:
                first_trade_time = trades[0].entry_time
                last_trade_time = trades[-1].exit_time
                for fmt in ['%d/%m/%Y,%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
                    try:
                        first_dt = datetime.strptime(first_trade_time.replace(',', ' '), fmt)
                        last_dt = datetime.strptime(last_trade_time.replace(',', ' '), fmt)
                        break
                    except:
                        continue
                else:
                    first_dt = None
                    last_dt = None
            except:
                first_dt = None
                last_dt = None
        else:
            first_dt = None
            last_dt = None
        
        # Extract and parse equity data
        timestamps = []
        equity_values = []
        drawdowns = []
        peak = 0
        
        for point in equity_curve:
            try:
                ts_str = point.get('timestamp', '')
                equity_raw = point.get('equity', initial_capital)
                # Convert to float if it's a string (from JSON loading)
                try:
                    equity = float(equity_raw)
                except (ValueError, TypeError):
                    equity = float(initial_capital)
                
                for fmt in ['%d/%m/%Y,%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
                    try:
                        ts = datetime.strptime(ts_str.replace(',', ' '), fmt)
                        break
                    except:
                        continue
                else:
                    ts = datetime.fromtimestamp(len(timestamps))
                
                # Filter to trade date range
                if first_dt and last_dt:
                    if ts < first_dt or ts > last_dt:
                        continue
                
                peak = max(peak, equity)
                dd = ((equity - peak) / peak * 100) if peak > 0 else 0
                timestamps.append(ts)
                equity_values.append(equity)
                drawdowns.append(dd)
            except:
                continue
        
        if not timestamps:
            raise ValueError("Could not parse any valid timestamps")
        
        # Create enhanced subplot layout
        fig = plt.figure(figsize=figsize, dpi=dpi)
        gs = fig.add_gridspec(3, 2, height_ratios=[2.5, 1, 1.5], hspace=0.35, wspace=0.3)
        
        # 1. Equity curve (top, full width)
        ax1 = fig.add_subplot(gs[0, :])
        try:
            ax1.plot(timestamps, equity_values, linewidth=2.5, color='#2196F3', label='Equity', alpha=0.9)
            ax1.fill_between(timestamps, equity_values, initial_capital, 
                             where=[e >= initial_capital for e in equity_values],
                             color='#4CAF50', alpha=0.2)
            ax1.fill_between(timestamps, equity_values, initial_capital,
                             where=[e < initial_capital for e in equity_values],
                             color='#f44336', alpha=0.2)
            ax1.axhline(y=initial_capital, color='#757575', linestyle='--', linewidth=1.5, alpha=0.7, label='Initial Capital')
            
            final_equity = float(equity_values[-1]) if equity_values else initial_capital
            total_return = ((final_equity - initial_capital) / initial_capital) * 100
            textstr = f'Final Equity: ${final_equity:,.2f}\nTotal Return: {total_return:+.2f}%'
            props = dict(boxstyle='round', facecolor='#FFF8DC', alpha=0.9, edgecolor='#333', linewidth=1.5)
            ax1.text(0.02, 0.98, textstr, transform=ax1.transAxes, fontsize=11, fontweight='bold',
                    verticalalignment='top', bbox=props)
            ax1.set_title(title, fontsize=16, fontweight='bold', pad=15)
            ax1.set_ylabel('Equity ($)', fontsize=12, fontweight='bold')
            ax1.grid(True, alpha=0.3, linestyle='--')
            ax1.spines['top'].set_visible(False)
            ax1.spines['right'].set_visible(False)
        except Exception as e:
            logger.error(f"ERROR plotting equity curve: {e}", exc_info=True)
        
        # 2. Drawdown (middle, full width)
        ax2 = fig.add_subplot(gs[1, :])
        try:
            ax2.fill_between(timestamps, drawdowns, 0, color='#f44336', alpha=0.4)
            ax2.plot(timestamps, drawdowns, linewidth=1.8, color='#d32f2f')
            max_dd = min(drawdowns) if drawdowns else 0
            ax2.set_ylabel('Drawdown (%)', fontsize=12, fontweight='bold')
            ax2.grid(True, alpha=0.3, linestyle='--')
            ax2.text(0.98, 0.08, f'Max DD: {max_dd:.2f}%', transform=ax2.transAxes,
                    fontsize=10, fontweight='bold', verticalalignment='bottom', horizontalalignment='right',
                    bbox=dict(boxstyle='round', facecolor='#FFF8DC', alpha=0.9, edgecolor='#333', linewidth=1.5))
            ax2.spines['top'].set_visible(False)
            ax2.spines['right'].set_visible(False)
        except Exception as e:
            print(f"ERROR plotting drawdown: {e}")
            import traceback
            traceback.print_exc()
        
        # 3. Win Rate by Session (bottom left)
        ax3 = fig.add_subplot(gs[2, 0])
        try:
            sessions = ['Asia\n(18:00-02:00)', 'Europe\n(02:00-10:30)', 'New York\n(08:30-15:00)']
            session_keys = ['Asia', 'Europe', 'New York']
            win_rates = []
            for key in session_keys:
                val = session_stats.get(key, {}).get('win_rate', 0)
                try:
                    win_rates.append(float(val))
                except (ValueError, TypeError):
                    win_rates.append(0.0)
            colors = ['#FF9800', '#2196F3', '#4CAF50']
            bars = ax3.bar(sessions, win_rates, color=colors, alpha=0.8, edgecolor='#333', linewidth=1.5)
            ax3.axhline(y=50, color='gray', linestyle='--', alpha=0.5, linewidth=1)
            ax3.set_ylabel('Win Rate (%)', fontsize=11, fontweight='bold')
            ax3.set_title('Win Rate by Session (IL Time)', fontsize=12, fontweight='bold')
            ax3.set_ylim(0, 100)
            ax3.grid(True, alpha=0.3, axis='y', linestyle='--')
            ax3.spines['top'].set_visible(False)
            ax3.spines['right'].set_visible(False)
            for bar, rate in zip(bars, win_rates):
                height = bar.get_height()
                ax3.text(bar.get_x() + bar.get_width()/2., height + 2,
                        f'{rate:.1f}%', ha='center', va='bottom', fontsize=9, fontweight='bold')
        except Exception as e:
            print(f"ERROR plotting session stats: {e}")
            import traceback
            traceback.print_exc()
        
        # 4. Success Rate by Hour (bottom right)
        ax4 = fig.add_subplot(gs[2, 1])
        try:
            hours = sorted(hourly_stats.keys())
            hourly_win_rates = []
            for h in hours:
                val = hourly_stats[h].get('win_rate', 0)
                try:
                    hourly_win_rates.append(float(val))
                except (ValueError, TypeError):
                    hourly_win_rates.append(0.0)
            
            ax4.plot(hours, hourly_win_rates, marker='o', linewidth=2, markersize=6, 
                    color='#9C27B0', alpha=0.8)
            ax4.axhline(y=50, color='gray', linestyle='--', alpha=0.5, linewidth=1)
            ax4.fill_between(hours, hourly_win_rates, 50, 
                             where=[r >= 50 for r in hourly_win_rates],
                             color='#4CAF50', alpha=0.3)
            ax4.fill_between(hours, hourly_win_rates, 50,
                             where=[r < 50 for r in hourly_win_rates],
                             color='#f44336', alpha=0.3)
            ax4.set_xlabel('Hour of Day', fontsize=11, fontweight='bold')
            ax4.set_ylabel('Success Rate (%)', fontsize=11, fontweight='bold')
            ax4.set_title('Success Rate by Hour', fontsize=12, fontweight='bold')
            ax4.set_ylim(0, 100)
            ax4.set_xticks(range(0, 24, 2))
            ax4.grid(True, alpha=0.3, linestyle='--')
            ax4.spines['top'].set_visible(False)
            ax4.spines['right'].set_visible(False)
        except Exception as e:
            print(f"ERROR plotting hourly stats: {e}")
            import traceback
            traceback.print_exc()
        
        # Format x-axis dates
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d\n%H:%M'))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d\n%H:%M'))
        fig.autofmt_xdate()
        
        # Save figure
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        plt.savefig(output_path, dpi=dpi, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close(fig)
        return output_path

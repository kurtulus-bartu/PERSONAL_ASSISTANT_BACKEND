"""
Stock Service for fetching stock prices from Yahoo Finance using yfinance
"""

import yfinance as yf
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time


class StockService:
    """
    Stock price service using Yahoo Finance (yfinance library)

    Fetches stock prices for global markets including:
    - Turkish stocks (*.IS suffix, e.g., THYAO.IS)
    - US stocks (e.g., AAPL, MSFT, GOOGL)
    - Other markets

    Features:
    - In-memory cache (10 minutes TTL)
    - Retry mechanism (up to 3 attempts)
    """

    def __init__(self):
        """Initialize stock service with cache and session"""
        self._cache = {}  # Format: {symbol: {'data': {...}, 'timestamp': float}}
        self._cache_ttl = 600  # 10 minutes

        # Create session with user-agent to avoid rate limiting
        import requests
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def get_stock_price(self, symbol: str, date: Optional[str] = None) -> Optional[Dict]:
        """
        Get current or historical stock price with cache and retry

        Args:
            symbol: Yahoo Finance symbol (e.g., "THYAO.IS", "AAPL")
            date: Optional date (YYYY-MM-DD), None for latest

        Returns:
            {
                'symbol': 'THYAO.IS',
                'stock_name': 'Türk Hava Yolları',
                'price': 250.50,
                'currency': 'TRY',
                'date': '2026-01-05',
                'market': 'IST'
            }
            or None if symbol not found
        """
        # Check cache for current prices only (not historical)
        if not date:
            cache_key = symbol.upper()
            cached_data = self._get_from_cache(cache_key)
            if cached_data:
                print(f"Cache hit for {cache_key}")
                return cached_data

        # Try fetching with retries
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Use session to avoid rate limiting
                ticker = yf.Ticker(symbol.upper(), session=self._session)

                if date:
                    # Historical price for specific date
                    start = datetime.strptime(date, "%Y-%m-%d")
                    end = start + timedelta(days=1)
                    hist = ticker.history(start=start, end=end, raise_errors=False)
                else:
                    # Latest price (last 7 days to ensure we get data)
                    end = datetime.now()
                    start = end - timedelta(days=7)
                    hist = ticker.history(start=start, end=end, raise_errors=False)

                if hist.empty:
                    print(f"⚠️ No history data for {symbol}, trying alternative method...")
                    # Try using fast_info as fallback
                    try:
                        fast_info = ticker.fast_info
                        if hasattr(fast_info, 'last_price') and fast_info.last_price:
                            result = {
                                'symbol': symbol.upper(),
                                'stock_name': symbol.upper(),
                                'price': float(fast_info.last_price),
                                'currency': fast_info.currency if hasattr(fast_info, 'currency') else ('TRY' if '.IS' in symbol.upper() else 'USD'),
                                'date': datetime.now().strftime("%Y-%m-%d"),
                                'market': self._extract_market(symbol)
                            }
                            print(f"✅ Stock price fetched via fast_info: {symbol} = {result['price']} {result['currency']}")
                            if not date:
                                self._save_to_cache(cache_key, result)
                            return result
                    except Exception as fast_e:
                        print(f"Fast info also failed: {str(fast_e)}")

                    print(f"❌ Stock price not found for symbol: {symbol}")
                    return None

                # Get the last available row
                last_row = hist.iloc[-1]

                # Get stock info (with timeout protection)
                try:
                    info = ticker.info if hasattr(ticker, 'info') else {}
                except:
                    info = {}

                # Fallback stock name if info is empty
                stock_name = symbol.upper()
                if info:
                    stock_name = info.get('longName') or info.get('shortName') or symbol.upper()

                result = {
                    'symbol': symbol.upper(),
                    'stock_name': stock_name,
                    'price': float(last_row['Close']),
                    'currency': info.get('currency', 'TRY' if '.IS' in symbol.upper() else 'USD'),
                    'date': last_row.name.strftime("%Y-%m-%d"),
                    'market': self._extract_market(symbol)
                }

                print(f"✅ Stock price fetched successfully: {symbol} = {result['price']} {result['currency']}")

                # Cache result for current prices
                if not date:
                    self._save_to_cache(cache_key, result)

                return result

            except Exception as e:
                error_msg = f"Attempt {attempt + 1}/{max_retries} failed for {symbol}: {type(e).__name__}: {str(e)}"
                print(error_msg)
                if attempt < max_retries - 1:
                    # Wait before retry (exponential backoff)
                    wait_time = 2 ** attempt  # 1s, 2s, 4s
                    print(f"Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                else:
                    print(f"❌ All retries exhausted for {symbol}. Error: {str(e)}")
                    return None

        return None

    def _get_from_cache(self, key: str) -> Optional[Dict]:
        """Get cached data if not expired"""
        if key in self._cache:
            cached = self._cache[key]
            age = time.time() - cached['timestamp']
            if age < self._cache_ttl:
                return cached['data']
            else:
                # Remove expired cache
                del self._cache[key]
        return None

    def _save_to_cache(self, key: str, data: Dict):
        """Save data to cache"""
        self._cache[key] = {
            'data': data,
            'timestamp': time.time()
        }

    def get_stock_history(self, symbol: str, days: int = 30) -> List[Dict]:
        """
        Get historical stock price data

        Args:
            symbol: Stock symbol
            days: Number of days of history (default: 30)

        Returns:
            List of price points:
            [
                {'date': '2025-12-01', 'price': 250.50, 'volume': 1000000},
                ...
            ]
        """
        try:
            ticker = yf.Ticker(symbol.upper())

            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            hist = ticker.history(start=start_date, end=end_date)

            if hist.empty:
                print(f"No historical data found for symbol: {symbol}")
                return []

            history = []
            for index, row in hist.iterrows():
                history.append({
                    'date': index.strftime("%Y-%m-%d"),
                    'price': float(row['Close']),
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'volume': int(row['Volume'])
                })

            return history

        except Exception as e:
            print(f"Error fetching stock history for {symbol}: {str(e)}")
            return []

    def calculate_profit_loss(
        self,
        symbol: str,
        purchase_price: float,
        purchase_amount: float,
        current_date: Optional[str] = None
    ) -> Dict:
        """
        Calculate profit/loss for a stock investment

        Args:
            symbol: Stock symbol
            purchase_price: Price per share when purchased
            purchase_amount: Total amount invested
            current_date: Optional date for historical calculation

        Returns:
            {
                'symbol': 'AAPL',
                'stock_name': 'Apple Inc.',
                'units': 6.67,
                'current_price': 180.0,
                'current_value': 1200.0,
                'profit_loss': 200.0,
                'profit_loss_percent': 20.0,
                'currency': 'USD'
            }
            or {'error': 'message'} if failed
        """
        try:
            # Calculate units (number of shares)
            units = purchase_amount / purchase_price if purchase_price > 0 else 0

            # Get current price
            price_data = self.get_stock_price(symbol, current_date)

            if not price_data:
                return {'error': f'Could not fetch price for {symbol}'}

            current_price = price_data['price']
            stock_name = price_data['stock_name']
            currency = price_data['currency']

            # Calculate current value
            current_value = units * current_price

            # Calculate profit/loss
            profit_loss = current_value - purchase_amount
            profit_loss_percent = (profit_loss / purchase_amount * 100) if purchase_amount > 0 else 0

            return {
                'symbol': symbol.upper(),
                'stock_name': stock_name,
                'units': round(units, 4),
                'purchase_price': round(purchase_price, 4),
                'current_price': round(current_price, 4),
                'investment_amount': round(purchase_amount, 2),
                'current_value': round(current_value, 2),
                'profit_loss': round(profit_loss, 2),
                'profit_loss_percent': round(profit_loss_percent, 2),
                'currency': currency
            }

        except Exception as e:
            print(f"Error calculating profit/loss for {symbol}: {str(e)}")
            return {'error': str(e)}

    def _extract_market(self, symbol: str) -> str:
        """
        Extract market from symbol

        Args:
            symbol: Stock symbol

        Returns:
            Market code (IST, NYSE, NASDAQ, etc.)
        """
        symbol_upper = symbol.upper()

        if symbol_upper.endswith('.IS'):
            return 'IST'  # Istanbul Stock Exchange
        elif symbol_upper.endswith('.L'):
            return 'LSE'  # London Stock Exchange
        elif symbol_upper.endswith('.HK'):
            return 'HKEX'  # Hong Kong Stock Exchange
        elif symbol_upper.endswith('.T'):
            return 'TSE'  # Tokyo Stock Exchange
        else:
            return 'NYSE'  # Default to NYSE for US stocks

    def search_stocks(self, query: str) -> List[Dict]:
        """
        Search for stocks by name or symbol

        Note: yfinance doesn't have a built-in search API,
        so this returns sample suggestions for common stocks.

        Args:
            query: Search query

        Returns:
            List of stock suggestions
        """
        # Sample common stocks for search
        common_stocks = [
            {'symbol': 'AAPL', 'name': 'Apple Inc.', 'market': 'NASDAQ'},
            {'symbol': 'MSFT', 'name': 'Microsoft Corporation', 'market': 'NASDAQ'},
            {'symbol': 'GOOGL', 'name': 'Alphabet Inc.', 'market': 'NASDAQ'},
            {'symbol': 'AMZN', 'name': 'Amazon.com Inc.', 'market': 'NASDAQ'},
            {'symbol': 'TSLA', 'name': 'Tesla Inc.', 'market': 'NASDAQ'},
            {'symbol': 'THYAO.IS', 'name': 'Türk Hava Yolları', 'market': 'IST'},
            {'symbol': 'AKBNK.IS', 'name': 'Akbank', 'market': 'IST'},
            {'symbol': 'GARAN.IS', 'name': 'Garanti BBVA', 'market': 'IST'},
            {'symbol': 'ISCTR.IS', 'name': 'İş Bankası (C)', 'market': 'IST'},
            {'symbol': 'YKBNK.IS', 'name': 'Yapı Kredi Bankası', 'market': 'IST'},
        ]

        if not query:
            return common_stocks[:10]

        query_lower = query.lower()
        results = [
            stock for stock in common_stocks
            if query_lower in stock['symbol'].lower() or query_lower in stock['name'].lower()
        ]

        return results[:10]


# Singleton instance
stock_service = StockService()

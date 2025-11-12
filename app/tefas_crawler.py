import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json


class TEFASCrawler:
    """TEFAS (Türkiye Elektronik Fon Alım Satım Platformu) veri çekici"""

    BASE_URL = "https://www.tefas.gov.tr"
    FUND_DETAIL_URL = f"{BASE_URL}/FonKartlari.aspx"
    API_URL = f"{BASE_URL}/api/DB/BindHistoryInfo"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
            'X-Requested-With': 'XMLHttpRequest'
        })

    def get_fund_price(self, fund_code: str, date: Optional[str] = None) -> Optional[Dict]:
        """
        Belirli bir fonun fiyat bilgisini getirir

        Args:
            fund_code: TEFAS fon kodu (örn: "TQE", "GAH", "AKE")
            date: Tarih (YYYY-MM-DD formatında, None ise bugün)

        Returns:
            Fon fiyat bilgisi veya None
        """
        try:
            if date is None:
                date = datetime.now().strftime("%Y-%m-%d")

            # TEFAS API endpoint
            params = {
                'fontip': 'YAT',
                'sfontur': '',
                'fonkod': fund_code.upper(),
                'fongrup': '',
                'bastarih': date,
                'bittarih': date,
                'fonturkod': '',
                'fonunvantip': ''
            }

            response = self.session.get(self.API_URL, params=params)
            response.raise_for_status()

            data = response.json()

            if data and len(data) > 0:
                fund_data = data[0]

                return {
                    'fund_code': fund_code.upper(),
                    'fund_name': fund_data.get('FONUNVAN', ''),
                    'price': float(fund_data.get('FIYAT', 0)),
                    'date': fund_data.get('TARIH', date),
                    'total_value': float(fund_data.get('PORTFOYBUYUKLUK', 0)),
                    'number_of_shares': int(fund_data.get('TEDPAYSAYISI', 0)),
                    'number_of_investors': int(fund_data.get('KISISAYISI', 0))
                }

            return None

        except Exception as e:
            print(f"TEFAS veri çekme hatası: {str(e)}")
            return None

    def get_fund_history(self, fund_code: str, days: int = 30) -> List[Dict]:
        """
        Fonun geçmiş fiyat bilgilerini getirir

        Args:
            fund_code: TEFAS fon kodu
            days: Kaç günlük geçmiş (varsayılan 30)

        Returns:
            Fiyat geçmişi listesi
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            params = {
                'fontip': 'YAT',
                'sfontur': '',
                'fonkod': fund_code.upper(),
                'fongrup': '',
                'bastarih': start_date.strftime("%Y-%m-%d"),
                'bittarih': end_date.strftime("%Y-%m-%d"),
                'fonturkod': '',
                'fonunvantip': ''
            }

            response = self.session.get(self.API_URL, params=params)
            response.raise_for_status()

            data = response.json()

            history = []
            for item in data:
                history.append({
                    'date': item.get('TARIH', ''),
                    'price': float(item.get('FIYAT', 0)),
                    'total_value': float(item.get('PORTFOYBUYUKLUK', 0)),
                    'number_of_shares': int(item.get('TEDPAYSAYISI', 0))
                })

            return history

        except Exception as e:
            print(f"TEFAS geçmiş veri çekme hatası: {str(e)}")
            return []

    def search_funds(self, query: str = "") -> List[Dict]:
        """
        Fon arama

        Args:
            query: Arama terimi (boş ise tüm fonları listeler)

        Returns:
            Fon listesi
        """
        try:
            # Tüm fonları getir
            params = {
                'fontip': 'YAT',
                'sfontur': '',
                'fonkod': '',
                'fongrup': '',
                'bastarih': datetime.now().strftime("%Y-%m-%d"),
                'bittarih': datetime.now().strftime("%Y-%m-%d"),
                'fonturkod': '',
                'fonunvantip': ''
            }

            response = self.session.get(self.API_URL, params=params)
            response.raise_for_status()

            data = response.json()

            funds = []
            for item in data:
                fund_code = item.get('FONKODU', '')
                fund_name = item.get('FONUNVAN', '')

                # Arama terimi varsa filtrele
                if query:
                    if query.upper() not in fund_code.upper() and query.upper() not in fund_name.upper():
                        continue

                funds.append({
                    'fund_code': fund_code,
                    'fund_name': fund_name,
                    'price': float(item.get('FIYAT', 0)),
                    'date': item.get('TARIH', ''),
                    'fund_type': item.get('FONTIPI', '')
                })

            return funds

        except Exception as e:
            print(f"TEFAS fon arama hatası: {str(e)}")
            return []

    def calculate_profit_loss(
        self,
        fund_code: str,
        purchase_price: float,
        purchase_amount: float,
        current_date: Optional[str] = None
    ) -> Dict:
        """
        Kar/zarar hesaplama

        Args:
            fund_code: Fon kodu
            purchase_price: Alış fiyatı
            purchase_amount: Alış miktarı (TL)
            current_date: Güncel tarih (None ise bugün)

        Returns:
            Kar/zarar bilgisi
        """
        try:
            current_data = self.get_fund_price(fund_code, current_date)

            if not current_data:
                return {
                    'error': 'Fon verisi alınamadı'
                }

            current_price = current_data['price']
            units = purchase_amount / purchase_price
            current_value = units * current_price
            profit_loss = current_value - purchase_amount
            profit_loss_percent = (profit_loss / purchase_amount) * 100

            return {
                'fund_code': fund_code,
                'fund_name': current_data['fund_name'],
                'purchase_price': purchase_price,
                'current_price': current_price,
                'units': round(units, 4),
                'purchase_amount': purchase_amount,
                'current_value': round(current_value, 2),
                'profit_loss': round(profit_loss, 2),
                'profit_loss_percent': round(profit_loss_percent, 2),
                'date': current_data['date']
            }

        except Exception as e:
            return {
                'error': f'Hesaplama hatası: {str(e)}'
            }


# Test fonksiyonu
if __name__ == "__main__":
    crawler = TEFASCrawler()

    # Örnek: TQE fonu fiyatını getir
    print("TQE Fon Fiyatı:")
    price = crawler.get_fund_price("TQE")
    print(json.dumps(price, indent=2, ensure_ascii=False))

    # Örnek: Kar/zarar hesaplama
    print("\nKar/Zarar Hesaplama:")
    result = crawler.calculate_profit_loss(
        fund_code="TQE",
        purchase_price=0.050000,
        purchase_amount=1000
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))

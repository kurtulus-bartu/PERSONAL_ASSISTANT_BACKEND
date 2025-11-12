import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import time


class TEFASCrawler:
    """TEFAS (Türkiye Elektronik Fon Alım Satım Platformu) veri çekici"""

    BASE_URL = "https://www.tefas.gov.tr"
    FUND_DETAIL_URL = f"{BASE_URL}/FonKartlari.aspx"
    API_URL = f"{BASE_URL}/api/DB/BindHistoryInfo"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.tefas.gov.tr/FonAnaliz.aspx',
            'Origin': 'https://www.tefas.gov.tr',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin'
        })
        self.last_request_time = 0
        self.min_request_interval = 0.5  # Minimum 500ms between requests

    def _rate_limit(self):
        """Rate limiting - istekler arasında minimum bekleme süresi"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last_request)
        self.last_request_time = time.time()

    def _safe_request(self, url: str, params: dict, timeout: int = 10) -> Optional[List[Dict]]:
        """Güvenli HTTP request - JSON parse hatalarını yakalar"""
        try:
            self._rate_limit()

            response = self.session.get(url, params=params, timeout=timeout)
            response.raise_for_status()

            # Response boş mu kontrol et
            if not response.text or response.text.strip() == '':
                print(f"TEFAS API boş yanıt döndürdü")
                return None

            # HTML hatası mı kontrol et
            if response.text.strip().startswith('<'):
                print(f"TEFAS API HTML döndürdü (muhtemelen hata sayfası)")
                return None

            # JSON parse et
            try:
                data = response.json()
                if isinstance(data, list):
                    return data
                else:
                    print(f"TEFAS API beklenmeyen format döndürdü: {type(data)}")
                    return None
            except json.JSONDecodeError as e:
                print(f"TEFAS JSON parse hatası: {str(e)}")
                print(f"Response içeriği (ilk 200 karakter): {response.text[:200]}")
                return None

        except requests.Timeout:
            print(f"TEFAS API timeout")
            return None
        except requests.RequestException as e:
            print(f"TEFAS API istek hatası: {str(e)}")
            return None
        except Exception as e:
            print(f"TEFAS beklenmeyen hata: {str(e)}")
            return None

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
                date = datetime.now().strftime("%d.%m.%Y")
            else:
                # Convert YYYY-MM-DD to DD.MM.YYYY (TEFAS format)
                date_obj = datetime.strptime(date, "%Y-%m-%d")
                date = date_obj.strftime("%d.%m.%Y")

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

            data = self._safe_request(self.API_URL, params)

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
                'bastarih': start_date.strftime("%d.%m.%Y"),
                'bittarih': end_date.strftime("%d.%m.%Y"),
                'fonturkod': '',
                'fonunvantip': ''
            }

            data = self._safe_request(self.API_URL, params)

            if not data:
                return []

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
            # Tüm fonları getir (bugünün verisi)
            today = datetime.now().strftime("%d.%m.%Y")

            params = {
                'fontip': 'YAT',
                'sfontur': '',
                'fonkod': '',
                'fongrup': '',
                'bastarih': today,
                'bittarih': today,
                'fonturkod': '',
                'fonunvantip': ''
            }

            data = self._safe_request(self.API_URL, params, timeout=15)

            if not data:
                print("TEFAS fon listesi alınamadı, örnek veri döndürülüyor")
                # Fallback: Popüler fonların örnek listesi
                return self._get_sample_funds(query)

            funds = []
            for item in data:
                fund_code = item.get('FONKODU', '')
                fund_name = item.get('FONUNVAN', '')

                # Arama terimi varsa filtrele
                if query:
                    query_upper = query.upper()
                    if query_upper not in fund_code.upper() and query_upper not in fund_name.upper():
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
            return self._get_sample_funds(query)

    def _get_sample_funds(self, query: str = "") -> List[Dict]:
        """Örnek fon listesi - TEFAS erişilemediğinde fallback"""
        sample_funds = [
            {'fund_code': 'TQE', 'fund_name': 'Tacirler Portföy Değişken Fon', 'price': 0.050000, 'date': datetime.now().strftime("%d.%m.%Y"), 'fund_type': 'Değişken Fon'},
            {'fund_code': 'GAH', 'fund_name': 'Garanti Portföy Altın Fonu', 'price': 0.042000, 'date': datetime.now().strftime("%d.%m.%Y"), 'fund_type': 'Değişken Fon'},
            {'fund_code': 'AKE', 'fund_name': 'Ak Portföy Eurobond Dolar Fonu', 'price': 0.015000, 'date': datetime.now().strftime("%d.%m.%Y"), 'fund_type': 'Borçlanma Araçları Fonu'},
            {'fund_code': 'YKT', 'fund_name': 'Yapı Kredi Portföy Teknoloji Sektörü Fonu', 'price': 0.025000, 'date': datetime.now().strftime("%d.%m.%Y"), 'fund_type': 'Hisse Senedi Fonu'},
            {'fund_code': 'IPG', 'fund_name': 'İş Portföy Gelişen Ülkeler Fonu', 'price': 0.018000, 'date': datetime.now().strftime("%d.%m.%Y"), 'fund_type': 'Hisse Senedi Fonu'},
        ]

        if query:
            query_upper = query.upper()
            return [f for f in sample_funds if query_upper in f['fund_code'] or query_upper in f['fund_name'].upper()]

        return sample_funds

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
                    'error': 'Fon verisi alınamadı. Lütfen fon kodunu kontrol edin veya daha sonra tekrar deneyin.'
                }

            current_price = current_data['price']

            # Eğer fiyat 0 ise hata döndür
            if current_price == 0:
                return {
                    'error': 'Fon fiyatı bulunamadı'
                }

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

    # Örnek: Fon arama
    print("\nFon Arama (YKT):")
    funds = crawler.search_funds("YKT")
    print(json.dumps(funds[:3], indent=2, ensure_ascii=False))

    # Örnek: Kar/zarar hesaplama
    print("\nKar/Zarar Hesaplama:")
    result = crawler.calculate_profit_loss(
        fund_code="TQE",
        purchase_price=0.050000,
        purchase_amount=1000
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))

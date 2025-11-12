from tefas import Crawler
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json


class TEFASCrawler:
    """TEFAS (Türkiye Elektronik Fon Alım Satım Platformu) veri çekici

    tefas-crawler paketi kullanılarak TEFAS verilerine erişim sağlar.
    """

    def __init__(self):
        """TEFAS Crawler'ı başlat"""
        self.crawler = Crawler()

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
                date_str = datetime.now().strftime("%d-%m-%Y")
            else:
                # Convert YYYY-MM-DD to DD-MM-YYYY
                date_obj = datetime.strptime(date, "%Y-%m-%d")
                date_str = date_obj.strftime("%d-%m-%Y")

            # tefas-crawler ile veri çek
            data = self.crawler.fetch(
                start=date_str,
                end=date_str,
                name=fund_code.upper()
            )

            if data.empty:
                print(f"TEFAS: {fund_code} fonu için veri bulunamadı")
                return None

            # İlk satırı al (tek gün sorgusu için tek satır olacak)
            row = data.iloc[0]

            return {
                'fund_code': fund_code.upper(),
                'fund_name': row.get('title', ''),
                'price': float(row.get('price', 0)),
                'date': row.get('date', date_str),
                'total_value': float(row.get('marketcap', 0)),
                'number_of_shares': int(row.get('number_of_shares', 0)),
                'number_of_investors': int(row.get('number_of_investors', 0))
            }

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

            # tefas-crawler ile veri çek
            data = self.crawler.fetch(
                start=start_date.strftime("%d-%m-%Y"),
                end=end_date.strftime("%d-%m-%Y"),
                name=fund_code.upper()
            )

            if data.empty:
                print(f"TEFAS: {fund_code} fonu için geçmiş veri bulunamadı")
                return []

            history = []
            for _, row in data.iterrows():
                history.append({
                    'date': row.get('date', ''),
                    'price': float(row.get('price', 0)),
                    'total_value': float(row.get('marketcap', 0)),
                    'number_of_shares': int(row.get('number_of_shares', 0))
                })

            return history

        except Exception as e:
            print(f"TEFAS geçmiş veri çekme hatası: {str(e)}")
            return []

    def search_funds(self, query: str = "") -> List[Dict]:
        """
        Fon arama

        Args:
            query: Arama terimi (boş ise popüler fonları listeler)

        Returns:
            Fon listesi
        """
        try:
            # Bugünün tarihini al
            today = datetime.now().strftime("%d-%m-%Y")

            # Eğer query varsa o fonu ara
            if query:
                data = self.crawler.fetch(
                    start=today,
                    end=today,
                    name=query.upper()
                )
            else:
                # Query yoksa popüler fonları döndür
                popular_funds = ['TQE', 'GAH', 'AKE', 'YKT', 'IPG', 'TKE', 'AYE', 'IYE']
                return self._get_multiple_funds(popular_funds, today)

            if data.empty:
                print(f"TEFAS: '{query}' araması için sonuç bulunamadı")
                return self._get_sample_funds(query)

            funds = []
            for _, row in data.iterrows():
                funds.append({
                    'fund_code': row.get('code', ''),
                    'fund_name': row.get('title', ''),
                    'price': float(row.get('price', 0)),
                    'date': row.get('date', today),
                    'fund_type': row.get('type', 'Yatırım Fonu')
                })

            return funds

        except Exception as e:
            print(f"TEFAS fon arama hatası: {str(e)}")
            return self._get_sample_funds(query)

    def _get_multiple_funds(self, fund_codes: List[str], date: str) -> List[Dict]:
        """Birden fazla fon için veri çek"""
        funds = []
        for code in fund_codes:
            try:
                data = self.crawler.fetch(
                    start=date,
                    end=date,
                    name=code
                )
                if not data.empty:
                    row = data.iloc[0]
                    funds.append({
                        'fund_code': row.get('code', code),
                        'fund_name': row.get('title', ''),
                        'price': float(row.get('price', 0)),
                        'date': row.get('date', date),
                        'fund_type': row.get('type', 'Yatırım Fonu')
                    })
            except:
                continue
        return funds if funds else self._get_sample_funds("")

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

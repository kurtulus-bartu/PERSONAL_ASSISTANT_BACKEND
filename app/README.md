# Personal Assistant Backend API

iOS Personal Assistant uygulaması için Python backend servisi. TEFAS fon verileri çekme ve Gemini AI entegrasyonu sağlar.

## Özellikler

- **TEFAS Crawler**: Türkiye Elektronik Fon Alım Satım Platformu'ndan gerçek zamanlı fon verileri çekme
- **Portföy Yönetimi**: Kullanıcının fon yatırımlarını takip etme ve kar/zarar hesaplama
- **Gemini AI**: Google Gemini ile portföy analizi ve finansal tavsiyeler
- **RESTful API**: FastAPI ile hızlı ve güvenilir API endpoints

## Teknolojiler

- **FastAPI**: Modern, hızlı web framework
- **BeautifulSoup**: Web scraping için
- **Google Generative AI**: Gemini API entegrasyonu
- **Uvicorn**: ASGI server

## Kurulum

### Gereksinimler

- Python 3.9+
- pip

### Lokal Geliştirme

1. Repoyu klonlayın:
```bash
git clone <repo-url>
cd backend
```

2. Virtual environment oluşturun:
```bash
python -m venv venv
source venv/bin/activate  # Mac/Linux
# veya
venv\Scripts\activate  # Windows
```

3. Bağımlılıkları yükleyin:
```bash
pip install -r requirements.txt
```

4. `.env` dosyası oluşturun:
```bash
cp .env.example .env
```

`.env` dosyasını düzenleyin ve Gemini API anahtarınızı ekleyin:
```
GEMINI_API_KEY=your_actual_api_key_here
```

5. Sunucuyu başlatın:
```bash
uvicorn app.main:app --reload
```

API şu adreste çalışacak: http://localhost:8000

API dokümantasyonu: http://localhost:8000/docs

## API Endpoints

### TEFAS Endpoints

#### Fon Fiyatı Getir
```
GET /api/funds/price/{fund_code}?date=2025-01-15
```

Örnek:
```bash
curl http://localhost:8000/api/funds/price/TQE
```

#### Fon Geçmişi
```
GET /api/funds/history/{fund_code}?days=30
```

#### Fon Arama
```
GET /api/funds/search?query=tacirler
```

#### Portföy Hesaplama
```
POST /api/portfolio/calculate
```

Body:
```json
[
  {
    "fund_code": "TQE",
    "fund_name": "Tacirler Portföy Değişken Fon",
    "investment_amount": 5000,
    "purchase_price": 0.050000,
    "purchase_date": "2025-01-01T00:00:00",
    "units": 100000
  }
]
```

### Gemini AI Endpoints

#### AI Chat
```
POST /api/ai/chat
```

Body:
```json
{
  "message": "Portföyüm hakkında ne düşünüyorsun?",
  "context": "{\"total_investment\": 10000, \"current_value\": 10500}",
  "api_key": "your_gemini_api_key"
}
```

#### Portföy Analizi (AI)
```
POST /api/ai/analyze-portfolio
```

## Render'a Deploy Etme

1. GitHub'a kod yükleme:
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin <your-github-repo-url>
git push -u origin main
```

2. Render Dashboard'a gidin: https://render.com

3. "New" → "Web Service" seçin

4. GitHub reponuzu bağlayın

5. Ayarları yapın:
   - **Name**: personal-assistant-backend
   - **Environment**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

6. Environment Variables ekleyin:
   - `GEMINI_API_KEY`: Gemini API anahtarınız
   - `ENVIRONMENT`: production

7. "Create Web Service" butonuna tıklayın

Deploy sonrası URL'niz: `https://personal-assistant-backend.onrender.com`

## Test

### TEFAS Crawler Test
```bash
python -m app.tefas_crawler
```

### Gemini Service Test
```bash
export GEMINI_API_KEY=your_key
python -m app.gemini_service
```

## iOS Entegrasyonu

iOS uygulamanızdan API'yi kullanmak için:

```swift
let baseURL = "https://your-backend.onrender.com"

// Fon fiyatı getir
let url = URL(string: "\(baseURL)/api/funds/price/TQE")!
```

## Supabase (Portföy geçmişi)

Finans ekranındaki günlük/haftalık grafikler Supabase üzerinde tutulan `fund_daily_values` tablosundan
gelir.

### Ortam değişkenleri

`.env` dosyanıza veya Render paneline aşağıdakileri ekleyin:

```
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service_role_key>
```

### Tablo şeması

Aşağıdaki SQL script'i tabloyu oluşturur:

```sql
create table if not exists fund_daily_values (
    id uuid primary key default gen_random_uuid(),
    snapshot_date date not null,
    recorded_at timestamptz not null default now(),
    fund_code text not null,
    fund_name text,
    current_value numeric not null,
    investment_amount numeric,
    profit_loss numeric,
    profit_loss_percent numeric,
    current_price numeric,
    units numeric,
    inserted_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists fund_daily_values_unique_idx
    on fund_daily_values (fund_code, snapshot_date);
```

> Backend her kar/zarar hesaplamasında fonlar + `TOTAL` satırı için upsert gerçekleştirir.
> Eksik günler, TEFAS verisiyle otomatik doldurulur.

## Güvenlik

- API anahtarlarını **asla** kod içinde tutmayın
- `.env` dosyasını git'e eklemeyin (`.gitignore`'da)
- Production'da CORS ayarlarını spesifik domain'e sınırlayın

## Lisans

MIT

## Katkıda Bulunma

Pull request'ler kabul edilir. Büyük değişiklikler için önce bir issue açın.

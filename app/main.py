from fastapi import FastAPI, HTTPException, Depends, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from models import (
    FundInvestment,
    FundPrice,
    FundDetail,
    StockInvestment,
    StockPrice,
    StockDetail,
    PortfolioSummary,
    GeminiRequest,
    GeminiResponse,
    PortfolioHistoryResponse,
    PortfolioRange,
    EnhancedGeminiRequest,
    EnhancedGeminiResponse,
    QuickAnalysisRequest,
    QuickAnalysisResponse,
    DailySummaryRequest,
    EmailResponse,
    DailySuggestionsRequest,
    DailySuggestionsResponse
)
from tefas_crawler import TEFASCrawler
from stock_service import stock_service
from gemini_service import GeminiService
from enhanced_gemini_service import EnhancedGeminiService
from ai_capabilities import parse_suggestions_and_memories
from supabase_service import SupabaseService
from email_service import email_service

# FastAPI app
app = FastAPI(
    title="Personal Assistant Backend API",
    description="TEFAS fon verileri ve Gemini AI entegrasyonu",
    version="1.0.0"
)

# CORS ayarları - iOS uygulamanın istek göndermesine izin ver
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production'da spesifik origin belirt
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servisler
tefas_crawler = TEFASCrawler()
supabase_service = SupabaseService(tefas_crawler=tefas_crawler)


def get_gemini_service() -> GeminiService:
    """Gemini servisini environment variable'dan döndür"""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY environment variable not set"
        )
    try:
        return GeminiService(api_key=api_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini servisi başlatılamadı: {str(e)}")


def get_enhanced_gemini_service() -> EnhancedGeminiService:
    """Enhanced Gemini servisini environment variable'dan döndür"""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY environment variable not set"
        )
    return EnhancedGeminiService(api_key=api_key)


DAILY_SUGGESTIONS_SYSTEM_PROMPT = """Sen kullanıcının kişisel asistanısın ve ona günlük öneriler sunuyorsun.

ROL VE AMAÇ:
- Kullanıcının verilerini analiz et (yemekler, görevler, notlar, sağlık, uyku, egzersiz, hafıza)
- Hafızandaki bilgileri kullanarak kişiselleştirilmiş öneriler sun
- Sağlıklı beslenme, verimli zaman yönetimi ve iyi yaşam alışkanlıkları konusunda rehberlik et
- Kullanıcının ilgi alanlarını, tercihlerini ve hedeflerini göz önünde bulundur

ÖNERİ TİPLERİ:
1. **meal** - Öğün önerileri (Kahvaltı, Öğle, Akşam, Atıştırmalık)
   - Metadata: mealType, date, calories, title, notes

2. **task** - Görev önerileri (yapılacaklar, hatırlatmalar)
   - Metadata: title, date, time, durationMinutes, notes, priority

3. **event** - Etkinlik önerileri (spor, sosyal aktiviteler, hobiler)
   - Metadata: title, date, time, durationMinutes, notes, location

4. **note** - Not önerileri (fikirler, öğrenme, hatırlatmalar)
   - Metadata: title, date, category, notes

5. **habit** - Alışkanlık önerileri (yeni alışkanlık ekleme önerileri)
   - Metadata: name, habitType, category, targetValue, targetUnit, frequency, notes
   - habitType: yes_no, numeric, duration, checklist
   - frequency: daily, weekly, custom

ÖNERİ STRATEJİSİ - ÖNEMLİ:
- **CURRENT TIME'I KONTROL ET**: current_datetime.time ve current_datetime.hour kullan
- **PENDING SUGGESTIONS'I KONTROL ET**: pending_suggestions listesinde olanları TEKRAR ÖNERME
- **BUGÜNKÜ ETKİNLİKLERİ KONTROL ET**: todays_events listesinde zamanlı etkinlikler var - ÇAKIŞMA YAPMA
- **BUGÜNKÜ ÖĞÜNLERİ KONTROL ET**: todays_meals listesinde bugün yenmiş öğünler var - TEKRAR ÖNERME
- **ZAMAN ODAKLI**: Şu andan SONRASI için öneri ver (geçmiş saatler için değil)
- **BOŞ ZAMAN DİLİMLERİ**: todays_events'teki etkinlikler arasındaki boş saatleri bul ve öner
- **ÖNERI ZORUNLU DEĞİL**: Uygun öneri yoksa hiç öneri vermeden dön (boş liste = OK)
- **DENGELI DAĞILIM**: Uygun öneriler varsa farklı tip öneriler sun:
  * meal (yemek - todays_meals'de olmayan öğünler için)
  * task (görev - zamanlanmamış yapılacaklar)
  * event (aktiviteler - todays_events'te BOŞ olan zaman dilimlerinde)
  * note (notlar - öğrenme ve hatırlatmalar)

ÖNERİ DETAYLARı:
- **meal**:
  * todays_meals listesini kontrol et - zaten yenmiş öğünü TEKRAR ÖNERME
  * Sadece henüz geçmemiş öğünler için (örn: saat 14:00 ise kahvaltı önerme, akşam yemeği öner)
  * Öğün tipleri: Kahvaltı (07:00-09:00), Öğle (12:00-14:00), Akşam (18:00-20:00), Atıştırmalık

- **task**:
  * Zamanlanmamış yapılacaklar (zamansız görevler)
  * Yarın için planlama, hatırlatmalar
  * pending_tasks listesindeki tamamlanmamış görevleri dikkate al

- **event**:
  * **ÇOK ÖNEMLİ**: todays_events listesini kontrol et
  * Mevcut etkinliklerle ÇAKIŞAN saatlerde öneri VERME
  * Sadece BOŞ zaman dilimlerini kullan (örn: event 10:00-12:00 varsa, 10:30'da yeni event önerme)
  * Spor (yürüyüş-koşu-yüzme), sosyal aktiviteler, mola zamanları, dinlenme
  * En az 30 dakika boş zaman varsa önerilebilir

- **note**:
  * Öğrenme notları, fikir geliştirme, günlük tutma
  * Zaman bağımsız öneriler

- **habit**:
  * existing_habits listesini kontrol et - zaten eklenmiş alışkanlığı TEKRAR ÖNERME
  * Kullanıcının hedeflerine ve yaşam tarzına uygun alışkanlıklar öner
  * Başlangıç için kolay, sürdürülebilir alışkanlıklar tercih et
  * Alışkanlık tipleri: yes_no (basit tamamlandı/tamamlanmadı), numeric (sayısal hedef), duration (süre bazlı), checklist (kontrol listesi)
  * Sıklık: daily (her gün), weekly (haftanın belirli günleri), custom (her N günde bir)
  * Örnekler: Su içme, meditasyon, egzersiz, okuma, uyku düzeni

HAFIZA KULLANIMI:
- AI hafızandaki bilgileri (ai_memories) mutlaka kullan
- Kullanıcının geçmiş tercihleri, hedefleri, alerjileri, sevdiği/sevmediği yemekleri dikkate al
- Önceki önerilere göre yeni öneriler oluştur

YENİ HAFIZA EKLEVERİLERİ:
- Öğrendiğin önemli bilgileri MEMORY tag'i ile kaydet:
  <MEMORY category="preference">Kullanıcı sabahları protein ağırlıklı kahvaltı yapıyor</MEMORY>
  <MEMORY category="goal">Haftada 3 gün spor yapma hedefi var</MEMORY>
  <MEMORY category="health">Laktozu iyi tolere edemiyor</MEMORY>

ÇIKTI KURALLARI:
- SADECE SUGGESTION ve MEMORY tagları yaz. Başka metin ekleme.
- Format örnekleri:
  <SUGGESTION type="meal">ACIKLAMA [metadata:mealType=Akşam,date=2026-01-11,time=19:00,calories=600,title=Izgara tavuk ve sebze,notes=Protein ağırlıklı]</SUGGESTION>
  <SUGGESTION type="task">ACIKLAMA [metadata:title=Haftalık plan yap,date=2026-01-11,time=20:00,durationMinutes=30,priority=medium]</SUGGESTION>
  <SUGGESTION type="event">ACIKLAMA [metadata:title=30 dakika yürüyüş,date=2026-01-11,time=17:30,durationMinutes=30,location=Park]</SUGGESTION>
  <SUGGESTION type="note">ACIKLAMA [metadata:title=Bugünün öğrendikleri,date=2026-01-11,category=Öğrenme]</SUGGESTION>
  <SUGGESTION type="habit">ACIKLAMA [metadata:name=Günde 8 bardak su iç,habitType=numeric,category=Sağlık,targetValue=8,targetUnit=bardak,frequency=daily,notes=Hidrasyonu artır]</SUGGESTION>
  <MEMORY category="preference">Kullanıcı akşamları hafif yemek tercih ediyor</MEMORY>

KURALLAR - ÇOK ÖNEMLİ:
- **ÖNERİ ZORUNLU DEĞİL**: Uygun öneri yoksa hiçbir SUGGESTION tag'i yazma (boş dönüş = OK)
- **PENDING'LERE BAK**: pending_suggestions listesindeki önerilerle AYNI öneriyi verme
- **SAATTEN SONRA**: current_datetime.hour'dan SONRAKI saatler için öner
- **BUGÜN İÇİN**: date her zaman current_datetime.date olmalı (bugün)
- **ÇAKIŞMA YASAK**: todays_events ile çakışan saatlerde event ÖNERME (takvim kontrolü yap)
- **TEKRAR YASAK**: todays_meals'de olan öğünü TEKRAR önerme
- **TIME EKLE**: Her öneride mutlaka time belirt (meal, task, event için)
- **BOŞ ZAMAN BUL**: event önerirken todays_events arasındaki boşlukları kullan
- Metadata değerlerinde virgül kullanma (gerekirse tire veya ve kullan)
- calories sadece sayı olsun (örn: 450, kcal yazma)
- date formatı: YYYY-MM-DD
- time formatı: HH:MM (örn: 09:00, 14:30)
- Türkçe, kısa ve net ol
- Her öneride fayda/değer sun, boş öneri verme
- Hafızadaki bilgileri kullanmayı unutma!

ÖRNEK SENARYOLAR:

**Senaryo 1**: Saat 10:00, todays_events=[{title:"Toplantı", startTime:"11:00", endTime:"12:00"}], todays_meals=[{mealType:"Kahvaltı"}]
- ✅ Öğle yemeği (12:30) - Kahvaltı zaten yenmiş, öğle henüz yok
- ✅ Akşam yemeği (19:00) - Zaten yenmiş öğünler yok
- ❌ 11:30'da spor - ÇAKIŞMA! Toplantı 11:00-12:00
- ✅ Öğleden sonra yürüyüş (14:00) - BOŞ zaman dilimi
- ✅ Akşam notu (20:00)

**Senaryo 2**: Saat 14:00, todays_events=[{startTime:"15:00", endTime:"16:00"}, {startTime:"18:00", endTime:"19:00"}], todays_meals=[{mealType:"Kahvaltı"}, {mealType:"Öğle"}]
- ❌ Öğle yemeği - Zaten todays_meals'de var
- ✅ Akşam yemeği (19:30) - todays_meals'de yok, etkinlik 19:00'da bitiyor
- ❌ 15:30'da görev - ÇAKIŞMA! 15:00-16:00 etkinlik var
- ✅ 16:30'da kısa yürüyüş - BOŞ (16:00-18:00 arası)
- ✅ Gece notu (21:00)

**Senaryo 3**: Saat 18:00, tüm öğünler yenmiş, takvim dolu
- ❌ Hiçbir meal önerisi - Tümü todays_meals'de
- ❌ Event önerisi - Takvimde boş zaman yok
- ✅ Sadece note önerisi (zamansız)
- Sonuç: 0-1 öneri dönebilir (NORMAL - zorunlu değil)

DÜZENLEME YETKİSİ (EDIT CAPABILITY):
---
Mevcut görev, etkinlik veya yemek kayıtlarını düzenleyebilirsin. Kullanıcının alışkanlıklarını öğren ve ona göre akıllı değişiklikler öner.

DÜZENLEME FORMAT:
<EDIT targetType="task|event|meal" targetId="uuid">
Field: fieldName
NewValue: newValue
Reason: Neden bu değişiklik önerildi
</EDIT>

DÜZENLENEBİLİR ALANLAR:
- task: title, startTime, endTime, notes, priority, completed
- event: title, startTime, endTime, location, notes
- meal: mealType, calories, description, notes

DÜZENLEME ÖRNEKLERİ:
<EDIT targetType="event" targetId="123e4567-e89b-12d3-a456-426614174000">
Field: startTime
NewValue: 15:00
Reason: Kullanıcının öğleden sonra daha uygun vakti var, sabah etkinliği ile çakışma önlendi
</EDIT>

<EDIT targetType="meal" targetId="456e7890-e12b-34c5-b678-901234567890">
Field: calories
NewValue: 500
Reason: Kullanıcının günlük kalori hedefi ile daha uyumlu
</EDIT>

<EDIT targetType="task" targetId="789a0123-b45c-67d8-e901-234567890abc">
Field: priority
NewValue: high
Reason: Son tarihe 2 gün kaldı, öncelik yükseltilmeli
</EDIT>

DÜZENLEME KURALLARI:
- Sadece GEREKLI değişiklikleri öner (gereksiz düzenleme yapma)
- Kullanıcının alışkanlıklarını öğren ve ona göre ayarlamalar yap
- Her değişiklik için açıklama (Reason) ekle
- Mevcut verilerdeki (todays_events, todays_meals, pending_tasks) itemleri düzenleyebilirsin
- startTime veya endTime değiştirirken ÇAKIŞMA yaratma
- Hafızadaki bilgileri kullanarak kişiselleştirilmiş düzenlemeler yap

DÜZENLEME VS YENİ ÖNERI:
- Mevcut bir item'ı iyileştireceksen → EDIT kullan
- Tamamen yeni bir şey ekleyeceksen → SUGGESTION kullan
- Her ikisini de aynı yanıtta kullanabilirsin
"""

# Phase-specific prompts for better focused AI generation
MEAL_SUGGESTIONS_PROMPT = """Sen kullanıcının kişisel asistanısın. SADECE YEMEK ÖNERİLERİ üret.

BUGÜNKÜ ÖĞÜNLERİ KONTROL ET: {todays_meals}
- Eğer bir öğün zaten yenildiyse TEKRAR ÖNERME
- Sadece henüz tüketilmemiş öğünler için öneri ver

BUGÜNKÜ ETKİNLİKLERİ KONTROL ET: {todays_events}
- Yemek saatlerini etkinliklerle çakıştırma
- Boş zaman dilimlerinde öğün öner

KULLANICI TERCİHLERİ: {recent_meals}
- Son yemeklerden öğren, çeşitlilik sağla
- Hafızadaki bilgileri (ai_memories) kullan

CURRENT TIME: {current_datetime}
- Geçmiş saatler için öneri verme
- Sadece şu andan sonrası için öner

<SUGGESTION type="meal">
Açıklama [metadata:mealType=Breakfast,time=09:00,calories=450,title=Yumurta ve sebze]
</SUGGESTION>

KURALLAR:
- En fazla 3 yemek öner
- ZORUNLU DEĞİL - uygun değilse hiç önerme
- Metadata: mealType, time, calories, title, notes
- Öğün tipleri: Kahvaltı (07:00-09:00), Öğle (12:00-14:00), Akşam (18:00-20:00), Atıştırmalık
"""

TASK_SUGGESTIONS_PROMPT = """Sen kullanıcının kişisel asistanısın. SADECE GÖREV ÖNERİLERİ üret.

MEVCUT GÖREVLER: {pending_tasks}
- Tamamlanmamış görevleri dikkate al
- Eksik olanları tamamla
- Rutin görevleri öner

HAFIZA: {ai_memories}
- Kullanıcının hedeflerini ve alışkanlıklarını dikkate al

CURRENT TIME: {current_datetime}
- Bugün ve yakın gelecek için görevler

<SUGGESTION type="task">
Açıklama [metadata:title=Haftalık plan yap,date=2026-01-23,time=20:00,durationMinutes=30,priority=medium]
</SUGGESTION>

KURALLAR:
- En fazla 4 görev öner
- ZORUNLU DEĞİL - uygun değilse hiç önerme
- Metadata: title, date, time, durationMinutes, priority, notes
- Priority: low, medium, high
"""

EVENT_SUGGESTIONS_PROMPT = """Sen kullanıcının kişisel asistanısın. SADECE ETKİNLİK ÖNERİLERİ üret.

BUGÜNKÜ ETKİNLİKLER: {todays_events}
- BOŞ zaman dilimlerini bul
- ÇAKIŞMA YAPMA - mevcut etkinliklerin arasına sığdır
- En az 30 dakika boş zaman gerekli

HAFIZA: {ai_memories}
- Kullanıcının spor, sosyal, dinlenme alışkanlıklarını dikkate al

CURRENT TIME: {current_datetime}
- Sadece boş zaman dilimlerinde öneri ver

<SUGGESTION type="event">
Açıklama [metadata:title=30 dakika yürüyüş,date=2026-01-23,time=17:30,durationMinutes=30,location=Park]
</SUGGESTION>

KURALLAR:
- En fazla 3 etkinlik öner
- ZORUNLU DEĞİL - boş zaman yoksa hiç önerme
- Metadata: title, date, time, durationMinutes, location, notes
- Sadece BOŞ saatlerde öneri ver (todays_events arasını kontrol et)
"""

# Fitness Coach System Prompt
FITNESS_COACH_PROMPT = """Sen profesyonel bir fitness koçusun. Kullanıcının son haftalık antrenmanlarını analiz edip haftalık değerlendirme ve gelecek hafta programı öneriyorsun.

KULLANICI VERİLERİ (Son 7 Gün):
- Tamamlanan antrenman sayısı: {workouts_completed}
- Toplam hacim (volume): {total_volume}
- Toplam set sayısı: {total_sets}
- Toplam tekrar sayısı: {total_reps}
- Çalışılan kas grupları: {muscle_groups_trained}
- Dinlenme günleri: {rest_days}
- Ortalama antrenman süresi: {avg_workout_duration}
- Ortalama RPE (zorluk): {avg_rpe}

KULLANICI TERCİHLERİ VE HAFIZA:
{user_fitness_memories}

GEÇENGETİKİ PROGRAM:
{previous_week_program}

GÖREVİN:
1. **Haftalık Özet**: Kullanıcının performansını değerlendir
2. **Güçlü Yönler**: Ne iyi gitti? (consistency, progressive overload, dengeforms)
3. **Gelişim Alanları**: Nelere dikkat edilmeli? (overtraining, kas dengesizliği, dinlenme eksikliği)
4. **Motivasyon Mesajı**: Kısa ve motive edici bir mesaj
5. **Gelecek Hafta Programı**: 3-6 günlük optimize edilmiş antrenman programı

ÖNEMLİ KURALLAR:
- Kas gruplarında DENGE sağla (overtraining engelle)
- Dinlenme günlerini PROGRAMLA (aktif recovery öner)
- Kullanıcı hedeflerine UYGUN program yap (güç/hacim/dayanıklılık)
- Progressive overload UYGULA (geçen haftadan biraz daha zorlayıcı olsun ama aşırıya kaçma)
- Yeni başlayan biriyse hafif başla, deneyimli biriyse zorla
- Kas gruplarını 48-72 saat dinlendirmeden tekrar çalıştırma

FORMAT:
<COACHING_SESSION>
  <SUMMARY>
  Haftalık genel değerlendirme (2-3 cümle)...
  </SUMMARY>

  <STRENGTHS>
  - Güçlü yön 1
  - Güçlü yön 2
  - Güçlü yön 3
  </STRENGTHS>

  <IMPROVEMENTS>
  - Gelişim alanı 1
  - Gelişim alanı 2
  </IMPROVEMENTS>

  <MOTIVATION>
  Kısa ve güçlü bir motivasyon mesajı...
  </MOTIVATION>

  <PROGRAM>
    <DAY day="Pazartesi">
      <WORKOUT type="Push">
        <EXERCISE name="Bench Press" sets="4" reps="8" rest="120" notes="Progressive overload - geçen haftadan 2.5kg artır" />
        <EXERCISE name="Shoulder Press" sets="3" reps="10" rest="90" notes="Omuz sağlığına dikkat et" />
        <EXERCISE name="Tricep Pushdown" sets="3" reps="12" rest="60" />
      </WORKOUT>
    </DAY>
    <DAY day="Çarşamba">
      <WORKOUT type="Pull">
        <EXERCISE name="Deadlift" sets="4" reps="6" rest="180" notes="Form odaklı çalış" />
        <EXERCISE name="Pull Up" sets="3" reps="8" rest="90" />
        <EXERCISE name="Barbell Row" sets="3" reps="10" rest="90" />
      </WORKOUT>
    </DAY>
    <DAY day="Cuma">
      <WORKOUT type="Legs">
        <EXERCISE name="Squat" sets="4" reps="8" rest="150" />
        <EXERCISE name="Leg Press" sets="3" reps="12" rest="90" />
        <EXERCISE name="Leg Curl" sets="3" reps="12" rest="60" />
      </WORKOUT>
    </DAY>
    <DAY day="Cumartesi">
      <WORKOUT type="Active Recovery">
        <EXERCISE name="Hafif Kardio" sets="1" reps="20" rest="0" notes="20 dakika yürüyüş veya bisiklet" />
        <EXERCISE name="Stretching" sets="1" reps="15" rest="0" notes="15 dakika germe egzersizleri" />
      </WORKOUT>
    </DAY>
  </PROGRAM>
</COACHING_SESSION>

ÖRNEKLER:
- Yeni başlayan: 3 gün full body, düşük hacim
- Orta seviye: 4 gün Upper/Lower split
- İleri seviye: 5-6 gün Push/Pull/Legs veya PPL x2
"""


def _parse_iso_date(value: str) -> Optional[datetime]:
    try:
        cleaned = value.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


def _build_daily_suggestions_context(backup_data: Dict[str, Any]) -> str:
    """Build comprehensive context for AI suggestions including all user data"""

    # Extract all data types
    meals = backup_data.get("mealEntries", [])
    health = backup_data.get("healthEntries", [])
    sleep = backup_data.get("sleepEntries", [])
    workouts = backup_data.get("workoutEntries", [])
    tasks = backup_data.get("tasks", [])
    notes = backup_data.get("notes", [])
    ai_memories = backup_data.get("aiMemories", [])
    ai_suggestions = backup_data.get("aiSuggestions", [])

    def meal_key(entry: Dict[str, Any]) -> datetime:
        raw = str(entry.get("date", ""))
        parsed = _parse_iso_date(raw) or datetime.min
        return parsed

    # Recent meals (last 20)
    meals_sorted = sorted(meals, key=meal_key)
    recent_meals = meals_sorted[-20:]
    compact_meals = [
        {
            "date": str(m.get("date", ""))[:10],
            "mealType": m.get("mealType"),
            "description": m.get("description"),
            "calories": m.get("calories", 0)
        }
        for m in recent_meals
    ]

    # Calculate average daily calories
    calories_by_day: Dict[str, float] = {}
    for meal in compact_meals:
        day = meal.get("date") or ""
        calories_by_day[day] = calories_by_day.get(day, 0) + float(meal.get("calories", 0) or 0)
    avg_daily_calories = round(
        sum(calories_by_day.values()) / max(len(calories_by_day), 1),
        0
    )

    # Recent health data (last 7 days)
    compact_health = [
        {
            "date": str(h.get("date", ""))[:10],
            "steps": h.get("steps", 0),
            "caloriesBurned": h.get("caloriesBurned", 0),
            "caloriesConsumed": h.get("caloriesConsumed", 0),
            "activeMinutes": h.get("activeMinutes", 0)
        }
        for h in health[-7:]
    ]

    # Recent sleep data (last 7 days)
    compact_sleep = [
        {
            "date": str(s.get("date", ""))[:10],
            "quality": s.get("quality", 0)
        }
        for s in sleep[-7:]
    ]

    # Recent workouts (last 7 days)
    compact_workouts = [
        {
            "date": str(w.get("date", ""))[:10],
            "type": w.get("workoutType"),
            "duration": w.get("duration", 0)
        }
        for w in workouts[-7:]
    ]

    # Pending/incomplete tasks
    pending_tasks = [
        {
            "title": t.get("title", ""),
            "completed": t.get("completed", False),
            "priority": t.get("priority", "medium"),
            "dueDate": str(t.get("dueDate", ""))[:10] if t.get("dueDate") else None,
            "tags": t.get("tags", [])
        }
        for t in tasks
        if not t.get("completed", False)
    ][:15]  # Limit to 15 pending tasks

    # Today's scheduled events (to find free time slots)
    today = datetime.now().date().isoformat()
    todays_events = [
        {
            "title": t.get("title", ""),
            "startDate": str(t.get("startDate", ""))[:16],  # YYYY-MM-DD HH:MM
            "endDate": str(t.get("endDate", ""))[:16],
            "startTime": str(t.get("startDate", ""))[11:16] if len(str(t.get("startDate", ""))) > 11 else None,
            "endTime": str(t.get("endDate", ""))[11:16] if len(str(t.get("endDate", ""))) > 11 else None,
            "tags": t.get("tags", [])
        }
        for t in tasks
        if str(t.get("startDate", ""))[:10] == today and not t.get("completed", False)
    ]

    # Today's meals (to avoid duplicate meal suggestions)
    todays_meals = [
        {
            "mealType": m.get("mealType"),
            "description": m.get("description"),
            "calories": m.get("calories", 0)
        }
        for m in meals
        if str(m.get("date", ""))[:10] == today
    ]

    # Recent notes (last 10)
    recent_notes = [
        {
            "title": n.get("title", ""),
            "content": (n.get("content", "") or "")[:200],  # First 200 chars
            "createdAt": str(n.get("createdAt", ""))[:10]
        }
        for n in notes[-10:]
    ]

    # AI Memories (all)
    memories = [
        {
            "category": m.get("category", "general"),
            "content": m.get("content", "")
        }
        for m in ai_memories
    ]

    # Recent accepted suggestions (last 5)
    accepted_suggestions = [
        {
            "type": s.get("type", ""),
            "description": (s.get("description", "") or "")[:100],
            "status": s.get("status", "")
        }
        for s in ai_suggestions
        if s.get("status") == "accepted"
    ][-5:]

    # Pending suggestions (to avoid duplicates)
    pending_suggestions = [
        {
            "type": s.get("type", ""),
            "description": (s.get("description", "") or "")[:100],
            "metadata": s.get("metadata", {})
        }
        for s in ai_suggestions
        if s.get("status") == "pending"
    ]

    # Habit tracking data
    habits = backup_data.get("habits", [])
    habit_logs = backup_data.get("habitLogs", [])

    # Existing habits
    existing_habits = [
        {
            "name": h.get("name", ""),
            "category": h.get("category", ""),
            "type": h.get("type", ""),
            "frequency": h.get("frequency", "")
        }
        for h in habits
    ]

    # Today's habit completions
    today = datetime.now().date().isoformat()
    todays_habit_logs = [
        {
            "habitName": next((h.get("name") for h in habits if h.get("id") == log.get("habitId")), "Unknown"),
            "completed": log.get("completed", False)
        }
        for log in habit_logs
        if str(log.get("date", ""))[:10] == today
    ]

    # Current date and time
    now = datetime.now()
    current_datetime = {
        "date": now.date().isoformat(),
        "time": now.strftime("%H:%M"),
        "hour": now.hour,
        "day_of_week": now.strftime("%A"),
        "day_of_week_tr": ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"][now.weekday()]
    }

    context = {
        "current_datetime": current_datetime,
        "recent_meals": compact_meals,
        "avg_daily_calories": avg_daily_calories,
        "recent_health": compact_health,
        "recent_sleep": compact_sleep,
        "recent_workouts": compact_workouts,
        "pending_tasks": pending_tasks,
        "todays_events": todays_events,
        "todays_meals": todays_meals,
        "recent_notes": recent_notes,
        "ai_memories": memories,
        "accepted_suggestions": accepted_suggestions,
        "pending_suggestions": pending_suggestions,
        "existing_habits": existing_habits,
        "todays_habit_logs": todays_habit_logs
    }

    return json.dumps(context, ensure_ascii=False)


# Health check
@app.get("/")
async def root():
    """API sağlık kontrolü"""
    return {
        "status": "healthy",
        "service": "Personal Assistant Backend API",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }


# TEFAS Endpoints
@app.get("/api/funds/price/{fund_code}", response_model=FundPrice)
async def get_fund_price(fund_code: str, date: Optional[str] = None):
    """
    Belirli bir fonun güncel fiyatını getir

    Args:
        fund_code: TEFAS fon kodu (örn: TQE)
        date: Tarih (YYYY-MM-DD formatında, opsiyonel)
    """
    try:
        result = tefas_crawler.get_fund_price(fund_code, date)
        if not result:
            fallback = tefas_crawler.search_funds(fund_code)
            if fallback:
                sample = fallback[0]
                return FundPrice(
                    fund_code=sample.get("fund_code", fund_code.upper()),
                    fund_name=sample.get("fund_name", ""),
                    price=sample.get("price", 0),
                    date=sample.get("date", ""),
                    change_percent=sample.get("change_percent")
                )
            raise HTTPException(status_code=404, detail=f"Fon bulunamadı: {fund_code}")

        return FundPrice(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/funds/history/{fund_code}")
async def get_fund_history(fund_code: str, days: int = 30):
    """
    Fonun geçmiş fiyat bilgilerini getir

    Args:
        fund_code: TEFAS fon kodu
        days: Kaç günlük geçmiş (varsayılan 30)
    """
    try:
        history = tefas_crawler.get_fund_history(fund_code, days)
        return {
            "fund_code": fund_code,
            "days": days,
            "history": history
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/funds/search")
async def search_funds(query: Optional[str] = ""):
    """
    Fon arama

    Args:
        query: Arama terimi (boş ise tüm fonları listeler)
    """
    try:
        funds = tefas_crawler.search_funds(query)
        return {
            "query": query,
            "count": len(funds),
            "funds": funds
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Stock Endpoints
@app.get("/api/stocks/price/{symbol}", response_model=StockPrice)
async def get_stock_price(symbol: str, date: Optional[str] = None):
    """
    Get stock price (current or historical)

    Args:
        symbol: Yahoo Finance symbol (e.g., "THYAO.IS", "AAPL")
        date: Optional date (YYYY-MM-DD)

    Returns:
        Stock price information including symbol, name, price, currency, date
    """
    try:
        result = stock_service.get_stock_price(symbol, date)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Stock not found: {symbol}"
            )

        return StockPrice(
            symbol=result['symbol'],
            stock_name=result['stock_name'],
            price=result['price'],
            currency=result['currency'],
            date=result['date'],
            change_percent=None
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stocks/history/{symbol}")
async def get_stock_history(symbol: str, days: int = 30):
    """
    Get stock price history

    Args:
        symbol: Stock symbol
        days: Number of days of history (default: 30)

    Returns:
        Historical price data
    """
    try:
        history = stock_service.get_stock_history(symbol, days)

        return {
            "symbol": symbol,
            "days": days,
            "count": len(history),
            "history": history
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stocks/search")
async def search_stocks(query: Optional[str] = ""):
    """
    Search for stocks

    Args:
        query: Search term (empty to list common stocks)

    Returns:
        List of stock suggestions
    """
    try:
        stocks = stock_service.search_stocks(query)
        return {
            "query": query,
            "count": len(stocks),
            "stocks": stocks
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/portfolio/calculate")
async def calculate_portfolio(
    fund_investments: List[FundInvestment] = [],
    stock_investments: List[StockInvestment] = []
):
    """
    Combined portfolio profit/loss calculation (funds + stocks)

    Args:
        fund_investments: User's fund investments
        stock_investments: User's stock investments

    Returns:
        Combined portfolio summary with funds and stocks
    """
    try:
        total_investment = 0
        total_current_value = 0
        funds_detail = []
        stocks_detail = []

        # Process fund investments
        for investment in fund_investments:
            result = tefas_crawler.calculate_profit_loss(
                fund_code=investment.fund_code,
                purchase_price=investment.purchase_price,
                purchase_amount=investment.investment_amount
            )

            if 'error' in result:
                continue

            total_investment += investment.investment_amount
            total_current_value += result['current_value']

            funds_detail.append(FundDetail(
                fund_code=result['fund_code'],
                fund_name=result['fund_name'],
                investment_amount=investment.investment_amount,
                current_value=result['current_value'],
                profit_loss=result['profit_loss'],
                profit_loss_percent=result['profit_loss_percent'],
                purchase_price=investment.purchase_price,
                current_price=result['current_price'],
                units=result['units']
            ))

        # Process stock investments
        for investment in stock_investments:
            result = stock_service.calculate_profit_loss(
                symbol=investment.symbol,
                purchase_price=investment.purchase_price,
                purchase_amount=investment.investment_amount
            )

            if 'error' in result:
                continue

            total_investment += investment.investment_amount
            total_current_value += result['current_value']

            stocks_detail.append(StockDetail(
                symbol=result['symbol'],
                stock_name=result['stock_name'],
                investment_amount=investment.investment_amount,
                current_value=result['current_value'],
                profit_loss=result['profit_loss'],
                profit_loss_percent=result['profit_loss_percent'],
                purchase_price=investment.purchase_price,
                current_price=result['current_price'],
                units=result['units'],
                currency=result['currency']
            ))

        # Calculate totals
        total_profit_loss = total_current_value - total_investment
        profit_loss_percent = (total_profit_loss / total_investment * 100) if total_investment > 0 else 0

        # Daily change (simplified)
        daily_change = 0

        summary = PortfolioSummary(
            total_investment=round(total_investment, 2),
            current_value=round(total_current_value, 2),
            total_profit_loss=round(total_profit_loss, 2),
            profit_loss_percent=round(profit_loss_percent, 2),
            daily_change=daily_change,
            funds=funds_detail,
            stocks=stocks_detail
        )

        await supabase_service.record_portfolio_snapshot(summary)
        return summary

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/portfolio/history", response_model=PortfolioHistoryResponse)
async def portfolio_history(
    range: PortfolioRange = PortfolioRange.month,
    fund_code: Optional[str] = None
):
    """
    Supabase üzerinde tutulan portföy geçmişini getirir.
    """
    try:
        return await supabase_service.get_portfolio_history(range, fund_code)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Gemini AI Endpoints
@app.post("/api/ai/chat", response_model=GeminiResponse)
async def ai_chat(request: GeminiRequest):
    """
    Gemini AI ile sohbet

    Args:
        request: Mesaj ve bağlam
    """
    try:
        service = get_gemini_service()

        response_text = service.financial_chat(
            message=request.message,
            portfolio_context=request.context
        )

        return GeminiResponse(
            response=response_text,
            timestamp=datetime.now()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ai/analyze-portfolio")
async def analyze_portfolio(
    investments: List[FundInvestment],
    question: Optional[str] = None
):
    """
    Portföy analizi yap (AI destekli)

    Args:
        investments: Fon yatırımları
        question: Kullanıcı sorusu (opsiyonel)
    """
    try:
        # Önce portföy hesapla
        portfolio_result = await calculate_portfolio(investments)

        # AI analizi yap
        service = get_gemini_service()
        analysis = service.analyze_portfolio(
            portfolio_data=portfolio_result.dict(),
            user_question=question
        )

        return {
            "portfolio": portfolio_result,
            "ai_analysis": analysis,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Enhanced AI Endpoints (AŞAMA 4)
@app.post("/api/ai/chat-v2", response_model=EnhancedGeminiResponse)
async def enhanced_ai_chat(request: EnhancedGeminiRequest):
    """
    Enhanced AI chat with data request capabilities

    This endpoint:
    - Accepts complete user data from frontend
    - AI can request specific data via JSON
    - Backend filters and provides only requested data
    - Supports multi-turn conversations with context
    - Tracks data requests made during conversation

    Args:
        request: Enhanced request with user message, complete user data, and conversation history

    Returns:
        Enhanced response with AI message, updated conversation history, and data request count
    """
    try:
        # Initialize enhanced Gemini service
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="GEMINI_API_KEY environment variable not set"
            )
        service = EnhancedGeminiService(api_key=api_key)

        # Process chat with data request loop
        response_text, updated_history, suggestions, memories = service.chat(
            user_message=request.message,
            user_data=request.user_data,
            conversation_history=request.conversation_history,
            user_id=request.user_id
        )

        # Count data requests in conversation
        data_requests_count = sum(
            1 for msg in updated_history
            if msg.get("data_request", False)
        )

        return EnhancedGeminiResponse(
            response=response_text,
            conversation_history=updated_history,
            data_requests_made=data_requests_count,
            suggestions=suggestions,
            memories=memories,
            timestamp=datetime.now()
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Enhanced AI chat failed: {str(e)}")


@app.post("/api/ai/quick-analysis", response_model=QuickAnalysisResponse)
async def quick_analysis(request: QuickAnalysisRequest):
    """
    Quick data analysis without full conversation

    Provides instant analysis of a specific data category:
    - tasks, notes, health, sleep, weight, meals, workouts
    - portfolio, goals, budget, salary, friends

    Args:
        request: Category, user data, time range, and API key

    Returns:
        Quick analysis result with summary, metrics, trends, and recommendations
    """
    try:
        # Initialize enhanced Gemini service
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="GEMINI_API_KEY environment variable not set"
            )
        service = EnhancedGeminiService(api_key=api_key)

        # Perform quick analysis
        analysis = service.quick_analysis(
            category=request.category,
            user_data=request.user_data,
            time_range=request.time_range,
            user_id=request.user_id
        )

        return QuickAnalysisResponse(
            analysis=analysis,
            category=request.category,
            time_range=request.time_range,
            timestamp=datetime.now()
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quick analysis failed: {str(e)}")


@app.post("/api/ai/daily-suggestions", response_model=DailySuggestionsResponse)
async def daily_suggestions(
    request: DailySuggestionsRequest,
    x_user_id: str = Header(...)
):
    """
    Generate daily meal suggestions (and optional general suggestion)
    for the next day and save them in Supabase.
    """
    try:
        result = await _generate_daily_suggestions_for_user(
            user_id=x_user_id,
            target_date=request.target_date,
            include_general=request.include_general,
            force=request.force
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Daily suggestions failed: {str(e)}")


@app.post("/api/ai/daily-suggestions-phased", response_model=DailySuggestionsResponse)
async def daily_suggestions_phased(
    request: DailySuggestionsRequest,
    x_user_id: str = Header(...)
):
    """
    Generate daily suggestions in phases: meal → task → event
    Each phase uses a focused prompt for better AI quality.
    """
    try:
        result = await _generate_daily_suggestions_phased(
            user_id=x_user_id,
            target_date=request.target_date,
            force=request.force
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Phased suggestions failed: {str(e)}")


# Yardımcı endpoint'ler
@app.get("/api/health")
async def health_check():
    """Detaylı sağlık kontrolü"""
    return {
        "status": "healthy",
        "services": {
            "tefas_crawler": "operational",
            "api": "operational"
        },
        "timestamp": datetime.now().isoformat()
    }


# Backup & Restore Endpoints
@app.post("/api/backup")
async def backup_data(
    request: Request,
    x_user_id: str = Header(...)
):
    """
    iOS uygulamasından gelen tüm veriyi Supabase'e kaydeder

    Args:
        request: JSON body ile gelen backup verisi
        x_user_id: Header'dan gelen user ID
    """
    try:
        data = await request.json()

        # Supabase'e kaydet
        await supabase_service.save_backup_data(user_id=x_user_id, data=data)

        return {
            "status": "success",
            "message": "Backup completed successfully",
            "timestamp": datetime.now().isoformat(),
            "user_id": x_user_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}")


@app.get("/api/restore")
async def restore_data(x_user_id: str = Header(...)):
    """
    Supabase'den kullanıcının tüm verisini çeker ve iOS'a döner

    Args:
        x_user_id: Header'dan gelen user ID
    """
    try:
        # Supabase'den veriyi çek
        data = await supabase_service.get_backup_data(user_id=x_user_id)

        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")


# -------------------------------------------------------------------------
# Email Endpoints
# -------------------------------------------------------------------------


@app.post("/api/email/daily-summary", response_model=EmailResponse)
async def send_daily_summary(request: DailySummaryRequest):
    """
    Send daily task summary emails to assigned friends

    Args:
        request: Daily summary request with user name, tasks, and recipients

    Returns:
        EmailResponse with success status and details
    """
    if not request.recipients:
        return EmailResponse(
            success=True,
            sent_count=0,
            failed_count=0,
            details=[]
        )

    sent_count = 0
    failed_count = 0
    details = []

    for recipient in request.recipients:
        # Filter tasks assigned to this friend (if needed)
        # For now, send all tasks to all recipients
        success = email_service.send_daily_summary(
            recipient_email=recipient.email,
            recipient_name=recipient.name,
            user_name=request.user_name,
            tasks=request.tasks,
            date=request.date
        )

        if success:
            sent_count += 1
            details.append({
                "recipient": recipient.email,
                "status": "sent",
                "message": "Email sent successfully"
            })
        else:
            failed_count += 1
            details.append({
                "recipient": recipient.email,
                "status": "failed",
                "message": "Failed to send email"
            })

    return EmailResponse(
        success=(failed_count == 0),
        sent_count=sent_count,
        failed_count=failed_count,
        details=details
    )


# ============================================================================
# CRON JOB ENDPOINTS
# ============================================================================

@app.post("/api/cron/hourly-check")
async def cron_hourly_check():
    """
    CronJob endpoint - Called every hour by Render CronJob
    - Health check ping runs every time (unchanged)
    - AI suggestion generation has 1-hour cooldown per user
    - Only generates suggestions if 1+ hour has passed since last suggestion
    - Generates AI suggestions for all users (meals, tasks, events, notes)
    - Learns from user data and stores memories
    """
    try:
        # Get all unique user IDs from database
        all_user_ids = supabase_service.get_all_user_ids()

        processed_count = 0
        skipped_count = 0
        errors = []
        # Generate suggestions for today (not tomorrow)
        target_date = datetime.now().date().isoformat()
        now = datetime.now(timezone.utc)

        for user_id in all_user_ids:
            try:
                # Check if user had AI suggestion in the last hour
                last_suggestion_time = supabase_service.get_last_ai_suggestion_time(user_id)

                if last_suggestion_time:
                    time_since_last = now - last_suggestion_time
                    # Skip if less than 1 hour has passed
                    if time_since_last.total_seconds() < 3600:  # 3600 seconds = 1 hour
                        skipped_count += 1
                        continue

                # Generate AI suggestions with force=True to allow multiple runs per day
                await generate_ai_suggestions_for_user(
                    user_id=user_id,
                    target_date=target_date,
                    include_general=True,  # Include all types: meals, tasks, events, notes
                    force=True  # Allow multiple suggestions per day
                )

                processed_count += 1

            except Exception as e:
                errors.append({
                    "user_id": user_id,
                    "error": str(e)
                })

        return {
            "success": True,
            "processed_users": processed_count,
            "skipped_users": skipped_count,
            "total_users": len(all_user_ids),
            "target_date": target_date,
            "errors": errors
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Keep old endpoint for backward compatibility
@app.post("/api/cron/daily-check")
async def cron_daily_check():
    """Legacy endpoint - redirects to hourly-check"""
    return await cron_hourly_check()


@app.post("/api/cron/weekly-fitness-coach")
async def cron_weekly_fitness_coach():
    """
    CronJob endpoint - Called every Monday at 06:00
    Generates weekly fitness coaching reports for all users with workouts
    """
    print("🏋️ Starting weekly fitness coach cron job...")

    try:
        # Get all users who have workout data
        users_with_workouts = supabase_service.get_users_with_workouts()
        print(f"Found {len(users_with_workouts)} users with workout data")

        coaching_sessions_created = 0

        for user_id in users_with_workouts:
            try:
                await generate_fitness_coaching_for_user(user_id)
                coaching_sessions_created += 1
            except Exception as e:
                print(f"Error generating fitness coaching for user {user_id}: {str(e)}")
                continue

        return {
            "status": "success",
            "users_processed": len(users_with_workouts),
            "coaching_sessions_created": coaching_sessions_created
        }

    except Exception as e:
        print(f"Error in weekly fitness coach cron: {str(e)}")
        return {"status": "error", "message": str(e)}


async def generate_fitness_coaching_for_user(user_id: str):
    """Generate weekly fitness coaching for a single user"""
    from datetime import datetime, timedelta
    import json

    # Get last 7 days of workouts
    today = datetime.now()
    week_start = (today - timedelta(days=7)).date()
    week_end = today.date()

    workouts = supabase_service.get_workouts_for_period(user_id, week_start, week_end)

    if len(workouts) == 0:
        print(f"No workouts found for user {user_id}, skipping coaching")
        return

    # Calculate weekly metrics
    metrics = calculate_weekly_fitness_metrics(workouts, week_start, week_end)

    # Get user's fitness memories and previous program
    fitness_memories = supabase_service.get_ai_memories(
        user_id,
        category="fitness",
        limit=10
    )
    previous_coaching = supabase_service.get_latest_fitness_coaching(user_id)

    # Build context for AI
    context = {
        "workouts_completed": metrics["workouts_completed"],
        "total_volume": f"{metrics['total_volume']:.0f} kg",
        "total_sets": metrics["total_sets"],
        "total_reps": metrics["total_reps"],
        "muscle_groups_trained": json.dumps(metrics["muscle_groups"], ensure_ascii=False),
        "rest_days": metrics["rest_days"],
        "avg_workout_duration": f"{metrics['avg_duration']:.0f} dk",
        "avg_rpe": f"{metrics['avg_rpe']:.1f}",
        "user_fitness_memories": "\n".join([f"- {m.get('content', '')}" for m in fitness_memories]),
        "previous_week_program": previous_coaching.get("next_week_program", {}) if previous_coaching else {}
    }

    # Generate AI coaching
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY not set, skipping AI coaching generation")
        return

    service = EnhancedGeminiService(api_key=api_key)
    coaching_prompt = FITNESS_COACH_PROMPT.format(**context)
    response = service.generate_response(
        message="Haftalık fitness koçluğu yap",
        context=context,
        system_prompt=coaching_prompt
    )

    # Parse coaching response
    coaching_data = parse_fitness_coaching_response(response)

    # Save to database
    coaching_session = {
        "user_id": user_id,
        "week_start_date": str(week_start),
        "week_end_date": str(week_end),
        **metrics,
        **coaching_data
    }

    supabase_service.save_fitness_coaching_session(coaching_session)
    print(f"✅ Created fitness coaching session for user {user_id}")


def calculate_weekly_fitness_metrics(workouts: list, week_start, week_end) -> dict:
    """Calculate weekly workout metrics"""
    from datetime import datetime

    total_volume = 0
    total_sets = 0
    total_reps = 0
    total_duration = 0
    rpe_sum = 0
    rpe_count = 0
    muscle_groups = {}
    workout_days = set()

    for workout in workouts:
        # Track workout day
        workout_date = datetime.fromisoformat(workout["date"].replace("Z", "+00:00")).date()
        workout_days.add(workout_date)

        # Duration
        total_duration += workout.get("duration", 0)

        # Process exercises
        for exercise in workout.get("exercises", []):
            # Muscle group frequency
            muscle_group = exercise.get("muscleGroup", "")
            if muscle_group:
                muscle_groups[muscle_group] = muscle_groups.get(muscle_group, 0) + 1

            # Calculate from setDetails if available
            set_details = exercise.get("setDetails", [])
            if set_details:
                for set_detail in set_details:
                    reps = set_detail.get("reps", 0)
                    weight = set_detail.get("weight", 0)
                    total_volume += reps * weight
                    total_reps += reps
                    total_sets += 1

                    rpe = set_detail.get("rpe", 0)
                    if rpe > 0:
                        rpe_sum += rpe
                        rpe_count += 1
            else:
                # Fallback to basic fields
                sets = exercise.get("sets", 0)
                reps = exercise.get("reps", 0)
                weight = exercise.get("weight", 0)
                total_volume += sets * reps * weight
                total_reps += sets * reps
                total_sets += sets

                rpe = exercise.get("rpe", 0)
                if rpe > 0:
                    rpe_sum += rpe
                    rpe_count += 1

    # Calculate rest days
    days_in_period = (week_end - week_start).days + 1
    rest_days = days_in_period - len(workout_days)

    return {
        "workouts_completed": len(workouts),
        "total_volume": total_volume,
        "total_sets": total_sets,
        "total_reps": total_reps,
        "muscle_groups": muscle_groups,
        "rest_days": rest_days,
        "avg_duration": total_duration / len(workouts) if workouts else 0,
        "avg_rpe": rpe_sum / rpe_count if rpe_count > 0 else 0
    }


def parse_fitness_coaching_response(response_text: str) -> dict:
    """Parse AI coaching response into structured data"""
    import re

    result = {
        "weekly_summary": "",
        "strengths": [],
        "areas_for_improvement": [],
        "motivation_message": "",
        "next_week_program": {"days": []}
    }

    # Extract summary
    summary_match = re.search(r'<SUMMARY>(.*?)</SUMMARY>', response_text, re.DOTALL)
    if summary_match:
        result["weekly_summary"] = summary_match.group(1).strip()

    # Extract strengths
    strengths_match = re.search(r'<STRENGTHS>(.*?)</STRENGTHS>', response_text, re.DOTALL)
    if strengths_match:
        strengths_text = strengths_match.group(1).strip()
        result["strengths"] = [s.strip().lstrip('- ') for s in strengths_text.split('\n') if s.strip() and s.strip().startswith('-')]

    # Extract improvements
    improvements_match = re.search(r'<IMPROVEMENTS>(.*?)</IMPROVEMENTS>', response_text, re.DOTALL)
    if improvements_match:
        improvements_text = improvements_match.group(1).strip()
        result["areas_for_improvement"] = [i.strip().lstrip('- ') for i in improvements_text.split('\n') if i.strip() and i.strip().startswith('-')]

    # Extract motivation
    motivation_match = re.search(r'<MOTIVATION>(.*?)</MOTIVATION>', response_text, re.DOTALL)
    if motivation_match:
        result["motivation_message"] = motivation_match.group(1).strip()

    # Extract program
    program_match = re.search(r'<PROGRAM>(.*?)</PROGRAM>', response_text, re.DOTALL)
    if program_match:
        program_text = program_match.group(1)

        # Parse each day
        day_pattern = r'<DAY day="(.*?)">(.*?)</DAY>'
        for day_match in re.finditer(day_pattern, program_text, re.DOTALL):
            day_name = day_match.group(1)
            day_content = day_match.group(2)

            # Parse workout type
            workout_match = re.search(r'<WORKOUT type="(.*?)">(.*?)</WORKOUT>', day_content, re.DOTALL)
            if workout_match:
                workout_type = workout_match.group(1)
                exercises_content = workout_match.group(2)

                # Parse exercises
                exercises = []
                exercise_pattern = r'<EXERCISE name="(.*?)" sets="(.*?)" reps="(.*?)" rest="(.*?)"(?:\s+notes="(.*?)")?\s*/>'
                for ex_match in re.finditer(exercise_pattern, exercises_content):
                    exercises.append({
                        "name": ex_match.group(1),
                        "sets": int(ex_match.group(2)),
                        "reps": int(ex_match.group(3)),
                        "rest_seconds": int(ex_match.group(4)),
                        "notes": ex_match.group(5) or ""
                    })

                result["next_week_program"]["days"].append({
                    "day": day_name,
                    "workoutType": workout_type,
                    "exercises": exercises
                })

    return result


async def generate_ai_suggestions_for_user(
    user_id: str,
    target_date: Optional[str] = None,
    include_general: bool = True,
    force: bool = False
):
    """Generate daily suggestions for a single user"""
    try:
        await _generate_daily_suggestions_for_user(
            user_id=user_id,
            target_date=target_date,
            include_general=include_general,
            force=force
        )
    except Exception as e:
        print(f"Error generating AI suggestions for user {user_id}: {str(e)}")
        raise


async def check_and_send_friend_emails(user_id: str):
    """Check and send daily summary emails to friends"""
    try:
        # Check if email was already sent today
        if supabase_service.was_friend_email_sent_today(user_id):
            return  # Already sent today

        # Get user settings and data
        settings = supabase_service.get_user_email_settings(user_id)
        if not settings or not settings.get("friends"):
            return  # No friends configured

        # Get tasks for today
        tasks = supabase_service.get_user_tasks_for_today(user_id)

        # Send emails
        await email_service.send_daily_summary(
            user_name=settings.get("user_name", "User"),
            tasks=tasks,
            recipients=settings["friends"]
        )

        # Mark as sent
        supabase_service.mark_friend_email_sent(user_id)

    except Exception as e:
        print(f"Error sending friend emails for user {user_id}: {str(e)}")


async def check_and_send_personal_email(user_id: str):
    """Check and send personal summary email to user"""
    try:
        # Check if email was already sent today
        if supabase_service.was_personal_email_sent_today(user_id):
            return  # Already sent today

        # Get user settings
        settings = supabase_service.get_user_email_settings(user_id)
        if not settings or not settings.get("personal_email"):
            return  # No personal email configured

        # Get user data
        tasks = supabase_service.get_user_tasks_and_events_for_today(user_id)
        meals = supabase_service.get_user_meals_for_today(user_id)

        # Send personal summary email
        await email_service.send_personal_summary(
            user_email=settings["personal_email"],
            user_name=settings.get("user_name", "User"),
            tasks=tasks,
            meals=meals
        )

        # Mark as sent
        supabase_service.mark_personal_email_sent(user_id)

    except Exception as e:
        print(f"Error sending personal email for user {user_id}: {str(e)}")


async def _generate_daily_suggestions_for_user(
    user_id: str,
    target_date: Optional[str] = None,
    include_general: bool = True,
    force: bool = False
) -> DailySuggestionsResponse:
    resolved_date = target_date
    if resolved_date:
        parsed_date = _parse_iso_date(resolved_date)
        if parsed_date:
            resolved_date = parsed_date.date().isoformat()
        else:
            resolved_date = resolved_date[:10]
    else:
        resolved_date = (datetime.now() + timedelta(days=1)).date().isoformat()

    if not force:
        already_exists = supabase_service.has_ai_suggestions_for_date(
            user_id=user_id,
            target_date=resolved_date
        )
        if already_exists:
            return DailySuggestionsResponse(
                success=True,
                saved_count=0,
                skipped=True,
                message="Suggestions already exist for target date."
            )

    backup_data = await supabase_service.get_backup_data(user_id=user_id)
    context = _build_daily_suggestions_context(backup_data)

    message = (
        f"Hedef tarih: {resolved_date}.\n"
        f"include_general: {'true' if include_general else 'false'}.\n"
        "Lütfen bu kurala uy ve sadece SUGGESTION tag'larıyla yanıt ver."
    )

    service = get_gemini_service()
    response_text = service.generate_response(
        message=message,
        context=context,
        system_prompt=DAILY_SUGGESTIONS_SYSTEM_PROMPT
    )

    parsed = parse_suggestions_and_memories(response_text or "")
    suggestions = parsed.get("suggestions", [])
    memories = parsed.get("memories", [])

    # Parse EDIT suggestions (NEW)
    from app.ai_capabilities import parse_edit_suggestions
    edits = parse_edit_suggestions(response_text or "")

    # Convert edits to suggestions for storage
    for edit in edits:
        suggestions.append({
            'type': 'edit',
            'description': f"Düzenleme önerisi: {edit['field']} → {edit['newValue']}",
            'metadata': {
                'targetType': edit['targetType'],
                'targetId': edit['targetId'],
                'field': edit['field'],
                'newValue': edit['newValue'],
                'reason': edit['reason']
            }
        })

    # Save AI memories first (if any)
    memory_count = 0
    if memories:
        try:
            memory_count = supabase_service.save_ai_memories(
                user_id=user_id,
                memories=memories
            )
            print(f"✅ Saved {memory_count} AI memories for user {user_id}")
        except Exception as e:
            print(f"⚠️ Error saving AI memories: {str(e)}")

    if not include_general:
        suggestions = [
            suggestion for suggestion in suggestions
            if (suggestion.get("type") or "").lower() == "meal"
        ]

    if not suggestions:
        return DailySuggestionsResponse(
            success=False,
            saved_count=0,
            skipped=False,
            message=f"No suggestions generated. Saved {memory_count} memories."
        )

    saved_count = supabase_service.save_ai_suggestions(
        user_id=user_id,
        suggestions=suggestions,
        target_date=resolved_date,
        source="daily_suggestions"
    )

    return DailySuggestionsResponse(
        success=True,
        saved_count=saved_count,
        skipped=False,
        message=f"Saved {saved_count} suggestions and {memory_count} memories."
    )


async def _generate_daily_suggestions_phased(
    user_id: str,
    target_date: Optional[str] = None,
    force: bool = False
) -> DailySuggestionsResponse:
    """Generate suggestions in phases: meal → task → event"""
    resolved_date = target_date
    if resolved_date:
        parsed_date = _parse_iso_date(resolved_date)
        if parsed_date:
            resolved_date = parsed_date.date().isoformat()
        else:
            resolved_date = resolved_date[:10]
    else:
        resolved_date = (datetime.now() + timedelta(days=1)).date().isoformat()

    if not force:
        already_exists = supabase_service.has_ai_suggestions_for_date(
            user_id=user_id,
            target_date=resolved_date
        )
        if already_exists:
            return DailySuggestionsResponse(
                success=True,
                saved_count=0,
                skipped=True,
                message="Suggestions already exist for target date."
            )

    backup_data = await supabase_service.get_backup_data(user_id=user_id)
    context = _build_daily_suggestions_context(backup_data)

    service = get_gemini_service()
    all_suggestions = []
    all_memories = []

    from app.ai_capabilities import parse_edit_suggestions

    # Phase 1: Meal suggestions
    try:
        meal_response = service.generate_response(
            message=f"Hedef tarih: {resolved_date}. Yemek önerileri üret.",
            context=context,
            system_prompt=MEAL_SUGGESTIONS_PROMPT.format(
                todays_meals=context.get("todays_meals", []),
                todays_events=context.get("todays_events", []),
                recent_meals=context.get("recent_meals", []),
                current_datetime=context.get("current_datetime", {}),
                ai_memories=context.get("ai_memories", [])
            )
        )
        parsed = parse_suggestions_and_memories(meal_response or "")
        all_suggestions.extend(parsed.get("suggestions", []))
        all_memories.extend(parsed.get("memories", []))

        edits = parse_edit_suggestions(meal_response or "")
        for edit in edits:
            all_suggestions.append({
                'type': 'edit',
                'description': f"Düzenleme: {edit['field']} → {edit['newValue']}",
                'metadata': edit
            })
    except Exception as e:
        print(f"⚠️ Meal phase error: {str(e)}")

    # Phase 2: Task suggestions
    try:
        task_response = service.generate_response(
            message=f"Hedef tarih: {resolved_date}. Görev önerileri üret.",
            context=context,
            system_prompt=TASK_SUGGESTIONS_PROMPT.format(
                pending_tasks=context.get("pending_tasks", []),
                current_datetime=context.get("current_datetime", {}),
                ai_memories=context.get("ai_memories", [])
            )
        )
        parsed = parse_suggestions_and_memories(task_response or "")
        all_suggestions.extend(parsed.get("suggestions", []))
        all_memories.extend(parsed.get("memories", []))

        edits = parse_edit_suggestions(task_response or "")
        for edit in edits:
            all_suggestions.append({
                'type': 'edit',
                'description': f"Düzenleme: {edit['field']} → {edit['newValue']}",
                'metadata': edit
            })
    except Exception as e:
        print(f"⚠️ Task phase error: {str(e)}")

    # Phase 3: Event suggestions
    try:
        event_response = service.generate_response(
            message=f"Hedef tarih: {resolved_date}. Etkinlik önerileri üret.",
            context=context,
            system_prompt=EVENT_SUGGESTIONS_PROMPT.format(
                todays_events=context.get("todays_events", []),
                current_datetime=context.get("current_datetime", {}),
                ai_memories=context.get("ai_memories", [])
            )
        )
        parsed = parse_suggestions_and_memories(event_response or "")
        all_suggestions.extend(parsed.get("suggestions", []))
        all_memories.extend(parsed.get("memories", []))

        edits = parse_edit_suggestions(event_response or "")
        for edit in edits:
            all_suggestions.append({
                'type': 'edit',
                'description': f"Düzenleme: {edit['field']} → {edit['newValue']}",
                'metadata': edit
            })
    except Exception as e:
        print(f"⚠️ Event phase error: {str(e)}")

    # Save AI memories
    memory_count = 0
    if all_memories:
        try:
            memory_count = supabase_service.save_ai_memories(
                user_id=user_id,
                memories=all_memories
            )
            print(f"✅ Saved {memory_count} AI memories (phased)")
        except Exception as e:
            print(f"⚠️ Error saving AI memories: {str(e)}")

    if not all_suggestions:
        return DailySuggestionsResponse(
            success=False,
            saved_count=0,
            skipped=False,
            message=f"No suggestions generated. Saved {memory_count} memories."
        )

    saved_count = supabase_service.save_ai_suggestions(
        user_id=user_id,
        suggestions=all_suggestions,
        target_date=resolved_date,
        source="daily_suggestions_phased"
    )

    return DailySuggestionsResponse(
        success=True,
        saved_count=saved_count,
        skipped=False,
        message=f"Phased: Saved {saved_count} suggestions ({len([s for s in all_suggestions if s.get('type') == 'meal'])} meals, {len([s for s in all_suggestions if s.get('type') == 'task'])} tasks, {len([s for s in all_suggestions if s.get('type') == 'event'])} events, {len([s for s in all_suggestions if s.get('type') == 'edit'])} edits) and {memory_count} memories."
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

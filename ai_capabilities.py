"""
AI Capabilities and Data Request System
Handles AI capability listing and data request processing
"""

import re
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone
from enum import Enum


class DataCategory(str, Enum):
    """Available data categories that AI can request"""
    TASKS = "tasks"
    NOTES = "notes"
    HEALTH = "health"
    SLEEP = "sleep"
    WEIGHT = "weight"
    MEALS = "meals"
    WORKOUTS = "workouts"
    PORTFOLIO = "portfolio"
    GOALS = "goals"
    BUDGET = "budget"
    SALARY = "salary"
    FRIENDS = "friends"


class TimeRange(str, Enum):
    """Time range options for data requests"""
    TODAY = "today"
    YESTERDAY = "yesterday"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"
    ALL = "all"
    CUSTOM = "custom"


# AI Capabilities Definition
AI_CAPABILITIES = {
    "data_access": {
        "tasks": {
            "description": "Görevler ve planlayıcı etkinlikleri",
            "operations": ["read", "create", "update", "delete", "analyze"],
            "filters": ["date_range", "status", "project", "tag"]
        },
        "notes": {
            "description": "Kullanıcı notları",
            "operations": ["read", "create", "update", "delete", "search"],
            "filters": ["date_range", "tags", "project"]
        },
        "health": {
            "description": "Sağlık verileri (adım, kalori, aktif dakika)",
            "operations": ["read", "analyze", "trend"],
            "filters": ["date_range"]
        },
        "sleep": {
            "description": "Uyku takibi",
            "operations": ["read", "analyze", "trend"],
            "filters": ["date_range", "quality"]
        },
        "weight": {
            "description": "Kilo ve vücut kompozisyonu takibi",
            "operations": ["read", "analyze", "trend"],
            "filters": ["date_range"]
        },
        "meals": {
            "description": "Yemek ve beslenme takibi",
            "operations": ["read", "create", "update", "delete", "analyze"],
            "filters": ["date_range", "meal_type"]
        },
        "workouts": {
            "description": "Egzersiz ve antrenman kayıtları",
            "operations": ["read", "analyze"],
            "filters": ["date_range", "workout_type"]
        },
        "portfolio": {
            "description": "Fon yatırımları ve portföy",
            "operations": ["read", "analyze", "calculate"],
            "filters": ["fund_code", "date_range"]
        },
        "goals": {
            "description": "Finansal hedefler",
            "operations": ["read", "analyze", "track_progress"],
            "filters": ["category", "status"]
        },
        "budget": {
            "description": "Bütçe ve harcama takibi",
            "operations": ["read", "analyze"],
            "filters": ["date_range", "month"]
        },
        "salary": {
            "description": "Maaş ve gelir bilgileri",
            "operations": ["read", "calculate"],
            "filters": ["year", "month"]
        },
        "friends": {
            "description": "Arkadaş listesi",
            "operations": ["read"],
            "filters": []
        },
        "ai_suggestions": {
            "description": "AI önerileri (kendi önerilerini yönetebilir)",
            "operations": ["read", "update", "delete"],
            "filters": ["status", "type", "date_range"]
        }
    },
    "actions": {
        "create_task": "Yeni görev oluştur",
        "update_task": "Mevcut görevi güncelle/taşı",
        "delete_task": "Görevi sil",
        "create_note": "Not ekle",
        "update_note": "Notu güncelle",
        "delete_note": "Notu sil",
        "add_meal": "Yemek kaydı ekle",
        "update_meal": "Yemek kaydını güncelle",
        "delete_meal": "Yemek kaydını sil",
        "update_suggestion": "Kendi önerisini güncelle",
        "delete_suggestion": "Kendi önerisini sil",
        "suggest_investment": "Yatırım önerisi sun",
        "analyze_trend": "Trend analizi yap",
        "calculate_progress": "İlerleme hesapla"
    },
    "analysis": {
        "portfolio_performance": "Portföy performans analizi",
        "health_trends": "Sağlık trendleri",
        "budget_analysis": "Bütçe analizi",
        "goal_tracking": "Hedef takibi",
        "habit_patterns": "Alışkanlık desenleri"
    }
}


def get_capabilities_prompt() -> str:
    """
    Generate the capabilities section for AI system prompt

    Returns:
        Formatted capabilities text for AI prompt
    """
    prompt = """
# SİSTEM YETENEKLERİ

Sen Personal Assistant uygulamasının AI asistanısın. Aşağıdaki yeteneklere sahipsin:

## VERİ ERİŞİMİ

Kullanıcının verilerine erişmek için JSON formatında veri talebi yapabilirsin.
Kullanılabilir veri kategorileri:

"""

    for category, details in AI_CAPABILITIES["data_access"].items():
        prompt += f"\n**{category.upper()}** - {details['description']}\n"
        prompt += f"  • İşlemler: {', '.join(details['operations'])}\n"
        if details['filters']:
            prompt += f"  • Filtreler: {', '.join(details['filters'])}\n"

    prompt += """

## VERİ TALEBİ FORMATI

Kullanıcının sorusunu yanıtlamak için veriye ihtiyaç duyduğunda, aşağıdaki JSON formatında istek yap:

```json
{
    "data_request": {
        "category": "tasks|notes|health|sleep|weight|meals|workouts|portfolio|goals|budget|salary|friends",
        "time_range": "today|yesterday|week|month|year|all",
        "filters": {
            "field": "value"
        },
        "custom_range": {
            "start_date": "YYYY-MM-DD",
            "end_date": "YYYY-MM-DD"
        }
    }
}
```

## ÖRNEK VERİ TALEPLERİ

1. Bu haftanın görevlerini görmek için:
```json
{
    "data_request": {
        "category": "tasks",
        "time_range": "week",
        "filters": {}
    }
}
```

2. Son aydaki uyku verilerini analiz etmek için:
```json
{
    "data_request": {
        "category": "sleep",
        "time_range": "month",
        "filters": {}
    }
}
```

3. Belirli bir fondaki yatırım bilgilerini görmek için:
```json
{
    "data_request": {
        "category": "portfolio",
        "time_range": "all",
        "filters": {
            "fund_code": "TQE"
        }
    }
}
```

## ÖNEMLİ KURALLAR

1. **Önce Veri Talep Et**: Kullanıcı bir soru sorduğunda, yanıt vermeden ÖNCE gerekli veriyi talep et
2. **Spesifik Ol**: Sadece ihtiyaç duyduğun veriyi talep et
3. **Zaman Aralığı Belirt**: Uygun zaman aralığını seç (today, week, month, vb.)
4. **Filtrele**: Gerekirse filters ile veriyi daralt
5. **Analiz Sonrası Yanıt**: Veriyi aldıktan SONRA analiz et ve kullanıcıya yanıt ver

## VERİ YAPISI DETAYLARI

### Görevler ve Etkinlikler (PlannerEvent)

Uygulamada iki tip planlama öğesi vardır:

**1. GÖREVLER (Tasks)** - isTask: true
- Belirli bir tarihe bağlı ama **saate bağlı olmayan** işler
- taskDate: Görevin tamamlanması gereken tarih
- taskStatus: "To Do", "In Progress", "Done"
- Örnek: "Rapor hazırla", "Market alışverişi yap", "Doktor randevusu al"

**2. ETKİNLİKLER (Events)** - isTask: false
- Belirli **tarih ve saate** bağlı etkinlikler
- startDate: Etkinliğin başlangıç tarihi ve saati
- endDate: Etkinliğin bitiş tarihi ve saati
- Örnek: "14:00 - 15:30 Toplantı", "18:00 Spor salonu", "09:00 - 17:00 İş"

**Ortak Alanlar:**
- title: Başlık
- tag: Kategori etiketi (örn: "İş", "Kişisel", "Sağlık")
- project: Proje adı
- notes: Notlar
- parentID: Üst görev ID'si (alt görevler için)
- recurrenceRule: Tekrarlama kuralı (opsiyonel)

**ÖRNEKLER:**

Görev oluşturma:
```json
{
  "isTask": true,
  "title": "Projeyi bitir",
  "taskDate": "2025-01-15",
  "taskStatus": "To Do",
  "tag": "İş",
  "project": "Website Redesign"
}
```

Saatli etkinlik oluşturma:
```json
{
  "isTask": false,
  "title": "Takım toplantısı",
  "startDate": "2025-01-15T14:00:00",
  "endDate": "2025-01-15T15:30:00",
  "tag": "İş",
  "project": "Website Redesign"
}
```

**ÖNEMLİ:** Kullanıcı belirli bir saat belirtiyorsa (örn: "yarın 14:00'te toplantı"), mutlaka **isTask: false** ile ETKİNLİK oluştur. Sadece tarih varsa (örn: "yarın rapor hazırla") **isTask: true** ile GÖREV oluştur.

## KULLANICI İLE ETKİLEŞİM

- Türkçe konuş
- Dostça ve profesyonel ol
- Açık ve anlaşılır açıklamalar yap
- Veri görselleştirmesi öner (grafik, tablo, vb.)
- Önerilerde bulunurken mantıklı gerekçeler sun
- Kullanıcı gizliliğine saygı göster

## ÖNERİLER VE HAFIZA

Kullanıcıya faydalı önerilerde bulunabilir ve önemli bilgileri hafızana kaydedebilirsin.

### Öneri Formatı
Uygulamada doğrudan işlem yapılabilecek öneriler oluşturmak için:

<SUGGESTION type="task|goal|health|finance|meal">
Öneri metni buraya
[metadata:key=value,key2=value2]
</SUGGESTION>

Örnekler:

Görev önerisi (saatsiz):
<SUGGESTION type="task">
Yarın market alışverişi yap
[metadata:date=2025-01-16,project=Kişisel,isTask=true]
</SUGGESTION>

Etkinlik önerisi (saatli):
<SUGGESTION type="task">
Yarın saat 18:00'de spor salonuna git
[metadata:startTime=18:00,duration=60,project=Sağlık,isTask=false]
</SUGGESTION>

Yemek önerisi:
<SUGGESTION type="meal">
Kahvaltı: Yulaf ezmesi, muz ve bal
[metadata:mealType=Kahvaltı,date=2025-01-16,calories=350]
</SUGGESTION>

### Hafıza Formatı
Kullanıcı hakkında öğrendiğin önemli bilgileri kaydetmek için:

<MEMORY category="habits|preferences|goals|health|finance|personal">
Hafıza kaydı metni
</MEMORY>

Örnek:
<MEMORY category="habits">
Kullanıcı her pazartesi akşamı spor salonuna gidiyor
</MEMORY>

## MEVCUT VERİLERİ DÜZENLEME VE SİLME

Kullanıcının mevcut verilerini düzenleyebilir veya silebilirsin. EDIT tag'i ile mevcut kayıtları değiştirebilirsin:

### Düzenleme Formatı
<EDIT targetType="task|meal|note" targetId="uuid">
Field: alanAdi
NewValue: yeniDeger
Reason: Neden değişiklik yapıldığı
</EDIT>

Örnekler:

Görevi başka güne taşıma:
<EDIT targetType="task" targetId="abc123-def456">
Field: taskDate
NewValue: 2025-01-20
Reason: Kullanıcı meşgul, görevi haftaya taşıyorum
</EDIT>

Yemek kaydını güncelleme:
<EDIT targetType="meal" targetId="meal-uuid-123">
Field: calories
NewValue: 450
Reason: Kalori hesabı düzeltildi
</EDIT>

### Silme Formatı
<DELETE targetType="task|meal|note|suggestion" targetId="uuid">
Reason: Silme gerekçesi
</DELETE>

Örnek - Kendi önerisini silme:
<DELETE targetType="suggestion" targetId="suggestion-uuid-123">
Reason: Kullanıcı bu öneriyi istemedi
</DELETE>

## KENDİ ÖNERİLERİNİ YÖNETME

Daha önce yaptığın AI önerilerini (suggestions) güncelleyebilir veya silebilirsin:
- Kullanıcı bir öneriyi beğenmediyse silebilirsin
- Öneriyi değiştirmek istersen güncelleyebilirsin
- Öneriyi farklı bir tarihe taşıyabilirsin

## YANIT FORMATI

Kullanıcıya yanıt verirken:
1. Kısa ve öz ol
2. Bullet point kullan
3. Sayıları ve metrikleri vurgula
4. Trendleri ve değişimleri belirt
5. Actionable önerilerde bulun
6. İlgili önerileri <SUGGESTION> tagları ile sun
7. Önemli bilgileri <MEMORY> tagları ile kaydet
8. Mevcut verileri düzenlemek için <EDIT> tagları kullan
9. Silme işlemleri için <DELETE> tagları kullan
"""

    return prompt


def parse_data_request(ai_response: str) -> Optional[Dict[str, Any]]:
    """
    Parse AI response to extract data request JSON

    Args:
        ai_response: AI's response text that may contain JSON data request

    Returns:
        Parsed data request dict or None if no valid request found
    """
    import json
    import re

    # Try to find JSON code blocks
    json_pattern = r'```json\s*(.*?)\s*```'
    matches = re.findall(json_pattern, ai_response, re.DOTALL)

    if matches:
        for match in matches:
            try:
                data = json.loads(match)
                if "data_request" in data:
                    return data["data_request"]
            except json.JSONDecodeError:
                continue

    # Try to find raw JSON
    try:
        # Look for { "data_request": ... }
        start = ai_response.find('{"data_request"')
        if start != -1:
            # Find the matching closing brace
            brace_count = 0
            end = start
            for i, char in enumerate(ai_response[start:], start=start):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end = i + 1
                        break

            if end > start:
                json_str = ai_response[start:end]
                data = json.loads(json_str)
                if "data_request" in data:
                    return data["data_request"]
    except:
        pass

    return None


def calculate_date_range(time_range: str, custom_range: Optional[Dict] = None) -> tuple[datetime, datetime]:
    """
    Calculate start and end dates based on time range

    Args:
        time_range: Time range enum value
        custom_range: Custom date range with start_date and end_date

    Returns:
        Tuple of (start_date, end_date)
    """
    now = datetime.now(timezone.utc)

    if time_range == TimeRange.TODAY:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now

    elif time_range == TimeRange.YESTERDAY:
        yesterday = now - timedelta(days=1)
        start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end = yesterday.replace(hour=23, minute=59, second=59)

    elif time_range == TimeRange.WEEK:
        start = now - timedelta(days=7)
        end = now

    elif time_range == TimeRange.MONTH:
        start = now - timedelta(days=30)
        end = now

    elif time_range == TimeRange.YEAR:
        start = now - timedelta(days=365)
        end = now

    elif time_range == TimeRange.CUSTOM and custom_range:
        start = datetime.fromisoformat(str(custom_range.get("start_date")).replace('Z', '+00:00'))
        end = datetime.fromisoformat(str(custom_range.get("end_date")).replace('Z', '+00:00'))

    else:  # ALL
        start = datetime(2020, 1, 1)  # Arbitrary old date
        end = now

    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    else:
        start = start.astimezone(timezone.utc)

    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    else:
        end = end.astimezone(timezone.utc)

    return start, end


def validate_data_request(request: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate a data request

    Args:
        request: Data request dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check required fields
    if "category" not in request:
        return False, "Missing 'category' field"

    # Validate category
    try:
        category = DataCategory(request["category"])
    except ValueError:
        valid_categories = [c.value for c in DataCategory]
        return False, f"Invalid category. Valid options: {', '.join(valid_categories)}"

    # Validate time_range if provided
    if "time_range" in request:
        try:
            TimeRange(request["time_range"])
        except ValueError:
            valid_ranges = [r.value for r in TimeRange]
            return False, f"Invalid time_range. Valid options: {', '.join(valid_ranges)}"

    # Validate custom_range if time_range is custom
    if request.get("time_range") == TimeRange.CUSTOM:
        if "custom_range" not in request:
            return False, "custom_range required when time_range is 'custom'"

        custom_range = request["custom_range"]
        if "start_date" not in custom_range or "end_date" not in custom_range:
            return False, "custom_range must contain start_date and end_date"

    return True, None


def format_response_with_request_info(data_request: Dict[str, Any]) -> str:
    """
    Format a user-friendly message about the data request being processed

    Args:
        data_request: Validated data request

    Returns:
        Formatted message
    """
    category = data_request.get("category", "bilinmeyen")
    time_range = data_request.get("time_range", "all")

    time_range_tr = {
        "today": "bugün",
        "yesterday": "dün",
        "week": "bu hafta",
        "month": "bu ay",
        "year": "bu yıl",
        "all": "tüm zamanlar",
        "custom": "özel tarih aralığı"
    }

    category_tr = {
        "tasks": "görevler",
        "notes": "notlar",
        "health": "sağlık verileri",
        "sleep": "uyku verileri",
        "weight": "kilo verileri",
        "meals": "yemek kayıtları",
        "workouts": "antrenman kayıtları",
        "portfolio": "portföy verileri",
        "goals": "finansal hedefler",
        "budget": "bütçe bilgileri",
        "salary": "maaş bilgileri",
        "friends": "arkadaş listesi"
    }

    category_name = category_tr.get(category, category)
    time_name = time_range_tr.get(time_range, time_range)

    return f"📊 **{category_name}** verilerini analiz ediyorum ({time_name})..."


def parse_suggestions_and_memories(ai_response: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Parse AI response to extract suggestions and memory items

    Args:
        ai_response: AI's response text that may contain SUGGESTION and MEMORY tags

    Returns:
        Dict with 'suggestions' and 'memories' lists
    """
    import re

    suggestions = []
    memories = []

    # Parse SUGGESTION tags
    # Format: <SUGGESTION type="task">Text here[metadata:key=value,key2=value2]</SUGGESTION>
    suggestion_pattern = r'<SUGGESTION\s+type="([^"]+)">(.*?)</SUGGESTION>'
    suggestion_matches = re.findall(suggestion_pattern, ai_response, re.DOTALL | re.IGNORECASE)

    for suggestion_type, content in suggestion_matches:
        content = content.strip()

        # Extract metadata if present
        metadata = {}
        metadata_pattern = r'\[metadata:([^\]]+)\]'
        metadata_match = re.search(metadata_pattern, content)

        if metadata_match:
            metadata_str = metadata_match.group(1)
            # Remove metadata from content
            content = re.sub(metadata_pattern, '', content).strip()

            # Parse metadata key=value pairs
            # Use lookahead to only split on commas followed by key=value,
            # preserving commas within values (e.g. menu items)
            pairs = re.split(r',(?=\s*[a-zA-Z_]\w*\s*=)', metadata_str)
            for pair in pairs:
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    metadata[key.strip()] = value.strip()

        suggestions.append({
            'type': suggestion_type,
            'description': content,
            'metadata': metadata if metadata else None
        })

    # Parse MEMORY tags
    # Format: <MEMORY category="habits">Text here</MEMORY>
    memory_pattern = r'<MEMORY(?:\s+category="([^"]+)")?>(.*?)</MEMORY>'
    memory_matches = re.findall(memory_pattern, ai_response, re.DOTALL | re.IGNORECASE)

    for category, content in memory_matches:
        normalized_category = (category or "general").strip() or "general"
        normalized_content = (content or "").strip()
        if not normalized_content:
            continue
        memories.append({
            'content': normalized_content,
            'category': normalized_category
        })

    return {
        'suggestions': suggestions,
        'memories': memories
    }


def parse_edit_suggestions(ai_response: str) -> List[Dict[str, Any]]:
    """
    Parse AI response to extract EDIT tags for modifying existing items

    Args:
        ai_response: AI's response text that may contain EDIT tags

    Returns:
        List of edit suggestion dictionaries
    """
    import re

    edits = []

    # Parse EDIT tags
    # Format: <EDIT targetType="task" targetId="uuid">Field: field\nNewValue: value\nReason: reason</EDIT>
    edit_pattern = r'<EDIT\s+targetType="([^"]+)"\s+targetId="([^"]+)">([^<]+)</EDIT>'
    edit_matches = re.findall(edit_pattern, ai_response, re.DOTALL)

    for target_type, target_id, content in edit_matches:
        content = content.strip()

        # Parse field, newValue, reason from content
        field_match = re.search(r'Field:\s*(.+?)(?:\n|$)', content, re.MULTILINE)
        value_match = re.search(r'NewValue:\s*(.+?)(?:\n|$)', content, re.MULTILINE)
        reason_match = re.search(r'Reason:\s*(.+?)(?:\n|$)', content, re.MULTILINE)

        if field_match and value_match:
            edits.append({
                'targetType': target_type.strip(),
                'targetId': target_id.strip(),
                'field': field_match.group(1).strip(),
                'newValue': value_match.group(1).strip(),
                'reason': reason_match.group(1).strip() if reason_match else ""
            })

    return edits


def parse_delete_requests(ai_response: str) -> List[Dict[str, Any]]:
    """
    Parse AI response to extract DELETE tags for removing items

    Args:
        ai_response: AI's response text that may contain DELETE tags

    Returns:
        List of delete request dictionaries
    """
    import re

    deletes = []

    # Parse DELETE tags
    # Format: <DELETE targetType="task" targetId="uuid">Reason: reason</DELETE>
    delete_pattern = r'<DELETE\s+targetType="([^"]+)"\s+targetId="([^"]+)">(.*?)</DELETE>'
    delete_matches = re.findall(delete_pattern, ai_response, re.DOTALL)

    for target_type, target_id, content in delete_matches:
        content = content.strip()

        # Parse reason from content
        reason_match = re.search(r'Reason:\s*(.+?)(?:\n|$)', content, re.MULTILINE)
        reason = reason_match.group(1).strip() if reason_match else content.strip()

        deletes.append({
            'targetType': target_type.strip(),
            'targetId': target_id.strip(),
            'reason': reason
        })

    return deletes


def remove_tags_from_response(ai_response: str) -> str:
    """
    Remove SUGGESTION and MEMORY tags from AI response to get clean text

    Args:
        ai_response: AI's response with tags

    Returns:
        Clean response text without tags
    """
    import re

    # Remove SUGGESTION tags
    clean_response = re.sub(r'<SUGGESTION[^>]+>.*?</SUGGESTION>', '', ai_response, flags=re.DOTALL)

    # Remove MEMORY tags
    clean_response = re.sub(r'<MEMORY[^>]+>.*?</MEMORY>', '', clean_response, flags=re.DOTALL)

    # Clean up extra whitespace
    clean_response = re.sub(r'\n\s*\n', '\n\n', clean_response)
    clean_response = clean_response.strip()

    return clean_response


# Export main functions
__all__ = [
    'AI_CAPABILITIES',
    'DataCategory',
    'TimeRange',
    'get_capabilities_prompt',
    'parse_data_request',
    'calculate_date_range',
    'validate_data_request',
    'format_response_with_request_info',
    'parse_suggestions_and_memories',
    'parse_edit_suggestions',
    'parse_delete_requests',
    'remove_tags_from_response'
]

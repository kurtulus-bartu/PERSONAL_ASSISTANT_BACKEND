"""
AI Capabilities and Data Request System
Handles AI capability listing and data request processing
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
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
            "operations": ["read", "create", "update", "analyze"],
            "filters": ["date_range", "status", "project", "tag"]
        },
        "notes": {
            "description": "Kullanıcı notları",
            "operations": ["read", "create", "search"],
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
            "operations": ["read", "analyze"],
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
        }
    },
    "actions": {
        "create_task": "Yeni görev oluştur",
        "create_note": "Not ekle",
        "add_meal": "Yemek kaydı ekle",
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

## KULLANICI İLE ETKİLEŞİM

- Türkçe konuş
- Dostça ve profesyonel ol
- Açık ve anlaşılır açıklamalar yap
- Veri görselleştirmesi öner (grafik, tablo, vb.)
- Önerilerde bulunurken mantıklı gerekçeler sun
- Kullanıcı gizliliğine saygı göster

## YANIT FORMATI

Kullanıcıya yanıt verirken:
1. Kısa ve öz ol
2. Bullet point kullan
3. Sayıları ve metrikleri vurgula
4. Trendleri ve değişimleri belirt
5. Actionable önerilerde bulun
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
    now = datetime.now()

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
        start = datetime.fromisoformat(custom_range.get("start_date"))
        end = datetime.fromisoformat(custom_range.get("end_date"))

    else:  # ALL
        start = datetime(2020, 1, 1)  # Arbitrary old date
        end = now

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


# Export main functions
__all__ = [
    'AI_CAPABILITIES',
    'DataCategory',
    'TimeRange',
    'get_capabilities_prompt',
    'parse_data_request',
    'calculate_date_range',
    'validate_data_request',
    'format_response_with_request_info'
]

from fastapi import FastAPI, HTTPException, Depends, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
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


DAILY_SUGGESTIONS_SYSTEM_PROMPT = """Sen bir beslenme koçusun ve kullanıcıya yarın için yemek önerileri çıkarıyorsun.

ÇIKTI KURALLARI:
- SADECE SUGGESTION tagları yaz. Başka metin ekleme.
- Format:
  <SUGGESTION type="meal">ACIKLAMA [metadata:mealType=Kahvaltı,date=YYYY-MM-DD,calories=450,title=...,notes=...]</SUGGESTION>
  <SUGGESTION type="task">ACIKLAMA [metadata:title=...,date=YYYY-MM-DD,durationMinutes=30,notes=...]</SUGGESTION>
- Metadata değerlerinde virgül kullanma. Gerekirse '-' kullan.
- calories sadece sayı olsun (kcal yazma).
- date mutlaka hedef tarih (YYYY-MM-DD) olmalı.
- Yemek önerileri Türkçe, kısa ve net olmalı.
- En az 3 öğün (Kahvaltı, Öğle, Akşam) öner. İstersen Atıştırmalık ekleyebilirsin.
- include_general true ise 1 adet task önerisi ekle.
"""


def _parse_iso_date(value: str) -> Optional[datetime]:
    try:
        cleaned = value.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


def _build_daily_suggestions_context(backup_data: Dict[str, Any]) -> str:
    meals = backup_data.get("mealEntries", [])
    health = backup_data.get("healthEntries", [])
    sleep = backup_data.get("sleepEntries", [])
    workouts = backup_data.get("workoutEntries", [])

    def meal_key(entry: Dict[str, Any]) -> datetime:
        raw = str(entry.get("date", ""))
        parsed = _parse_iso_date(raw) or datetime.min
        return parsed

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

    calories_by_day: Dict[str, float] = {}
    for meal in compact_meals:
        day = meal.get("date") or ""
        calories_by_day[day] = calories_by_day.get(day, 0) + float(meal.get("calories", 0) or 0)
    avg_daily_calories = round(
        sum(calories_by_day.values()) / max(len(calories_by_day), 1),
        0
    )

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

    compact_sleep = [
        {
            "date": str(s.get("date", ""))[:10],
            "quality": s.get("quality", 0)
        }
        for s in sleep[-7:]
    ]

    compact_workouts = [
        {
            "date": str(w.get("date", ""))[:10],
            "type": w.get("workoutType"),
            "duration": w.get("duration", 0)
        }
        for w in workouts[-7:]
    ]

    context = {
        "recent_meals": compact_meals,
        "avg_daily_calories": avg_daily_calories,
        "recent_health": compact_health,
        "recent_sleep": compact_sleep,
        "recent_workouts": compact_workouts
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
        target_date = request.target_date
        if target_date:
            parsed_date = _parse_iso_date(target_date)
            if parsed_date:
                target_date = parsed_date.date().isoformat()
        else:
            target_date = (datetime.now() + timedelta(days=1)).date().isoformat()

        include_general = bool(request.include_general)

        if not request.force:
            already_exists = supabase_service.has_ai_suggestions_for_date(
                user_id=x_user_id,
                target_date=target_date
            )
            if already_exists:
                return DailySuggestionsResponse(
                    success=True,
                    saved_count=0,
                    skipped=True,
                    message="Suggestions already exist for target date."
                )

        backup_data = await supabase_service.get_backup_data(user_id=x_user_id)
        context = _build_daily_suggestions_context(backup_data)

        message = (
            f"Hedef tarih: {target_date}.\n"
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
                message="No suggestions generated."
            )

        saved_count = supabase_service.save_ai_suggestions(
            user_id=x_user_id,
            suggestions=suggestions,
            target_date=target_date,
            source="daily_suggestions"
        )

        return DailySuggestionsResponse(
            success=True,
            saved_count=saved_count,
            skipped=False,
            message="Suggestions saved."
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Daily suggestions failed: {str(e)}")


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

@app.post("/api/cron/daily-check")
async def cron_daily_check():
    """
    CronJob endpoint - Called every 5 minutes
    - Generates AI suggestions for all users
    - Sends daily summary emails to friends (if not sent today)
    - Sends personal summary email to user (if not sent today)
    """
    try:
        # Get all unique user IDs from database
        all_user_ids = supabase_service.get_all_user_ids()

        processed_count = 0
        errors = []

        for user_id in all_user_ids:
            try:
                # 1. Generate AI suggestions (if not already generated for today)
                await generate_ai_suggestions_for_user(user_id)

                # 2. Check and send friend emails
                await check_and_send_friend_emails(user_id)

                # 3. Check and send personal summary email
                await check_and_send_personal_email(user_id)

                processed_count += 1

            except Exception as e:
                errors.append({
                    "user_id": user_id,
                    "error": str(e)
                })

        return {
            "success": True,
            "processed_users": processed_count,
            "total_users": len(all_user_ids),
            "errors": errors
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def generate_ai_suggestions_for_user(user_id: str):
    """Generate AI suggestions for a single user"""
    try:
        today = datetime.now().strftime("%Y-%m-%d")

        # Check if suggestions already exist for today
        if supabase_service.has_ai_suggestions_for_date(user_id, today):
            return  # Skip if already generated

        # Get user data
        user_data = supabase_service.get_user_data_for_ai(user_id)

        # Generate AI suggestions
        service = get_enhanced_gemini_service()
        prompt = generate_daily_ai_prompt(user_data)

        _, _, suggestions, _ = service.chat(
            message=prompt,
            user_data=user_data,
            conversation_history=[],
            user_id=user_id
        )

        # Save suggestions
        if suggestions:
            supabase_service.save_ai_suggestions(
                user_id=user_id,
                suggestions=suggestions,
                target_date=today
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


def generate_daily_ai_prompt(user_data: Dict[str, Any]) -> str:
    """Generate AI prompt for daily suggestions"""
    today = datetime.now().strftime("%Y-%m-%d")

    prompt = f"""Sen bir yapay zeka asistanısın. Kullanıcının verilerini analiz ederek günlük öneriler üretiyorsun.

Bugünün tarihi: {today}

Kullanıcının verileri:
- Görevler: {len(user_data.get('tasks', []))} görev
- Etkinlikler: {len(user_data.get('events', []))} etkinlik
- Notlar: {len(user_data.get('notes', []))} not
- Sağlık verileri: {len(user_data.get('health_entries', []))} kayıt

Lütfen kullanıcı için aşağıdaki önerileri oluştur:

1. **Görev Önerileri** (2-3 tane): Kullanıcının mevcut görevlerine ve alışkanlıklarına göre yeni görev önerileri
2. **Etkinlik Önerileri** (1-2 tane): Kullanıcının programına uygun etkinlik önerileri
3. **Genel Öneriler** (2-3 tane): Sağlık, verimlilik, yaşam kalitesi ile ilgili genel öneriler

Her öneri için:
- type: "task", "event" veya "general"
- content: Öneri içeriği (açıklayıcı ve net)
- priority: "high", "medium" veya "low"
- category: İlgili kategori

Lütfen önerileri JSON formatında döndür."""

    return prompt


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

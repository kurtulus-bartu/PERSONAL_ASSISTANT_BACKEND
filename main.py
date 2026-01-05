from fastapi import FastAPI, HTTPException, Depends, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
from datetime import datetime
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
    EmailResponse
)
from tefas_crawler import TEFASCrawler
from stock_service import stock_service
from gemini_service import GeminiService
from enhanced_gemini_service import EnhancedGeminiService
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


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

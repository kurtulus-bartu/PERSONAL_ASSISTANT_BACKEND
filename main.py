from fastapi import FastAPI, HTTPException, Depends, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
from datetime import datetime
import os

from models import (
    FundInvestment,
    FundPrice,
    FundDetail,
    PortfolioSummary,
    GeminiRequest,
    GeminiResponse,
    PortfolioHistoryResponse,
    PortfolioRange,
    EnhancedGeminiRequest,
    EnhancedGeminiResponse,
    QuickAnalysisRequest,
    QuickAnalysisResponse
)
from tefas_crawler import TEFASCrawler
from gemini_service import GeminiService
from enhanced_gemini_service import EnhancedGeminiService
from supabase_service import SupabaseService

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


def get_gemini_service(api_key: str) -> GeminiService:
    """Gemini servisini döndür"""
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
            raise HTTPException(status_code=404, detail=f"Fon bulunamadı: {fund_code}")

        return FundPrice(**result)
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


@app.post("/api/portfolio/calculate")
async def calculate_portfolio(investments: List[FundInvestment]):
    """
    Portföy kar/zarar hesaplama

    Args:
        investments: Kullanıcının fon yatırımları listesi
    """
    try:
        total_investment = 0
        total_current_value = 0
        funds_detail = []

        for investment in investments:
            # Her fon için kar/zarar hesapla
            result = tefas_crawler.calculate_profit_loss(
                fund_code=investment.fund_code,
                purchase_price=investment.purchase_price,
                purchase_amount=investment.investment_amount
            )

            if 'error' in result:
                # Hata varsa atla
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

        total_profit_loss = total_current_value - total_investment
        profit_loss_percent = (total_profit_loss / total_investment * 100) if total_investment > 0 else 0

        # Günlük değişim hesaplama (basitleştirilmiş)
        daily_change = 0  # Bu kısmı geçmiş verilerle daha detaylı hesaplayabilirsin

        summary = PortfolioSummary(
            total_investment=round(total_investment, 2),
            current_value=round(total_current_value, 2),
            total_profit_loss=round(total_profit_loss, 2),
            profit_loss_percent=round(profit_loss_percent, 2),
            daily_change=daily_change,
            funds=funds_detail
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
        request: Mesaj, bağlam ve API anahtarı
    """
    try:
        service = get_gemini_service(request.api_key)

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
    api_key: str,
    question: Optional[str] = None
):
    """
    Portföy analizi yap (AI destekli)

    Args:
        investments: Fon yatırımları
        api_key: Gemini API anahtarı
        question: Kullanıcı sorusu (opsiyonel)
    """
    try:
        # Önce portföy hesapla
        portfolio_result = await calculate_portfolio(investments)

        # AI analizi yap
        service = get_gemini_service(api_key)
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
        service = EnhancedGeminiService(api_key=request.api_key)

        # Process chat with data request loop
        response_text, updated_history = service.chat(
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
        service = EnhancedGeminiService(api_key=request.api_key)

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


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

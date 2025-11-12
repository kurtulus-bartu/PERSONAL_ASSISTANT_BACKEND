from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class FundInvestment(BaseModel):
    """Kullanıcının fon yatırım bilgisi"""
    fund_code: str = Field(..., description="TEFAS fon kodu (örn: TQE)")
    fund_name: Optional[str] = Field(None, description="Fon adı")
    investment_amount: float = Field(..., description="Yatırılan miktar (TL)")
    purchase_price: float = Field(..., description="Alış fiyatı")
    purchase_date: datetime = Field(..., description="Alış tarihi")
    units: Optional[float] = Field(None, description="Alınan pay adedi (otomatik hesaplanır)")


class FundPrice(BaseModel):
    """TEFAS fon fiyat bilgisi"""
    fund_code: str
    fund_name: str
    price: float
    date: str
    change_percent: Optional[float] = None


class FundDetail(BaseModel):
    """Fon detay bilgisi"""
    fund_code: str
    fund_name: str
    investment_amount: float
    current_value: float
    profit_loss: float
    profit_loss_percent: float
    purchase_price: float
    current_price: float
    units: float


class PortfolioSummary(BaseModel):
    """Portföy özeti"""
    total_investment: float = Field(..., description="Toplam yatırım")
    current_value: float = Field(..., description="Güncel değer")
    total_profit_loss: float = Field(..., description="Toplam kar/zarar")
    profit_loss_percent: float = Field(..., description="Kar/zarar yüzdesi")
    daily_change: float = Field(..., description="Günlük değişim")
    funds: List[FundDetail] = Field(default_factory=list, description="Fonların detaylı bilgisi")


class GeminiRequest(BaseModel):
    """Gemini API isteği"""
    message: str = Field(..., description="Kullanıcı mesajı")
    context: Optional[str] = Field(None, description="Bağlam bilgisi")
    api_key: str = Field(..., description="Gemini API anahtarı")


class GeminiResponse(BaseModel):
    """Gemini API yanıtı"""
    response: str = Field(..., description="AI yanıtı")
    timestamp: datetime = Field(default_factory=datetime.now)


# -------------------------------------------------------------------------
# Supabase / History modelleri
# -------------------------------------------------------------------------


class PortfolioRange(str, Enum):
    day = "day"
    week = "week"
    month = "month"
    year = "year"


class PortfolioHistoryPoint(BaseModel):
    timestamp: datetime
    total_value: float
    fund_code: Optional[str] = None


class FundReference(BaseModel):
    fund_code: str
    fund_name: Optional[str] = None


class FundPerformance(BaseModel):
    fund_code: str
    fund_name: Optional[str] = None
    latest_value: float
    daily_change: float
    weekly_change: float
    monthly_change: float
    yearly_change: float


class PortfolioHistoryResponse(BaseModel):
    range: PortfolioRange
    fund_code: Optional[str] = None
    start_date: datetime
    end_date: datetime
    points: List[PortfolioHistoryPoint] = Field(default_factory=list)
    change_value: float
    change_percent: float
    available_funds: List[FundReference] = Field(default_factory=list)
    performances: List[FundPerformance] = Field(default_factory=list)

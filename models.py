from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
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


# -------------------------------------------------------------------------
# Enhanced AI Chat Models (AŞAMA 4)
# -------------------------------------------------------------------------


class ConversationMessage(BaseModel):
    """Single conversation message"""
    role: str = Field(..., description="Message role: user, assistant, or system")
    content: str = Field(..., description="Message content")
    is_user: bool = Field(..., description="Whether message is from user")
    data_request: Optional[bool] = Field(False, description="Whether this is a data request notification")
    timestamp: Optional[datetime] = Field(default_factory=datetime.now)


class EnhancedGeminiRequest(BaseModel):
    """Enhanced Gemini AI request with full user data"""
    message: str = Field(..., description="User message")
    user_data: Dict[str, Any] = Field(..., description="Complete user data from frontend")
    conversation_history: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Previous conversation messages"
    )
    api_key: str = Field(..., description="Gemini API key")
    user_id: Optional[str] = Field(None, description="User ID for database queries")


class EnhancedGeminiResponse(BaseModel):
    """Enhanced Gemini AI response"""
    response: str = Field(..., description="AI response text")
    conversation_history: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Updated conversation history"
    )
    data_requests_made: int = Field(0, description="Number of data requests made")
    suggestions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="AI-generated suggestions for user actions"
    )
    memories: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="AI-generated memory items about user"
    )
    timestamp: datetime = Field(default_factory=datetime.now)


class QuickAnalysisRequest(BaseModel):
    """Request for quick data analysis"""
    category: str = Field(..., description="Data category (tasks, health, portfolio, etc.)")
    user_data: Dict[str, Any] = Field(..., description="User data")
    time_range: str = Field("week", description="Time range (today, week, month, year, all)")
    api_key: str = Field(..., description="Gemini API key")
    user_id: Optional[str] = Field(None, description="User ID")


class QuickAnalysisResponse(BaseModel):
    """Quick analysis response"""
    analysis: str = Field(..., description="Analysis result")
    category: str = Field(..., description="Analyzed category")
    time_range: str = Field(..., description="Time range used")
    timestamp: datetime = Field(default_factory=datetime.now)


# -------------------------------------------------------------------------
# Email Models
# -------------------------------------------------------------------------


class EmailRecipient(BaseModel):
    """Email recipient information"""
    email: str = Field(..., description="Recipient email address")
    name: str = Field(..., description="Recipient name")


class DailySummaryRequest(BaseModel):
    """Request to send daily task summary emails"""
    user_name: str = Field(..., description="User's name")
    tasks: List[Dict[str, Any]] = Field(..., description="List of tasks")
    recipients: List[EmailRecipient] = Field(..., description="Recipients (friends)")
    date: Optional[str] = Field(None, description="Date string (defaults to today)")


class EmailResponse(BaseModel):
    """Email sending response"""
    success: bool = Field(..., description="Whether all emails were sent successfully")
    sent_count: int = Field(0, description="Number of emails sent successfully")
    failed_count: int = Field(0, description="Number of failed emails")
    details: List[Dict[str, Any]] = Field(default_factory=list, description="Details for each recipient")

import os
import json
from typing import List, Dict, Optional
import google.generativeai as genai


class GeminiService:
    """Google Gemini AI Servisi"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Gemini servisini başlatır

        Args:
            api_key: Gemini API anahtarı (None ise çevre değişkeninden alır)
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY gerekli")

        genai.configure(api_key=self.api_key)
        # Gemini 1.5 Flash - hızlı ve uygun maliyetli
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    def generate_response(
        self,
        message: str,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Gemini'den yanıt al

        Args:
            message: Kullanıcı mesajı
            context: Bağlam bilgisi (portföy verileri, vb.)
            system_prompt: Sistem promptu

        Returns:
            AI yanıtı
        """
        try:
            # Prompt oluştur
            full_prompt = ""

            if system_prompt:
                full_prompt += f"{system_prompt}\n\n"

            if context:
                full_prompt += f"Bağlam:\n{context}\n\n"

            full_prompt += f"Kullanıcı: {message}\n\nAsistan:"

            # Yanıt al
            response = self.model.generate_content(full_prompt)

            return response.text

        except Exception as e:
            return f"Hata: {str(e)}"

    def analyze_portfolio(
        self,
        portfolio_data: Dict,
        user_question: Optional[str] = None
    ) -> str:
        """
        Portföy analizi yap

        Args:
            portfolio_data: Portföy verileri
            user_question: Kullanıcı sorusu (opsiyonel)

        Returns:
            Analiz sonucu
        """
        system_prompt = """Sen bir finans asistanısın. Kullanıcının TEFAS fon portföyünü analiz ediyorsun.

Görevlerin:
- Portföy performansını değerlendirmek
- Kar/zarar durumunu açıklamak
- Yatırım önerileri sunmak
- Risk değerlendirmesi yapmak

Türkçe, açık ve anlaşılır şekilde yanıt ver."""

        context = f"Portföy Verileri:\n{json.dumps(portfolio_data, indent=2, ensure_ascii=False)}"

        message = user_question or "Bu portföyü analiz et ve değerlendirmeni sun."

        return self.generate_response(
            message=message,
            context=context,
            system_prompt=system_prompt
        )

    def financial_chat(
        self,
        message: str,
        conversation_history: Optional[List[Dict]] = None,
        portfolio_context: Optional[Dict] = None
    ) -> str:
        """
        Finansal sohbet

        Args:
            message: Kullanıcı mesajı
            conversation_history: Konuşma geçmişi
            portfolio_context: Portföy bağlamı

        Returns:
            AI yanıtı
        """
        system_prompt = """Sen yardımcı bir finans asistanısın. Kullanıcıya TEFAS fonları ve yatırımları hakkında yardım ediyorsun.

Yeteneklerin:
- TEFAS fonları hakkında bilgi vermek
- Portföy analizi yapmak
- Yatırım önerileri sunmak
- Finansal soruları yanıtlamak

Türkçe, dostça ve profesyonel bir dille iletişim kur."""

        # Bağlam oluştur
        context_parts = []

        if portfolio_context:
            context_parts.append(f"Portföy Bilgileri:\n{json.dumps(portfolio_context, indent=2, ensure_ascii=False)}")

        if conversation_history:
            history_text = "\nKonuşma Geçmişi:\n"
            for msg in conversation_history[-5:]:  # Son 5 mesaj
                role = "Kullanıcı" if msg.get("is_user") else "Asistan"
                history_text += f"{role}: {msg.get('content')}\n"
            context_parts.append(history_text)

        context = "\n\n".join(context_parts) if context_parts else None

        return self.generate_response(
            message=message,
            context=context,
            system_prompt=system_prompt
        )

    def generate_investment_advice(
        self,
        user_profile: Dict,
        market_data: Optional[Dict] = None
    ) -> str:
        """
        Yatırım önerisi oluştur

        Args:
            user_profile: Kullanıcı profili (risk toleransı, hedefler, vb.)
            market_data: Piyasa verileri

        Returns:
            Yatırım önerisi
        """
        system_prompt = """Sen bir yatırım danışmanısın. Kullanıcının profiline göre TEFAS fonlarında yatırım önerileri sunuyorsun.

Dikkate alacağın faktörler:
- Kullanıcının risk toleransı
- Yatırım hedefleri
- Yatırım süresi
- Mevcut portföy durumu
- Piyasa koşulları

Önerilerini mantıklı gerekçelerle destekle."""

        context_parts = [f"Kullanıcı Profili:\n{json.dumps(user_profile, indent=2, ensure_ascii=False)}"]

        if market_data:
            context_parts.append(f"Piyasa Verileri:\n{json.dumps(market_data, indent=2, ensure_ascii=False)}")

        context = "\n\n".join(context_parts)

        return self.generate_response(
            message="Bana uygun yatırım fonları öner ve nedenlerini açıkla.",
            context=context,
            system_prompt=system_prompt
        )


# Test fonksiyonu
if __name__ == "__main__":
    # API key'i çevre değişkeninden al
    service = GeminiService()

    # Örnek portföy analizi
    portfolio = {
        "total_investment": 10000,
        "current_value": 10500,
        "profit_loss": 500,
        "profit_loss_percent": 5.0,
        "funds": [
            {
                "fund_code": "TQE",
                "fund_name": "Tacirler Portföy Değişken Fon",
                "investment": 5000,
                "current_value": 5300,
                "profit_loss": 300
            }
        ]
    }

    print("Portföy Analizi:")
    analysis = service.analyze_portfolio(portfolio)
    print(analysis)

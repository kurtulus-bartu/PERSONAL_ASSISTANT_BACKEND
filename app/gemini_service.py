import os
import json
from typing import List, Dict, Optional, Set
import google.generativeai as genai

_INVALID_MODELS: Set[str] = set()


def _expand_model_candidates(models: List[str]) -> List[str]:
    expanded: List[str] = []
    for name in models:
        if not name:
            continue
        if name not in expanded:
            expanded.append(name)
        if not name.startswith("models/"):
            prefixed = f"models/{name}"
            if prefixed not in expanded:
                expanded.append(prefixed)
    return expanded


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
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        fallback_models = [
            model_name,
            "gemini-3.0-flash",
            "gemini-3-flash",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash"
        ]
        self.model_candidates = _expand_model_candidates(fallback_models)
        self.model_name = self.model_candidates[0]
        self.model = genai.GenerativeModel(self.model_name)
        self.invalid_models = _INVALID_MODELS

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
            response = self._generate_with_fallback(full_prompt)

            return response.text

        except Exception as e:
            return f"Hata: {str(e)}"

    def _is_model_not_found_error(self, error: Exception) -> bool:
        message = str(error).lower()
        return "not found" in message or "404" in message

    def _generate_with_fallback(self, prompt: str):
        last_error: Optional[Exception] = None
        for candidate in self.model_candidates:
            if candidate in self.invalid_models:
                continue
            if self.model_name != candidate:
                self.model_name = candidate
                self.model = genai.GenerativeModel(candidate)
            try:
                return self.model.generate_content(prompt)
            except Exception as e:
                last_error = e
                if self._is_model_not_found_error(e):
                    self.invalid_models.add(candidate)
                    print(f"⚠️ Gemini model '{candidate}' not found. Falling back.")
                    continue
                raise
        if last_error:
            raise last_error
        raise RuntimeError("No available Gemini model.")

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

"""
Enhanced Gemini Service with AI Capabilities Integration
Implements data request loop and filtered data provision
"""

import os
import json
from typing import List, Dict, Optional, Any, Tuple
import google.generativeai as genai

from .ai_capabilities import (
    get_capabilities_prompt,
    parse_data_request,
    format_response_with_request_info,
    parse_suggestions_and_memories,
    remove_tags_from_response
)
from .ai_data_provider import AIDataProvider


class EnhancedGeminiService:
    """
    Enhanced Google Gemini AI Service
    Integrates with AI capabilities and data provider systems
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize enhanced Gemini service

        Args:
            api_key: Gemini API key (uses env variable if None)
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY gerekli")

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash')

        # Cache the capabilities prompt
        self.capabilities_prompt = get_capabilities_prompt()

    def chat(
        self,
        user_message: str,
        user_data: Dict[str, Any],
        conversation_history: Optional[List[Dict]] = None,
        user_id: Optional[str] = None,
        max_data_requests: int = 3
    ) -> Tuple[str, List[Dict], List[Dict], List[Dict]]:
        """
        Main chat interface with data request loop

        Args:
            user_message: User's message
            user_data: Complete user data from frontend
            conversation_history: Previous conversation messages
            user_id: User ID for database queries
            max_data_requests: Maximum number of data requests per conversation turn

        Returns:
            Tuple of (AI response, updated conversation history, suggestions, memories)
        """
        # Initialize conversation history if None
        if conversation_history is None:
            conversation_history = []

        # Add user message to history
        conversation_history.append({
            "role": "user",
            "content": user_message,
            "is_user": True
        })

        # Create AI data provider
        data_provider = AIDataProvider(user_data, user_id)

        # Data request loop
        data_request_count = 0
        ai_response = None
        collected_data = []

        while data_request_count < max_data_requests:
            # Build prompt for AI
            prompt = self._build_prompt(
                user_message=user_message,
                conversation_history=conversation_history[:-1],  # Exclude current message
                capabilities_prompt=self.capabilities_prompt,
                collected_data=collected_data
            )

            # Get AI response
            try:
                response = self.model.generate_content(prompt)
                ai_response = response.text
            except Exception as e:
                ai_response = f"Üzgünüm, bir hata oluştu: {str(e)}"
                break

            # Parse for data requests
            data_request = parse_data_request(ai_response)

            if data_request is None:
                # No data request found, this is the final response
                break

            # Process data request
            data_request_count += 1

            # Get requested data
            data_result = data_provider.process_data_request(data_request)

            # Add to collected data for context
            collected_data.append({
                "request": data_request,
                "result": data_result
            })

            # Add data request info to conversation
            request_info = format_response_with_request_info(data_request)
            conversation_history.append({
                "role": "system",
                "content": request_info,
                "is_user": False,
                "data_request": True
            })

            # If we've hit max requests, ask AI to respond with what it has
            if data_request_count >= max_data_requests:
                final_prompt = self._build_final_prompt(
                    user_message=user_message,
                    collected_data=collected_data
                )

                try:
                    response = self.model.generate_content(final_prompt)
                    ai_response = response.text
                except Exception as e:
                    ai_response = f"Veri toplandı ancak analiz sırasında hata oluştu: {str(e)}"

                break

        # Parse suggestions and memories from AI response
        parsed = parse_suggestions_and_memories(ai_response or "")
        suggestions = parsed.get('suggestions', [])
        memories = parsed.get('memories', [])

        # Remove tags from response for clean text
        clean_response = remove_tags_from_response(ai_response or "Yanıt oluşturulamadı.")

        # Add AI response to history (clean version without tags)
        if ai_response:
            conversation_history.append({
                "role": "assistant",
                "content": clean_response,
                "is_user": False
            })

        return clean_response, conversation_history, suggestions, memories

    def _build_prompt(
        self,
        user_message: str,
        conversation_history: List[Dict],
        capabilities_prompt: str,
        collected_data: List[Dict]
    ) -> str:
        """
        Build complete prompt for AI

        Args:
            user_message: Current user message
            conversation_history: Previous messages
            capabilities_prompt: AI capabilities description
            collected_data: Data collected from previous requests in this turn

        Returns:
            Complete prompt string
        """
        prompt_parts = []

        # 1. System capabilities
        prompt_parts.append(capabilities_prompt)

        # 2. Conversation history (last 10 messages)
        if conversation_history:
            prompt_parts.append("\n## KONUŞMA GEÇMİŞİ\n")
            for msg in conversation_history[-10:]:
                if msg.get("is_user"):
                    prompt_parts.append(f"Kullanıcı: {msg['content']}\n")
                elif not msg.get("data_request"):  # Skip data request system messages
                    prompt_parts.append(f"Asistan: {msg['content']}\n")

        # 3. Collected data from previous requests (if any)
        if collected_data:
            prompt_parts.append("\n## TOPLANAN VERİLER\n")
            for idx, data_item in enumerate(collected_data, 1):
                request = data_item["request"]
                result = data_item["result"]

                prompt_parts.append(f"\n### Veri Talebi {idx}\n")
                prompt_parts.append(f"Kategori: {request.get('category')}\n")
                prompt_parts.append(f"Zaman Aralığı: {request.get('time_range')}\n")

                if result.get("error"):
                    prompt_parts.append(f"Hata: {result['error']}\n")
                else:
                    prompt_parts.append(f"Veri:\n{json.dumps(result.get('data'), indent=2, ensure_ascii=False)}\n")

        # 4. Current user message
        prompt_parts.append(f"\n## KULLANICI MESAJI\n\nKullanıcı: {user_message}\n")

        # 5. Instructions
        prompt_parts.append("\n## TALİMATLAR\n")

        if not collected_data:
            prompt_parts.append(
                "Kullanıcının sorusunu yanıtlamak için veriye ihtiyacın varsa, "
                "JSON formatında veri talebi yap. Yoksa doğrudan yanıt ver.\n"
            )
        else:
            prompt_parts.append(
                "Yukarıda toplanan verilerle kullanıcının sorusunu yanıtla. "
                "Daha fazla veriye ihtiyacın varsa başka bir JSON veri talebi yapabilirsin. "
                "Aksi takdirde analiz et ve yanıt ver.\n"
            )

        prompt_parts.append("\nAsistan:")

        return "".join(prompt_parts)

    def _build_final_prompt(
        self,
        user_message: str,
        collected_data: List[Dict]
    ) -> str:
        """
        Build final prompt when max data requests reached

        Args:
            user_message: Original user message
            collected_data: All collected data

        Returns:
            Final prompt string
        """
        prompt_parts = []

        prompt_parts.append("# KULLANICI SORUSU\n\n")
        prompt_parts.append(f"{user_message}\n\n")

        prompt_parts.append("# TOPLANAN VERİLER\n\n")

        for idx, data_item in enumerate(collected_data, 1):
            request = data_item["request"]
            result = data_item["result"]

            prompt_parts.append(f"## Veri Seti {idx}\n")
            prompt_parts.append(f"Kategori: {request.get('category')}\n")
            prompt_parts.append(f"Zaman Aralığı: {request.get('time_range')}\n\n")

            if result.get("error"):
                prompt_parts.append(f"Hata: {result['error']}\n\n")
            else:
                prompt_parts.append(f"```json\n{json.dumps(result.get('data'), indent=2, ensure_ascii=False)}\n```\n\n")

        prompt_parts.append("# TALİMAT\n\n")
        prompt_parts.append(
            "Yukarıdaki verileri kullanarak kullanıcının sorusunu yanıtla. "
            "Verileri analiz et, trendleri belirt, ve actionable öneriler sun. "
            "Türkçe, dostça ve profesyonel bir dille yanıt ver.\n\n"
        )

        prompt_parts.append("Asistan:")

        return "".join(prompt_parts)

    def quick_analysis(
        self,
        category: str,
        user_data: Dict[str, Any],
        time_range: str = "week",
        user_id: Optional[str] = None
    ) -> str:
        """
        Quick data analysis without full conversation

        Args:
            category: Data category (tasks, health, portfolio, etc.)
            user_data: User data
            time_range: Time range for analysis
            user_id: User ID for database queries

        Returns:
            Analysis result
        """
        # Create data request
        data_request = {
            "category": category,
            "time_range": time_range,
            "filters": {}
        }

        # Get data
        data_provider = AIDataProvider(user_data, user_id)
        data_result = data_provider.process_data_request(data_request)

        if data_result.get("error"):
            return f"Veri alınamadı: {data_result['error']}"

        # Build analysis prompt
        prompt = f"""Sen bir veri analisti asistanısın. Aşağıdaki veriyi analiz et ve özetini sun.

# VERİ KATEGORİSİ: {category.upper()}
# ZAMAN ARALIĞI: {time_range}

# VERİ:
```json
{json.dumps(data_result.get('data'), indent=2, ensure_ascii=False)}
```

# TALİMAT:
Bu veriyi analiz et ve kullanıcıya:
1. Kısa özet (2-3 cümle)
2. Önemli metrikler ve sayılar
3. Trendler (artış/azalış)
4. Actionable öneriler (2-3 madde)

Türkçe, açık ve anlaşılır şekilde yanıt ver.

Asistan:"""

        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Analiz hatası: {str(e)}"

    def analyze_portfolio(
        self,
        user_data: Dict[str, Any],
        user_question: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> str:
        """
        Portfolio-specific analysis (backward compatibility)

        Args:
            user_data: User data with portfolio info
            user_question: Optional specific question
            user_id: User ID

        Returns:
            Portfolio analysis
        """
        if user_question:
            # Use chat interface for questions
            response, _ = self.chat(
                user_message=user_question,
                user_data=user_data,
                user_id=user_id
            )
            return response
        else:
            # Use quick analysis
            return self.quick_analysis(
                category="portfolio",
                user_data=user_data,
                time_range="all",
                user_id=user_id
            )

    def financial_chat(
        self,
        message: str,
        user_data: Dict[str, Any],
        conversation_history: Optional[List[Dict]] = None,
        user_id: Optional[str] = None
    ) -> Tuple[str, List[Dict]]:
        """
        Financial chat (backward compatibility wrapper for chat)

        Args:
            message: User message
            user_data: User data
            conversation_history: Conversation history
            user_id: User ID

        Returns:
            Tuple of (response, updated history)
        """
        return self.chat(
            user_message=message,
            user_data=user_data,
            conversation_history=conversation_history,
            user_id=user_id
        )


# Export
__all__ = ['EnhancedGeminiService']


# Test function
if __name__ == "__main__":
    """Test the enhanced service"""

    # Mock user data
    user_data = {
        "tasks": [
            {
                "id": "1",
                "title": "Kod yazmayı bitir",
                "startDate": "2025-01-01T10:00:00Z",
                "endDate": "2025-01-05T18:00:00Z",
                "task": "in_progress",
                "project": "AI Assistant",
                "tag": "development",
                "notes": "Backend AI integration"
            }
        ],
        "health": [
            {
                "date": "2025-01-01T00:00:00Z",
                "caloriesBurned": 2500,
                "caloriesConsumed": 2000,
                "steps": 10000,
                "activeMinutes": 45
            }
        ],
        "portfolio": {
            "total_investment": 10000,
            "current_value": 10500,
            "total_profit_loss": 500,
            "profit_loss_percent": 5.0,
            "funds": []
        }
    }

    # Initialize service
    service = EnhancedGeminiService()

    # Test 1: Simple question
    print("=== Test 1: Simple Question ===")
    response, history = service.chat(
        user_message="Merhaba! Bugün görevlerime bakabilir misin?",
        user_data=user_data
    )
    print(f"Response: {response}\n")

    # Test 2: Quick analysis
    print("=== Test 2: Quick Analysis ===")
    analysis = service.quick_analysis(
        category="health",
        user_data=user_data,
        time_range="today"
    )
    print(f"Analysis: {analysis}\n")

    # Test 3: Portfolio analysis
    print("=== Test 3: Portfolio Analysis ===")
    portfolio_analysis = service.analyze_portfolio(
        user_data=user_data,
        user_question="Portföyüm nasıl gidiyor?"
    )
    print(f"Portfolio: {portfolio_analysis}\n")

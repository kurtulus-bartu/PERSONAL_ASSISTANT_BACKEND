import asyncio
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException
from supabase import Client, create_client

from .models import (
    FundDetail,
    StockDetail,
    FundPerformance,
    FundReference,
    PortfolioHistoryPoint,
    PortfolioHistoryResponse,
    PortfolioRange,
    PortfolioSummary,
)

TOTAL_FUND_CODE = "TOTAL"


class SupabaseService:
    """Supabase tablosu üzerinden portföy geçmişini yöneten servis."""

    def __init__(self, tefas_crawler):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        self.client: Optional[Client] = None
        self.tefas_crawler = tefas_crawler

        if self.url and self.key:
            self.client = create_client(self.url, self.key)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def record_portfolio_snapshot(self, user_id: str, summary: PortfolioSummary) -> None:
        """Portföy özetini günlük tabloya yazar."""
        if not self.client:
            return

        await asyncio.to_thread(self._record_snapshot_sync, user_id, summary)

    async def upsert_finance_metric_from_summary(
        self,
        user_id: str,
        summary: PortfolioSummary
    ) -> None:
        """Günlük finans metriklerini portföy özetinden günceller."""
        if not self.client:
            return

        await asyncio.to_thread(self._upsert_finance_metric_from_summary_sync, user_id, summary)

    async def get_portfolio_history(
        self,
        range_value: PortfolioRange,
        fund_code: Optional[str] = None
    ) -> PortfolioHistoryResponse:
        """İstenen zaman aralığı için tarihsel portföy verisini getirir."""
        start_date, end_date = self._resolve_range(range_value)
        selected_code = (fund_code or TOTAL_FUND_CODE).upper()

        if not self.client:
            # Supabase tanımlı değilse boş response dön
            return PortfolioHistoryResponse(
                range=range_value,
                fund_code=None if selected_code == TOTAL_FUND_CODE else selected_code,
                start_date=self._as_utc_datetime(start_date),
                end_date=self._as_utc_datetime(end_date),
                points=[],
                change_value=0,
                change_percent=0,
                available_funds=[],
                performances=[]
            )

        rows = await asyncio.to_thread(
            self._fetch_rows,
            start_date,
            end_date,
            selected_code
        )

        if not rows:
            # Veri yoksa boş liste dön (ancak available funds yine de gönder)
            funds = await asyncio.to_thread(self._get_available_funds)
            performances = await asyncio.to_thread(self._build_performance_cache)
            return PortfolioHistoryResponse(
                range=range_value,
                fund_code=None if selected_code == TOTAL_FUND_CODE else selected_code,
                start_date=self._as_utc_datetime(start_date),
                end_date=self._as_utc_datetime(end_date),
                points=[],
                change_value=0,
                change_percent=0,
                available_funds=funds,
                performances=performances
            )

        filled_rows = await asyncio.to_thread(
            self._ensure_continuous_rows,
            rows,
            start_date,
            end_date,
            selected_code
        )

        points = [
            PortfolioHistoryPoint(
                timestamp=self._as_utc_datetime(
                    datetime.fromisoformat(row["snapshot_date"]).date()
                ),
                total_value=row["current_value"],
                fund_code=row["fund_code"]
            )
            for row in filled_rows
        ]

        change_value, change_percent = self._calculate_change(points)

        funds = await asyncio.to_thread(self._get_available_funds)
        performances = await asyncio.to_thread(self._build_performance_cache)

        return PortfolioHistoryResponse(
            range=range_value,
            fund_code=None if selected_code == TOTAL_FUND_CODE else selected_code,
            start_date=self._as_utc_datetime(start_date),
            end_date=self._as_utc_datetime(end_date),
            points=points,
            change_value=change_value,
            change_percent=change_percent,
            available_funds=funds,
            performances=performances
        )

    # -------------------------------------------------------------------------
    # Snapshot Storage
    # -------------------------------------------------------------------------

    def _record_snapshot_sync(self, user_id: str, summary: PortfolioSummary) -> None:
        recorded_at = datetime.now(timezone.utc)
        snapshot_date = recorded_at.date().isoformat()

        # Fund rows
        fund_rows = [
            self._serialize_fund_row(
                user_id,
                fund,
                recorded_at,
                snapshot_date
            )
            for fund in summary.funds
        ]

        # Total portfolio row (in fund_daily_values)
        fund_rows.append({
            "user_id": user_id,
            "snapshot_date": snapshot_date,
            "recorded_at": recorded_at.isoformat(),
            "fund_code": TOTAL_FUND_CODE,
            "fund_name": "Toplam Portföy",
            "current_value": summary.current_value,
            "profit_loss": summary.total_profit_loss,
            "profit_loss_percent": summary.profit_loss_percent,
            "investment_amount": summary.total_investment,
            "units": None
        })

        # Stock rows
        stock_rows = [
            self._serialize_stock_row(
                user_id,
                stock,
                recorded_at,
                snapshot_date
            )
            for stock in summary.stocks
        ]

        # Save to respective tables
        self._upsert_rows(fund_rows)
        self._upsert_stock_rows(stock_rows)

    def _upsert_finance_metric_from_summary_sync(
        self,
        user_id: str,
        summary: PortfolioSummary
    ) -> None:
        metric_date = datetime.now(timezone.utc).date().isoformat()
        metric_id = str(uuid5(NAMESPACE_URL, f"{user_id}:finance_metrics:{metric_date}"))

        row = {
            "id": metric_id,
            "user_id": user_id,
            "date": metric_date,
            "total_investment": summary.total_investment,
            "current_value": summary.current_value,
            "profit_loss": summary.total_profit_loss,
            "profit_loss_percent": summary.profit_loss_percent
        }

        self.client.table("finance_metrics") \
            .upsert(row, on_conflict="user_id,date") \
            .execute()
        self._remove_duplicates("finance_metrics", ["date"], user_id)

    def _serialize_fund_row(
        self,
        user_id: str,
        fund: FundDetail,
        recorded_at: datetime,
        snapshot_date: str
    ) -> Dict:
        return {
            "user_id": user_id,
            "snapshot_date": snapshot_date,
            "recorded_at": recorded_at.isoformat(),
            "fund_code": fund.fund_code,
            "fund_name": fund.fund_name,
            "current_value": fund.current_value,
            "profit_loss": fund.profit_loss,
            "profit_loss_percent": fund.profit_loss_percent,
            "investment_amount": fund.investment_amount,
            "units": fund.units,
            "current_price": fund.current_price,
        }

    def _serialize_stock_row(
        self,
        user_id: str,
        stock: "StockDetail",
        recorded_at: datetime,
        snapshot_date: str
    ) -> Dict:
        return {
            "user_id": user_id,
            "snapshot_date": snapshot_date,
            "recorded_at": recorded_at.isoformat(),
            "symbol": stock.symbol,
            "stock_name": stock.stock_name,
            "current_value": stock.current_value,
            "profit_loss": stock.profit_loss,
            "profit_loss_percent": stock.profit_loss_percent,
            "investment_amount": stock.investment_amount,
            "units": stock.units,
            "current_price": stock.current_price,
            "currency": stock.currency,
        }

    def _upsert_rows(self, rows: List[Dict]) -> None:
        if not rows or not self.client:
            return
        try:
            self.client.table("fund_daily_values") \
                .upsert(rows, on_conflict="user_id,fund_code,snapshot_date") \
                .execute()
        except Exception as e:
            print(
                "Supabase snapshot warning: fund_daily_values table missing or unavailable. "
                "Run migration 011_add_fund_daily_values.sql. "
                f"Error: {str(e)}"
            )

    def _upsert_stock_rows(self, rows: List[Dict]) -> None:
        if not rows or not self.client:
            return

        self.client.table("stock_daily_values") \
            .upsert(rows, on_conflict="user_id,symbol,snapshot_date") \
            .execute()

    # -------------------------------------------------------------------------
    # History Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _resolve_range(range_value: PortfolioRange) -> (date, date):
        today = datetime.utcnow().date()
        days = {
            PortfolioRange.day: 1,
            PortfolioRange.week: 7,
            PortfolioRange.month: 30,
            PortfolioRange.year: 365
        }[range_value]

        start = today - timedelta(days=days - 1) if days > 1 else today
        return start, today

    @staticmethod
    def _as_utc_datetime(day: date) -> datetime:
        return datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)

    def _fetch_rows(
        self,
        start_date: date,
        end_date: date,
        fund_code: str
    ) -> List[Dict]:
        query = self.client.table("fund_daily_values") \
            .select("*") \
            .gte("snapshot_date", start_date.isoformat()) \
            .lte("snapshot_date", end_date.isoformat())

        if fund_code:
            query = query.eq("fund_code", fund_code)

        response = query.order("snapshot_date", desc=False).execute()
        return response.data or []

    def _ensure_continuous_rows(
        self,
        rows: List[Dict],
        start_date: date,
        end_date: date,
        fund_code: str
    ) -> List[Dict]:
        """İstenen tarih aralığında her gün için satır döndüğünden emin olur."""
        existing = {row["snapshot_date"]: row for row in rows}
        cursor = start_date
        ordered_rows = rows.copy()

        while cursor <= end_date:
            key = cursor.isoformat()
            if key not in existing:
                computed = self._backfill_day(fund_code, cursor)
                if computed:
                    existing[key] = computed
                    ordered_rows.append(computed)
            cursor += timedelta(days=1)

        ordered_rows.sort(key=lambda item: item["snapshot_date"])
        return ordered_rows

    def _backfill_day(self, fund_code: str, target_date: date) -> Optional[Dict]:
        """Eksik günler için TEFAS verisinden değer hesaplayıp kaydeder."""
        if fund_code == TOTAL_FUND_CODE:
            total_value = 0
            total_investment = 0
            for fund in self._get_distinct_funds():
                row = self._backfill_day(fund["fund_code"], target_date)
                if row:
                    total_value += row["current_value"]
                    total_investment += row.get("investment_amount", 0)

            if total_value == 0:
                return None

            payload = {
                "snapshot_date": target_date.isoformat(),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "fund_code": TOTAL_FUND_CODE,
                "fund_name": "Toplam Portföy",
                "current_value": round(total_value, 2),
                "investment_amount": round(total_investment, 2),
                "profit_loss": round(total_value - total_investment, 2),
                "profit_loss_percent": round(
                    ((total_value - total_investment) / total_investment * 100)
                    if total_investment else 0,
                    2
                ),
                "units": None
            }

            self._upsert_rows([payload])
            return payload

        latest_row = self._get_latest_row_for_fund(fund_code)
        if not latest_row:
            return None

        units = latest_row.get("units")
        if not units:
            return None

        investment_amount = latest_row.get("investment_amount", 0)
        fund_name = latest_row.get("fund_name")

        price_data = self.tefas_crawler.get_fund_price(
            fund_code,
            target_date.isoformat()
        )
        if not price_data or not price_data.get("price"):
            return None

        current_price = price_data["price"]
        current_value = round(units * current_price, 2)
        profit_loss = round(current_value - investment_amount, 2)
        profit_percent = round(
            (profit_loss / investment_amount * 100) if investment_amount else 0,
            2
        )

        payload = {
            "snapshot_date": target_date.isoformat(),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "fund_code": fund_code,
            "fund_name": fund_name,
            "current_value": current_value,
            "investment_amount": investment_amount,
            "profit_loss": profit_loss,
            "profit_loss_percent": profit_percent,
            "units": units
        }

        self._upsert_rows([payload])
        return payload

    def _get_distinct_funds(self) -> List[Dict]:
        response = self.client.table("fund_daily_values") \
            .select("fund_code,fund_name") \
            .neq("fund_code", TOTAL_FUND_CODE) \
            .execute()

        seen = {}
        for row in response.data or []:
            seen[row["fund_code"]] = row.get("fund_name")
        return [{"fund_code": code, "fund_name": name} for code, name in seen.items()]

    def _get_latest_row_for_fund(self, fund_code: str) -> Optional[Dict]:
        response = self.client.table("fund_daily_values") \
            .select("*") \
            .eq("fund_code", fund_code) \
            .order("snapshot_date", desc=True) \
            .limit(1) \
            .execute()

        if not response.data:
            return None
        return response.data[0]

    # -------------------------------------------------------------------------
    # Performance Builders
    # -------------------------------------------------------------------------

    def _get_available_funds(self) -> List[FundReference]:
        records = self._get_distinct_funds()
        references = [
            FundReference(fund_code=TOTAL_FUND_CODE, fund_name="Toplam Portföy")
        ]
        for row in records:
            references.append(FundReference(
                fund_code=row["fund_code"],
                fund_name=row.get("fund_name")
            ))
        return references

    def _build_performance_cache(self) -> List[FundPerformance]:
        response = self.client.table("fund_daily_values") \
            .select("*") \
            .neq("fund_code", TOTAL_FUND_CODE) \
            .order("snapshot_date", desc=False) \
            .execute()

        rows = response.data or []
        grouped: Dict[str, List[Dict]] = {}
        for row in rows:
            grouped.setdefault(row["fund_code"], []).append(row)

        today = datetime.utcnow().date()
        performances: List[FundPerformance] = []

        for code, items in grouped.items():
            latest = items[-1]
            latest_value = latest["current_value"]
            fund_name = latest.get("fund_name")

            def value_days_ago(days: int) -> float:
                target = today - timedelta(days=days)
                for entry in reversed(items):
                    entry_date = datetime.fromisoformat(entry["snapshot_date"]).date()
                    if entry_date <= target:
                        return entry["current_value"]
                return items[0]["current_value"]

            def change(days: int) -> float:
                past = value_days_ago(days)
                return round(latest_value - past, 2)

            performances.append(FundPerformance(
                fund_code=code,
                fund_name=fund_name,
                latest_value=latest_value,
                daily_change=change(1),
                weekly_change=change(7),
                monthly_change=change(30),
                yearly_change=change(365)
            ))

        return performances

    @staticmethod
    def _calculate_change(
        points: List[PortfolioHistoryPoint]
    ) -> (float, float):
        if len(points) < 2:
            return 0, 0

        start_value = points[0].total_value
        end_value = points[-1].total_value
        change_value = round(end_value - start_value, 2)
        change_percent = round(
            (change_value / start_value * 100) if start_value else 0,
            2
        )
        return change_value, change_percent

    # -------------------------------------------------------------------------
    # Backup & Restore Operations
    # -------------------------------------------------------------------------

    async def save_backup_data(self, user_id: str, data: Dict) -> None:
        """iOS'dan gelen backup verisini Supabase'e kaydeder"""
        if not self.client:
            raise Exception("Supabase client not initialized")

        await asyncio.to_thread(self._save_backup_sync, user_id, data)

    def _save_backup_sync(self, user_id: str, data: Dict) -> None:
        """Sync olarak backup verisini kaydeder"""

        # Fund Investments
        if "fundInvestments" in data:
            self._save_fund_investments(user_id, data["fundInvestments"])

        # Stock Investments
        if "stockInvestments" in data:
            self._save_stock_investments(user_id, data["stockInvestments"])

        # Budget Info
        if "budgetInfo" in data:
            self._save_budget_info(user_id, data["budgetInfo"])

        # Monthly Expenses
        if "monthlyExpenses" in data:
            self._save_monthly_expenses(user_id, data["monthlyExpenses"])

        if "healthEntries" in data:
            self._save_health_entries(user_id, data["healthEntries"])

        if "financeMetrics" in data:
            self._save_finance_metrics(user_id, data["financeMetrics"])

        # Tasks
        if "tasks" in data:
            self._save_tasks(user_id, data["tasks"])

        # Notes
        if "notes" in data:
            self._save_notes(user_id, data["notes"])

        # Pomodoro Sessions
        if "pomodoroSessions" in data:
            self._save_pomodoro_sessions(user_id, data["pomodoroSessions"])

        # Weight Entries
        if "weightEntries" in data:
            self._save_weight_entries(user_id, data["weightEntries"])

        # Sleep Entries
        if "sleepEntries" in data:
            self._save_sleep_entries(user_id, data["sleepEntries"])

        # Meal Entries
        if "mealEntries" in data:
            self._save_meal_entries(user_id, data["mealEntries"])

        # Workout Entries
        if "workoutEntries" in data:
            self._save_workout_entries(user_id, data["workoutEntries"])

        # Habits
        if "habits" in data:
            self._save_habits(user_id, data["habits"])

        # Habit Logs
        if "habitLogs" in data:
            self._save_habit_logs(user_id, data["habitLogs"])

    def has_ai_suggestions_for_date(
        self,
        user_id: str,
        target_date: str,
        suggestion_type: Optional[str] = None
    ) -> bool:
        """Belirli gün için öneri var mı kontrol eder"""
        if not self.client:
            return False

        try:
            query = self.client.table("ai_suggestions") \
                .select("id") \
                .eq("user_id", user_id) \
                .eq("metadata->>forDate", target_date)
            if suggestion_type:
                query = query.eq("type", suggestion_type)
            response = query.execute()
            return bool(response.data)
        except Exception:
            return False

    def save_ai_suggestions(
        self,
        user_id: str,
        suggestions: List[Dict],
        target_date: Optional[str] = None,
        source: str = "daily_suggestions"
    ) -> int:
        """AI önerilerini Supabase'e kaydeder"""
        if not self.client:
            raise Exception("Supabase client not initialized")

        rows = []
        seen_ids = set()
        timestamp = datetime.now(timezone.utc).isoformat()

        def normalize_placeholder(text: str) -> str:
            translation = str.maketrans({
                "ı": "i", "İ": "i",
                "ş": "s", "Ş": "s",
                "ğ": "g", "Ğ": "g",
                "ü": "u", "Ü": "u",
                "ö": "o", "Ö": "o",
                "ç": "c", "Ç": "c"
            })
            normalized = text.translate(translation).strip().lower()
            return re.sub(r"[^a-z0-9]+", "", normalized)

        def metadata_value(metadata: Dict[str, Any], keys: List[str]) -> Optional[str]:
            lowered_map = {str(k).lower(): k for k in metadata.keys()}
            for key in keys:
                real_key = lowered_map.get(key.lower(), key)
                value = metadata.get(real_key)
                if value is None:
                    continue
                value_str = str(value).strip()
                if value_str:
                    return value_str
            return None

        for suggestion in suggestions:
            suggestion_type = (suggestion.get("type") or "note").strip()
            description = (suggestion.get("description") or "").strip()
            if not description:
                continue

            metadata = suggestion.get("metadata") or {}
            normalized = normalize_placeholder(description)
            if normalized in {"aciklama", "description", "desc", "icerik", "content", "metin"}:
                fallback = None
                for key in [
                    "title",
                    "name",
                    "taskTitle",
                    "eventTitle",
                    "habitName",
                    "menu",
                    "menuItems",
                    "mealType",
                    "targetTitle",
                    "newValue",
                    "reason",
                    "content"
                ]:
                    candidate = metadata_value(metadata, [key])
                    if not candidate:
                        continue
                    normalized_candidate = normalize_placeholder(candidate)
                    if normalized_candidate in {"aciklama", "description", "desc", "icerik", "content", "metin"}:
                        continue
                    fallback = str(candidate).replace("|", " • ").strip()
                    if fallback:
                        break

                if fallback:
                    description = fallback
                else:
                    description = "AI onerisi"
            if target_date:
                metadata.setdefault("date", target_date)
                metadata.setdefault("forDate", target_date)
            metadata.setdefault("source", source)
            if description and not metadata.get("content"):
                metadata["content"] = description

            base_date = metadata.get("forDate") or metadata.get("date") or target_date
            seed_parts = [
                metadata.get("title") or metadata.get("name") or metadata.get("taskTitle") or metadata.get("eventTitle") or metadata.get("mealType") or "",
                metadata.get("time") or metadata.get("startTime") or "",
                metadata.get("date") or metadata.get("forDate") or "",
                metadata.get("menu") or metadata.get("menuItems") or "",
                description
            ]
            seed = "|".join([str(part).strip() for part in seed_parts if part is not None])
            seed = seed.strip() or description

            if base_date:
                suggestion_id = str(
                    uuid5(NAMESPACE_URL, f"{user_id}:{base_date}:{suggestion_type}:{seed}")
                )
            else:
                suggestion_id = str(uuid4())

            if suggestion_id in seen_ids:
                continue
            seen_ids.add(suggestion_id)

            rows.append({
                "id": suggestion_id,
                "user_id": user_id,
                "type": suggestion_type,
                "status": "pending",
                "metadata": metadata,
                "timestamp": timestamp
            })

        if rows:
            self.client.table("ai_suggestions").upsert(rows, on_conflict="id").execute()

        return len(rows)

    def save_meal_entries_from_suggestions(
        self,
        user_id: str,
        suggestions: List[Dict[str, Any]],
        existing_meals: Optional[List[Dict[str, Any]]] = None,
        target_date: Optional[str] = None
    ) -> int:
        """Meal-type AI suggestions -> meal_entries kayıtları."""
        if not self.client:
            raise Exception("Supabase client not initialized")

        existing_keys = set()
        for meal in (existing_meals or []):
            date_value = str(meal.get("date", ""))[:10]
            meal_type = str(meal.get("mealType", "")).strip().lower()
            description = str(meal.get("description", "")).strip().lower()
            if date_value and meal_type and description:
                existing_keys.add((date_value, meal_type, description))

        def parse_item_calories(text: str) -> Optional[float]:
            if not text:
                return None
            match = re.search(r"(\d{2,4})\s*kcal", text.lower())
            if match:
                return float(match.group(1))
            return None

        def split_menu_items(raw_value: str) -> List[str]:
            if not raw_value:
                return []
            normalized = (
                str(raw_value)
                .replace("•", "\n")
                .replace("|", "\n")
                .replace(";", "\n")
            )
            parts: List[str] = []
            for line in normalized.splitlines():
                parts.extend(line.split(","))

            cleaned: List[str] = []
            seen: Set[str] = set()
            for part in parts:
                item = re.sub(r"\s+", " ", str(part)).strip(" -•*")
                key = item.lower()
                if not item or key in seen:
                    continue
                seen.add(key)
                cleaned.append(item)
            return cleaned

        meal_entries: List[Dict[str, Any]] = []

        for suggestion in suggestions:
            suggestion_type = (suggestion.get("type") or "").strip().lower()
            if suggestion_type != "meal":
                continue

            metadata = suggestion.get("metadata") or {}
            meal_type = (metadata.get("mealType") or metadata.get("meal_type") or "").strip()
            date_value = (metadata.get("date") or target_date or "").strip()
            if not meal_type or not date_value:
                continue

            date_key = date_value[:10]
            raw_menu = metadata.get("menu") or metadata.get("menuItems") or ""
            menu_items = split_menu_items(str(raw_menu))
            if not menu_items:
                fallback_text = (
                    str(suggestion.get("description", "")).strip()
                    or str(metadata.get("title", "")).strip()
                )
                menu_items = split_menu_items(fallback_text)
                if not menu_items and fallback_text:
                    menu_items = [fallback_text]

            if not menu_items:
                continue

            metadata_total = 0.0
            if metadata.get("calories"):
                digits = re.sub(r"[^0-9.]", "", str(metadata.get("calories")))
                if digits:
                    metadata_total = float(digits)

            parsed_values = [parse_item_calories(item) for item in menu_items]
            parsed_total = sum([value for value in parsed_values if value is not None])
            fallback_per_item = 0.0
            if metadata_total > 0 and parsed_total <= 0:
                fallback_per_item = metadata_total / max(len(menu_items), 1)

            for index, item in enumerate(menu_items):
                clean_item = re.sub(r"\s+", " ", item).strip(" -•*")
                if not clean_item:
                    continue

                dedupe_key = (date_key, meal_type.lower(), clean_item.lower())
                if dedupe_key in existing_keys:
                    continue

                item_calories = parsed_values[index] if index < len(parsed_values) else None
                if item_calories is None and fallback_per_item > 0:
                    item_calories = fallback_per_item

                meal_entries.append({
                    "id": str(uuid4()),
                    "date": date_key,
                    "mealType": meal_type,
                    "description": clean_item,
                    "calories": float(item_calories or 0.0),
                    "notes": metadata.get("notes", "")
                })
                existing_keys.add(dedupe_key)

        if meal_entries:
            self._save_meal_entries(user_id, meal_entries)

        return len(meal_entries)

    def get_last_ai_suggestion_time(self, user_id: str) -> Optional[datetime]:
        """Kullanıcının en son AI önerisi zamanını döndürür"""
        if not self.client:
            return None

        try:
            response = self.client.table("ai_suggestions") \
                .select("timestamp") \
                .eq("user_id", user_id) \
                .order("timestamp", desc=True) \
                .limit(1) \
                .execute()

            if response.data and len(response.data) > 0:
                timestamp_str = response.data[0]["timestamp"]
                # Parse ISO format timestamp
                return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

            return None
        except Exception as e:
            print(f"Error getting last AI suggestion time: {str(e)}")
            return None

    def save_ai_memories(
        self,
        user_id: str,
        memories: List[Dict]
    ) -> int:
        """AI hafızalarını Supabase'e kaydeder"""
        if not self.client:
            raise Exception("Supabase client not initialized")

        rows = []
        timestamp = datetime.now(timezone.utc).isoformat()

        for memory in memories:
            content = (memory.get("content") or "").strip()
            if not content:
                continue

            category = (memory.get("category") or "general").strip()

            # Create unique ID based on content to avoid duplicates
            memory_id = str(uuid5(NAMESPACE_URL, f"{user_id}:{category}:{content}"))

            rows.append({
                "id": memory_id,
                "user_id": user_id,
                "content": content,
                "category": category,
                "timestamp": timestamp
            })

        if rows:
            self.client.table("ai_memory_items").upsert(rows, on_conflict="id").execute()

        return len(rows)

    def _save_fund_investments(self, user_id: str, investments: List[Dict]) -> None:
        """Fon yatırımlarını kaydet"""
        rows = [
            {
                "id": inv["id"],
                "user_id": user_id,
                "fund_code": inv["fundCode"],
                "fund_name": inv["fundName"],
                "investment_amount": inv["investmentAmount"],
                "purchase_price": inv["purchasePrice"],
                "purchase_date": inv["purchaseDate"],
                "units": inv["units"],
                "notes": inv["notes"]
            }
            for inv in investments
        ]

        if rows:
            self.client.table("fund_investments").upsert(rows, on_conflict="id").execute()

    def _save_stock_investments(self, user_id: str, investments: List[Dict]) -> None:
        """Hisse yatırımlarını kaydet"""
        rows = [
            {
                "id": inv["id"],
                "user_id": user_id,
                "symbol": inv["symbol"],
                "stock_name": inv.get("stockName", ""),
                "investment_amount": inv["investmentAmount"],
                "purchase_price": inv["purchasePrice"],
                "purchase_date": inv["purchaseDate"],
                "units": inv["units"],
                "currency": inv.get("currency", "USD"),
                "notes": inv.get("notes", "")
            }
            for inv in investments
        ]

        if rows:
            self.client.table("stock_investments").upsert(rows, on_conflict="id").execute()

    def _save_budget_info(self, user_id: str, budget: Dict) -> None:
        """Bütçe bilgisini kaydet"""
        row = {
            "user_id": user_id,
            "monthly_salary": budget["monthlySalary"],
            "total_investments": budget["totalInvestments"],
            "custom_expenses": budget["customExpenses"]
        }

        self.client.table("budget_info").upsert(row, on_conflict="user_id").execute()

    def _save_monthly_expenses(self, user_id: str, expenses: List[Dict]) -> None:
        """Aylık harcamaları kaydet"""
        rows = [
            {
                "id": exp["id"],
                "user_id": user_id,
                "month": exp["month"],
                "total_expense": exp["totalExpense"],
                "salary": exp["salary"],
                "investments": exp["investments"]
            }
            for exp in expenses
        ]

        if rows:
            self.client.table("monthly_expenses").upsert(rows, on_conflict="id").execute()

    def _save_finance_metrics(self, user_id: str, metrics: List[Dict]) -> None:
        """Günlük finans metriklerini kaydet"""
        rows = [
            {
                "id": metric["id"],
                "user_id": user_id,
                "date": metric["date"],
                "total_investment": metric.get("totalInvestment", 0),
                "current_value": metric.get("currentValue", 0),
                "profit_loss": metric.get("profitLoss", 0),
                "profit_loss_percent": metric.get("profitLossPercent", 0)
            }
            for metric in metrics
        ]

        if rows:
            self.client.table("finance_metrics").upsert(rows, on_conflict="user_id,date").execute()
            self._remove_duplicates("finance_metrics", ["date"], user_id)

    def _save_health_entries(self, user_id: str, entries: List[Dict]) -> None:
        """Sağlık kayıtlarını (günlük) kaydet"""
        if not entries:
            return

        latest_per_day: Dict[str, Dict] = {}
        for entry in entries:
            date_key = entry.get("date", "")[:10]
            if not date_key:
                continue
            latest_per_day[date_key] = entry

        rows = [
            {
                "id": entry["id"],
                "user_id": user_id,
                "date": entry["date"],
                "calories_burned": entry.get("caloriesBurned", 0),
                "calories_consumed": entry.get("caloriesConsumed", 0),
                "steps": entry.get("steps", 0),
                "active_minutes": entry.get("activeMinutes", 0)
            }
            for entry in latest_per_day.values()
        ]

        if rows:
            self.client.table("health_entries").upsert(rows, on_conflict="user_id,date").execute()
            self._remove_duplicates("health_entries", ["date"], user_id)

    def _save_tasks(self, user_id: str, tasks: List[Dict]) -> None:
        """Görevleri kaydet"""
        # TODO: Implement task saving
        pass

    def _save_notes(self, user_id: str, notes: List[Dict]) -> None:
        """Notları kaydet"""
        # TODO: Implement note saving
        pass

    def _save_pomodoro_sessions(self, user_id: str, sessions: List[Dict]) -> None:
        """Pomodoro oturumlarını kaydet"""
        # TODO: Implement pomodoro saving
        pass

    def _save_weight_entries(self, user_id: str, entries: List[Dict]) -> None:
        """Kilo kayıtlarını kaydet"""
        latest_per_day: Dict[str, Dict] = {}
        for entry in entries:
            date_key = str(entry.get("date", ""))[:10]
            if not date_key:
                continue
            latest_per_day[date_key] = entry

        rows = [
            {
                "id": entry["id"],
                "user_id": user_id,
                "date": entry["date"],
                "weight": entry["weight"],
                "body_fat": entry.get("bodyFat", 0),
                "muscle_mass": entry.get("muscleMass", 0),
                "bmi": entry.get("bmi", 0),
                "notes": entry.get("notes", "")
            }
            for entry in latest_per_day.values()
        ]

        if rows:
            self.client.table("weight_entries").upsert(rows, on_conflict="user_id,date").execute()
            self._remove_duplicates("weight_entries", ["date"], user_id)

    def _save_sleep_entries(self, user_id: str, entries: List[Dict]) -> None:
        """Uyku kayıtlarını kaydet"""
        latest_per_day: Dict[str, Dict] = {}
        for entry in entries:
            date_key = str(entry.get("date", ""))[:10]
            if not date_key:
                continue
            latest_per_day[date_key] = entry

        rows = [
            {
                "id": entry["id"],
                "user_id": user_id,
                "date": entry["date"],
                "bed_time": entry["bedTime"],
                "wake_time": entry["wakeTime"],
                "quality": entry["quality"],
                "notes": entry.get("notes", "")
            }
            for entry in latest_per_day.values()
        ]

        if rows:
            self.client.table("sleep_entries").upsert(rows, on_conflict="user_id,date").execute()
            self._remove_duplicates("sleep_entries", ["date"], user_id)

    def _save_meal_entries(self, user_id: str, entries: List[Dict]) -> None:
        """Yemek kayıtlarını kaydet"""
        rows = [
            {
                "id": entry["id"],
                "user_id": user_id,
                "date": entry["date"],
                "meal_type": entry["mealType"],
                "description": entry["description"],
                "calories": entry["calories"],
                "notes": entry.get("notes", "")
            }
            for entry in entries
        ]

        if rows:
            self.client.table("meal_entries").upsert(rows, on_conflict="id").execute()

    def _save_workout_entries(self, user_id: str, entries: List[Dict]) -> None:
        """Antrenman kayıtlarını kaydet"""
        rows = [
            {
                "id": entry["id"],
                "user_id": user_id,
                "date": entry["date"],
                "workout_type": entry["workoutType"],
                "duration": entry["duration"],
                "calories_burned": entry["caloriesBurned"],
                "notes": entry.get("notes", "")
            }
            for entry in entries
        ]

        if rows:
            self.client.table("workout_entries").upsert(rows, on_conflict="id").execute()
            self._remove_duplicates(
                "workout_entries",
                ["date", "workout_type", "duration", "calories_burned"],
                user_id
            )

            # Egzersizleri de kaydet (with advanced fields)
            for entry in entries:
                if "exercises" in entry:
                    exercise_rows = [
                        {
                            "id": ex["id"],
                            "workout_id": entry["id"],
                            "user_id": user_id,
                            "name": ex["name"],
                            "sets": ex["sets"],
                            "reps": ex["reps"],
                            "weight": ex["weight"],
                            "notes": ex.get("notes", ""),
                            # NEW FIELDS for advanced tracking
                            "muscle_group": ex.get("muscleGroup", ""),
                            "category": ex.get("category", ""),
                            "rest_seconds": ex.get("restSeconds", 90),
                            "tempo": ex.get("tempo", ""),
                            "rpe": ex.get("rpe", 0),
                            "distance": ex.get("distance", 0),
                            "duration": ex.get("duration", 0)
                        }
                    for ex in entry["exercises"]
                ]
                if exercise_rows:
                    self.client.table("exercises").upsert(exercise_rows, on_conflict="id").execute()

                    # Save setDetails array for each exercise
                    for ex in entry["exercises"]:
                        set_details = ex.get("setDetails", [])
                        if set_details:
                            # Delete existing set details for this exercise
                            self.client.table("exercise_set_details").delete().eq("exercise_id", ex["id"]).execute()

                            # Insert new set details
                            set_rows = [
                                {
                                    "id": str(set_detail["id"]),
                                    "user_id": user_id,
                                    "exercise_id": ex["id"],
                                    "set_number": set_detail["setNumber"],
                                    "reps": set_detail["reps"],
                                    "weight": set_detail["weight"],
                                    "rpe": set_detail.get("rpe", 0),
                                    "notes": set_detail.get("notes", ""),
                                    "completed": set_detail.get("completed", False)
                                }
                                for set_detail in set_details
                            ]

                            if set_rows:
                                self.client.table("exercise_set_details").insert(set_rows).execute()

    @staticmethod
    def _normalize_date_value(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        value_str = str(value)
        return value_str[:10] if value_str else None

    @staticmethod
    def _normalize_time_value(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.time().strftime("%H:%M:%S")
        value_str = str(value).strip()
        if not value_str:
            return None
        if "T" in value_str:
            try:
                cleaned = value_str.replace("Z", "+00:00")
                parsed = datetime.fromisoformat(cleaned)
                return parsed.time().strftime("%H:%M:%S")
            except Exception:
                return value_str
        return value_str

    def _save_habits(self, user_id: str, habits: List[Dict]) -> None:
        """Alışkanlıkları kaydet"""
        rows = []
        for habit in habits:
            habit_id = habit.get("id")
            if not habit_id:
                continue

            frequency = habit.get("frequency") or "daily"

            rows.append({
                "id": habit_id,
                "user_id": user_id,
                "name": habit.get("name", ""),
                "frequency": frequency,
                "weekdays": habit.get("weekdays"),
                "custom_interval": habit.get("customInterval") or habit.get("custom_interval"),
                "created_at": habit.get("createdAt") or habit.get("created_at")
            })

        if rows:
            self.client.table("habits").upsert(rows, on_conflict="id").execute()

    def _save_habit_logs(self, user_id: str, logs: List[Dict]) -> None:
        """Alışkanlık loglarını kaydet"""
        rows = []
        for log in logs:
            log_id = log.get("id")
            habit_id = log.get("habitId") or log.get("habit_id")
            if not log_id or not habit_id:
                continue

            date_value = self._normalize_date_value(log.get("date"))
            if not date_value:
                continue

            rows.append({
                "id": log_id,
                "user_id": user_id,
                "habit_id": habit_id,
                "date": date_value,
                "completed": log.get("completed", False),
                "timestamp": log.get("timestamp")
            })

        if rows:
            self.client.table("habit_logs").upsert(rows, on_conflict="id").execute()

    async def get_backup_data(self, user_id: str) -> Dict:
        """Supabase'den kullanıcının tüm verisini çeker"""
        if not self.client:
            raise Exception("Supabase client not initialized")

        return await asyncio.to_thread(self._get_backup_sync, user_id)

    def _get_backup_sync(self, user_id: str) -> Dict:
        """Sync olarak backup verisini getirir"""
        backup_data = {}

        # Fund Investments
        fund_investments = self.client.table("fund_investments") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()
        backup_data["fundInvestments"] = [
            {
                "id": row["id"],
                "fundCode": row["fund_code"],
                "fundName": row["fund_name"],
                "investmentAmount": row["investment_amount"],
                "purchasePrice": row["purchase_price"],
                "purchaseDate": row["purchase_date"],
                "units": row["units"],
                "notes": row["notes"]
            }
            for row in (fund_investments.data or [])
        ]

        # Stock Investments
        stock_investments = self.client.table("stock_investments") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()
        backup_data["stockInvestments"] = [
            {
                "id": row["id"],
                "symbol": row["symbol"],
                "stockName": row["stock_name"],
                "investmentAmount": row["investment_amount"],
                "purchasePrice": row["purchase_price"],
                "purchaseDate": row["purchase_date"],
                "units": row["units"],
                "currency": row.get("currency", "USD"),
                "notes": row.get("notes", "")
            }
            for row in (stock_investments.data or [])
        ]

        # Budget Info
        budget_info = self.client.table("budget_info") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()
        if budget_info.data:
            budget_data = budget_info.data[0]
            backup_data["budgetInfo"] = {
                "monthlySalary": budget_data["monthly_salary"],
                "totalInvestments": budget_data["total_investments"],
                "customExpenses": budget_data["custom_expenses"]
            }

        # Monthly Expenses
        monthly_expenses = self.client.table("monthly_expenses") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()
        backup_data["monthlyExpenses"] = [
            {
                "id": row["id"],
                "month": row["month"],
                "totalExpense": row["total_expense"],
                "salary": row["salary"],
                "investments": row["investments"]
            }
            for row in (monthly_expenses.data or [])
        ]

        # Tasks (planner events)
        tasks_response = self.client.table("tasks") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()
        backup_data["tasks"] = [
            {
                "id": row["id"],
                "title": row.get("title", ""),
                "startDate": row.get("start_date"),
                "endDate": row.get("end_date"),
                "color": row.get("color", ""),
                "notes": row.get("notes", ""),
                "tag": row.get("tag", ""),
                "project": row.get("project", ""),
                "task": row.get("task", ""),
                "assignedFriendIDs": row.get("assigned_friend_ids") or [],
                "parentID": row.get("parent_id"),
                "recurrence": (
                    row.get("recurrence")
                    if row.get("recurrence") is not None
                    else (
                        {
                            "frequency": row.get("recurrence_frequency", "none"),
                            "interval": row.get("recurrence_interval", 1),
                            "weekdays": row.get("recurrence_weekdays") or [],
                            "until": row.get("recurrence_until")
                        } if row.get("recurrence_frequency") else None
                    )
                )
            }
            for row in (tasks_response.data or [])
        ]

        # Notes
        notes_response = self.client.table("notes") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()
        backup_data["notes"] = [
            {
                "id": row["id"],
                "title": row.get("title", ""),
                "content": row.get("content", ""),
                "tags": row.get("tags", []) or [],
                "project": row.get("project", ""),
                "date": row.get("note_date") or row.get("date")
            }
            for row in (notes_response.data or [])
        ]

        # AI Memories (last 200)
        ai_memories_response = self.client.table("ai_memory_items") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("timestamp", desc=True) \
            .limit(200) \
            .execute()
        backup_data["aiMemories"] = [
            {
                "id": row["id"],
                "content": row.get("content", ""),
                "category": row.get("category", "general"),
                "timestamp": row.get("timestamp")
            }
            for row in (ai_memories_response.data or [])
        ]

        # AI Suggestions (last 300)
        ai_suggestions_response = self.client.table("ai_suggestions") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("timestamp", desc=True) \
            .limit(300) \
            .execute()
        backup_data["aiSuggestions"] = []

        def _normalize_placeholder_local(text: str) -> str:
            translation = str.maketrans({
                "ı": "i", "İ": "i",
                "ş": "s", "Ş": "s",
                "ğ": "g", "Ğ": "g",
                "ü": "u", "Ü": "u",
                "ö": "o", "Ö": "o",
                "ç": "c", "Ç": "c"
            })
            lowered = (text or "").translate(translation).strip().lower()
            return re.sub(r"[^a-z0-9]+", "", lowered)

        for row in (ai_suggestions_response.data or []):
            metadata = row.get("metadata") or {}
            description = (
                row.get("description")
                or metadata.get("content")
                or metadata.get("title")
                or metadata.get("name")
                or metadata.get("taskTitle")
                or metadata.get("eventTitle")
                or metadata.get("menu")
                or metadata.get("menuItems")
                or ""
            )
            normalized = _normalize_placeholder_local(str(description))
            if normalized in {"aciklama", "description", "desc", "icerik", "content", "metin"}:
                fallback = None
                for key in [
                    "title",
                    "name",
                    "taskTitle",
                    "eventTitle",
                    "menu",
                    "menuItems",
                    "mealType",
                    "newValue",
                    "reason"
                ]:
                    candidate = metadata.get(key)
                    if not candidate:
                        continue
                    normalized_candidate = _normalize_placeholder_local(str(candidate))
                    if normalized_candidate in {"aciklama", "description", "desc", "icerik", "content", "metin"}:
                        continue
                    fallback = str(candidate).replace("|", " • ").strip()
                    if fallback:
                        break
                description = fallback or "AI onerisi"
            backup_data["aiSuggestions"].append({
                "id": row["id"],
                "type": row.get("type", ""),
                "description": description,
                "status": row.get("status", ""),
                "metadata": metadata,
                "timestamp": row.get("timestamp")
            })

        # Habits
        habits_response = self.client.table("habits") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()
        backup_data["habits"] = [
            {
                "id": row["id"],
                "name": row.get("name", ""),
                "frequency": row.get("frequency", ""),
                "weekdays": row.get("weekdays", []) or [],
                "customInterval": row.get("custom_interval"),
                "createdAt": row.get("created_at")
            }
            for row in (habits_response.data or [])
        ]

        # Habit Logs (last 300)
        habit_logs_response = self.client.table("habit_logs") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("date", desc=True) \
            .limit(300) \
            .execute()
        backup_data["habitLogs"] = [
            {
                "id": row["id"],
                "habitId": row.get("habit_id"),
                "date": row.get("date"),
                "completed": row.get("completed", False),
                "timestamp": row.get("timestamp")
            }
            for row in (habit_logs_response.data or [])
        ]

        # Health Entries
        health_entries = self.client.table("health_entries") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()
        backup_data["healthEntries"] = [
            {
                "id": row["id"],
                "date": row["date"],
                "caloriesBurned": row.get("calories_burned", 0),
                "caloriesConsumed": row.get("calories_consumed", 0),
                "steps": row.get("steps", 0),
                "activeMinutes": row.get("active_minutes", 0)
            }
            for row in (health_entries.data or [])
        ]

        finance_metrics = self.client.table("finance_metrics") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("date", desc=False) \
            .execute()
        backup_data["financeMetrics"] = [
            {
                "id": row["id"],
                "date": row["date"],
                "totalInvestment": row.get("total_investment", 0),
                "currentValue": row.get("current_value", 0),
                "profitLoss": row.get("profit_loss", 0),
                "profitLossPercent": row.get("profit_loss_percent", 0)
            }
            for row in (finance_metrics.data or [])
        ]

        # Weight Entries
        weight_entries = self.client.table("weight_entries") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()
        backup_data["weightEntries"] = [
            {
                "id": row["id"],
                "date": row["date"],
                "weight": row["weight"],
                "bodyFat": row.get("body_fat", 0),
                "muscleMass": row.get("muscle_mass", 0),
                "bmi": row.get("bmi", 0),
                "notes": row.get("notes", "")
            }
            for row in (weight_entries.data or [])
        ]

        # Sleep Entries
        sleep_entries = self.client.table("sleep_entries") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()
        backup_data["sleepEntries"] = [
            {
                "id": row["id"],
                "date": row["date"],
                "bedTime": row["bed_time"],
                "wakeTime": row["wake_time"],
                "quality": row["quality"],
                "notes": row.get("notes", "")
            }
            for row in (sleep_entries.data or [])
        ]

        # Meal Entries
        meal_entries = self.client.table("meal_entries") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()
        backup_data["mealEntries"] = [
            {
                "id": row["id"],
                "date": row["date"],
                "mealType": row["meal_type"],
                "description": row["description"],
                "calories": row["calories"],
                "notes": row.get("notes", "")
            }
            for row in (meal_entries.data or [])
        ]

        # Workout Entries with Exercises
        workout_entries = self.client.table("workout_entries") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()

        # Fetch all exercises and set details at once for efficiency
        exercises_response = self.client.table("exercises") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()

        set_details_response = self.client.table("exercise_set_details") \
            .select("*") \
            .eq("user_id", user_id) \
            .execute()

        # Group set details by exercise_id
        set_details_by_exercise = {}
        for sd in (set_details_response.data or []):
            ex_id = sd["exercise_id"]
            if ex_id not in set_details_by_exercise:
                set_details_by_exercise[ex_id] = []
            set_details_by_exercise[ex_id].append({
                "id": sd["id"],
                "setNumber": sd["set_number"],
                "reps": sd["reps"],
                "weight": sd["weight"],
                "rpe": sd.get("rpe", 0),
                "notes": sd.get("notes", ""),
                "completed": sd.get("completed", False)
            })

        workouts_with_exercises = []
        for workout in (workout_entries.data or []):
            # Filter exercises for this workout
            workout_exercises = [
                ex for ex in (exercises_response.data or [])
                if ex["workout_id"] == workout["id"]
            ]

            workouts_with_exercises.append({
                "id": workout["id"],
                "date": workout["date"],
                "workoutType": workout["workout_type"],
                "duration": workout["duration"],
                "caloriesBurned": workout["calories_burned"],
                "notes": workout.get("notes", ""),
                "exercises": [
                    {
                        "id": ex["id"],
                        "name": ex["name"],
                        "sets": ex["sets"],
                        "reps": ex["reps"],
                        "weight": ex["weight"],
                        "notes": ex.get("notes", ""),
                        # NEW FIELDS for advanced tracking
                        "muscleGroup": ex.get("muscle_group", ""),
                        "category": ex.get("category", ""),
                        "restSeconds": ex.get("rest_seconds", 90),
                        "tempo": ex.get("tempo", ""),
                        "rpe": ex.get("rpe", 0),
                        "distance": ex.get("distance", 0),
                        "duration": ex.get("duration", 0),
                        "setDetails": set_details_by_exercise.get(ex["id"], [])
                    }
                    for ex in workout_exercises
                ]
            })

        backup_data["workoutEntries"] = workouts_with_exercises

        return backup_data

    def _remove_duplicates(self, table: str, fields: List[str], user_id: str) -> None:
        """Belirli alanlara göre duplicate kayıtları siler"""
        try:
            response = self.client.table(table) \
                .select(",".join(["id"] + fields)) \
                .eq("user_id", user_id) \
                .execute()
        except Exception:
            return

        rows = response.data or []
        seen = set()
        duplicates: List[str] = []

        for row in rows:
            key = tuple(row.get(field) for field in fields)
            if key in seen:
                duplicates.append(row["id"])
            else:
                seen.add(key)

        while duplicates:
            chunk = duplicates[:100]
            duplicates = duplicates[100:]
            self.client.table(table).delete().in_("id", chunk).execute()

    # -------------------------------------------------------------------------
    # Cron Job Support Methods
    # -------------------------------------------------------------------------

    def get_all_user_ids(self) -> List[str]:
        """Get all unique user IDs from database"""
        if not self.client:
            return []

        user_ids = set()
        tables = ["tasks", "notes", "meal_entries", "health_entries"]

        for table in tables:
            try:
                response = self.client.table(table).select("user_id").execute()
                for row in (response.data or []):
                    if row.get("user_id"):
                        user_ids.add(row["user_id"])
            except Exception as e:
                print(f"Error getting user IDs from {table}: {str(e)}")

        return list(user_ids)

    def get_user_data_for_ai(self, user_id: str) -> Dict[str, Any]:
        """Get user data for AI processing"""
        if not self.client:
            return {}

        try:
            data = {}

            # Get tasks and events
            events_response = self.client.table("planner_events").select("*").eq("user_id", user_id).execute()
            data["tasks"] = [e for e in events_response.data if e.get("is_task")]
            data["events"] = [e for e in events_response.data if not e.get("is_task")]

            # Get notes
            notes_response = self.client.table("notes").select("*").eq("user_id", user_id).execute()
            data["notes"] = notes_response.data

            # Get health entries
            health_response = self.client.table("health_entries").select("*").eq("user_id", user_id).execute()
            data["health_entries"] = health_response.data

            return data
        except Exception as e:
            print(f"Error getting user data for AI: {str(e)}")
            return {}

    def get_user_email_settings(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user email settings"""
        if not self.client:
            return None

        try:
            response = self.client.table("user_settings") \
                .select("value") \
                .eq("user_id", user_id) \
                .eq("key", "email_settings") \
                .execute()
            if response.data:
                return response.data[0].get("value", {})
            return None
        except Exception as e:
            print(f"Error getting user email settings: {str(e)}")
            return None

    def get_user_friends(self, user_id: str) -> List[Dict[str, Any]]:
        """Get user's friends list"""
        if not self.client:
            return []

        try:
            response = self.client.table("friends") \
                .select("id,name,email") \
                .eq("user_id", user_id) \
                .execute()
            return response.data or []
        except Exception as e:
            print(f"Error getting user friends: {str(e)}")
            return []

    def was_daily_summary_sent_today(self, user_id: str) -> bool:
        """Check if daily summary email was sent today"""
        if not self.client:
            return False

        try:
            today = datetime.now(timezone.utc).date()
            response = self.client.table("daily_summary_email_state") \
                .select("last_sent_at") \
                .eq("user_id", user_id) \
                .limit(1) \
                .execute()
            if not response.data:
                return False
            last_sent = response.data[0].get("last_sent_at")
            if not last_sent:
                return False
            last_sent_dt = datetime.fromisoformat(last_sent.replace("Z", "+00:00"))
            return last_sent_dt.date() == today
        except Exception as e:
            print(f"Error checking daily summary status: {str(e)}")
            return False

    def mark_daily_summary_sent(self, user_id: str):
        """Mark daily summary email as sent today"""
        if not self.client:
            return

        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            self.client.table("daily_summary_email_state") \
                .upsert({
                    "user_id": user_id,
                    "last_sent_at": now_iso,
                    "updated_at": now_iso
                }, on_conflict="user_id") \
                .execute()
        except Exception as e:
            print(f"Error marking daily summary as sent: {str(e)}")

    def get_user_tasks_for_period(
        self,
        user_id: str,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """Get user's tasks/events for a date range (by start_date)."""
        if not self.client:
            return []

        try:
            start_ts = datetime.combine(start_date, datetime.min.time()).isoformat()
            end_ts = datetime.combine(end_date, datetime.max.time()).isoformat()
            response = self.client.table("tasks") \
                .select("*") \
                .eq("user_id", user_id) \
                .gte("start_date", start_ts) \
                .lte("start_date", end_ts) \
                .execute()
            rows = response.data or []
            return [
                row for row in rows
                if str(row.get("task", "")).strip().lower() != "done"
            ]
        except Exception as e:
            print(f"Error getting user tasks for period: {str(e)}")
            return []

    def get_user_meals_for_period(
        self,
        user_id: str,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """Get user's meals for a date range."""
        if not self.client:
            return []

        try:
            start_ts = datetime.combine(start_date, datetime.min.time()).isoformat()
            end_ts = datetime.combine(end_date, datetime.max.time()).isoformat()
            response = self.client.table("meal_entries") \
                .select("*") \
                .eq("user_id", user_id) \
                .gte("date", start_ts) \
                .lte("date", end_ts) \
                .execute()
            return response.data or []
        except Exception as e:
            print(f"Error getting user meals for period: {str(e)}")
            return []

    # ============================================================================
    # FITNESS COACHING METHODS
    # ============================================================================

    def get_users_with_workouts(self) -> List[str]:
        """Get all user IDs who have workout entries"""
        if not self.client:
            return []

        try:
            # Get distinct user_ids from workout_entries table
            response = self.client.table("workout_entries").select("user_id").execute()
            user_ids = list(set([row["user_id"] for row in response.data if row.get("user_id")]))
            return user_ids
        except Exception as e:
            print(f"Error getting users with workouts: {str(e)}")
            return []

    def get_workouts_for_period(self, user_id: str, start_date, end_date) -> List[Dict]:
        """Get user's workouts for a specific period"""
        if not self.client:
            return []

        try:
            # Get workouts
            workouts_response = self.client.table("workout_entries")\
                .select("*")\
                .eq("user_id", user_id)\
                .gte("date", str(start_date))\
                .lte("date", str(end_date))\
                .order("date")\
                .execute()

            if not workouts_response.data:
                return []

            # Get exercises for these workouts
            workout_ids = [w["id"] for w in workouts_response.data]
            exercises_response = self.client.table("exercises")\
                .select("*")\
                .in_("workout_id", workout_ids)\
                .execute()

            # Group exercises by workout_id
            exercises_by_workout = {}
            for exercise in exercises_response.data:
                workout_id = exercise["workout_id"]
                if workout_id not in exercises_by_workout:
                    exercises_by_workout[workout_id] = []
                exercises_by_workout[workout_id].append({
                    "id": exercise["id"],
                    "name": exercise["name"],
                    "sets": exercise.get("sets", 0),
                    "reps": exercise.get("reps", 0),
                    "weight": exercise.get("weight", 0),
                    "notes": exercise.get("notes", ""),
                    "muscleGroup": exercise.get("muscle_group", ""),
                    "category": exercise.get("category", ""),
                    "restSeconds": exercise.get("rest_seconds", 90),
                    "rpe": exercise.get("rpe", 0),
                    "setDetails": []  # TODO: Add set details support
                })

            # Build complete workout objects
            workouts = []
            for workout in workouts_response.data:
                workouts.append({
                    "id": workout["id"],
                    "date": workout["date"],
                    "workoutType": workout.get("workout_type", ""),
                    "duration": workout.get("duration", 0),
                    "caloriesBurned": workout.get("calories_burned", 0),
                    "notes": workout.get("notes", ""),
                    "exercises": exercises_by_workout.get(workout["id"], [])
                })

            return workouts

        except Exception as e:
            print(f"Error getting workouts for period: {str(e)}")
            return []

    def get_latest_fitness_coaching(self, user_id: str) -> Optional[Dict]:
        """Get the most recent fitness coaching session for a user"""
        if not self.client:
            return None

        try:
            response = self.client.table("fitness_coaching_sessions")\
                .select("*")\
                .eq("user_id", user_id)\
                .order("week_start_date", desc=True)\
                .limit(1)\
                .execute()

            if response.data and len(response.data) > 0:
                return response.data[0]
            return None

        except Exception as e:
            print(f"Error getting latest fitness coaching: {str(e)}")
            return None

    def has_fitness_coaching_for_week(self, user_id: str, week_start_date: date) -> bool:
        """Check whether a coaching session already exists for given week."""
        if not self.client:
            return False

        try:
            response = self.client.table("fitness_coaching_sessions") \
                .select("id") \
                .eq("user_id", user_id) \
                .eq("week_start_date", str(week_start_date)) \
                .limit(1) \
                .execute()
            return bool(response.data)
        except Exception as e:
            print(f"Error checking weekly fitness coaching existence: {str(e)}")
            return False

    def save_fitness_coaching_session(self, session_data: Dict) -> bool:
        """Save a fitness coaching session"""
        if not self.client:
            return False

        try:
            # Prepare session data
            session_row = {
                "user_id": session_data["user_id"],
                "week_start_date": session_data["week_start_date"],
                "week_end_date": session_data["week_end_date"],
                "workouts_completed": session_data.get("workouts_completed", 0),
                "total_volume": session_data.get("total_volume", 0),
                "total_sets": session_data.get("total_sets", 0),
                "total_reps": session_data.get("total_reps", 0),
                "muscle_groups_trained": session_data.get("muscle_groups", {}),
                "rest_days": session_data.get("rest_days", 0),
                "avg_workout_duration": int(session_data.get("avg_duration", 0)),
                "avg_rpe": session_data.get("avg_rpe", 0),
                "weekly_summary": session_data.get("weekly_summary", ""),
                "strengths": session_data.get("strengths", []),
                "areas_for_improvement": session_data.get("areas_for_improvement", []),
                "motivation_message": session_data.get("motivation_message", ""),
                "next_week_program": session_data.get("next_week_program", {})
            }

            # Upsert (insert or update if exists)
            self.client.table("fitness_coaching_sessions") \
                .upsert(session_row, on_conflict="user_id,week_start_date") \
                .execute()

            return True

        except Exception as e:
            print(f"Error saving fitness coaching session: {str(e)}")
            return False

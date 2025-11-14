import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import HTTPException
from supabase import Client, create_client

from models import (
    FundDetail,
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

    async def record_portfolio_snapshot(self, summary: PortfolioSummary) -> None:
        """Portföy özetini günlük tabloya yazar."""
        if not self.client:
            return

        await asyncio.to_thread(self._record_snapshot_sync, summary)

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

    def _record_snapshot_sync(self, summary: PortfolioSummary) -> None:
        recorded_at = datetime.now(timezone.utc)
        snapshot_date = recorded_at.date().isoformat()

        rows = [
            self._serialize_fund_row(
                fund,
                recorded_at,
                snapshot_date
            )
            for fund in summary.funds
        ]

        # Toplam portföy satırı
        rows.append({
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

        self._upsert_rows(rows)

    def _serialize_fund_row(
        self,
        fund: FundDetail,
        recorded_at: datetime,
        snapshot_date: str
    ) -> Dict:
        return {
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

    def _upsert_rows(self, rows: List[Dict]) -> None:
        if not rows or not self.client:
            return

        self.client.table("fund_daily_values") \
            .upsert(rows, on_conflict="fund_code,snapshot_date") \
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

        # Budget Info
        if "budgetInfo" in data:
            self._save_budget_info(user_id, data["budgetInfo"])

        # Monthly Expenses
        if "monthlyExpenses" in data:
            self._save_monthly_expenses(user_id, data["monthlyExpenses"])

        if "healthEntries" in data:
            self._save_health_entries(user_id, data["healthEntries"])

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
            for entry in entries
        ]

        if rows:
            self.client.table("weight_entries").upsert(rows, on_conflict="id").execute()

    def _save_sleep_entries(self, user_id: str, entries: List[Dict]) -> None:
        """Uyku kayıtlarını kaydet"""
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
            for entry in entries
        ]

        if rows:
            self.client.table("sleep_entries").upsert(rows, on_conflict="id").execute()

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

            # Egzersizleri de kaydet
            for entry in entries:
                if "exercises" in entry:
                    exercise_rows = [
                        {
                            "id": ex["id"],
                            "workout_id": entry["id"],
                            "name": ex["name"],
                            "sets": ex["sets"],
                            "reps": ex["reps"],
                            "weight": ex["weight"],
                            "notes": ex.get("notes", "")
                        }
                        for ex in entry["exercises"]
                    ]
                    if exercise_rows:
                        self.client.table("exercises").upsert(exercise_rows, on_conflict="id").execute()

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

        workouts_with_exercises = []
        for workout in (workout_entries.data or []):
            exercises = self.client.table("exercises") \
                .select("*") \
                .eq("workout_id", workout["id"]) \
                .execute()

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
                        "notes": ex.get("notes", "")
                    }
                    for ex in (exercises.data or [])
                ]
            })

        backup_data["workoutEntries"] = workouts_with_exercises

        return backup_data

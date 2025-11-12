import asyncio
import os
from datetime import date, datetime, timedelta
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
                start_date=datetime.combine(start_date, datetime.min.time()),
                end_date=datetime.combine(end_date, datetime.min.time()),
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
                start_date=datetime.combine(start_date, datetime.min.time()),
                end_date=datetime.combine(end_date, datetime.min.time()),
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
                timestamp=datetime.combine(
                    datetime.fromisoformat(row["snapshot_date"]).date(),
                    datetime.min.time()
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
            start_date=datetime.combine(start_date, datetime.min.time()),
            end_date=datetime.combine(end_date, datetime.min.time()),
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
        recorded_at = datetime.utcnow()
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
                "recorded_at": datetime.utcnow().isoformat(),
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
            "recorded_at": datetime.utcnow().isoformat(),
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

"""
AI Data Provider
Provides filtered data to AI based on data requests
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from ai_capabilities import (
    DataCategory,
    TimeRange,
    calculate_date_range,
    validate_data_request
)


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None

    if isinstance(value, datetime):
        return _ensure_aware(value)

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        except ValueError:
            try:
                parsed = datetime.fromisoformat(f"{raw}-01")
            except ValueError:
                return None
        return _ensure_aware(parsed)

    if isinstance(value, dict) and 'seconds' in value:
        try:
            return datetime.fromtimestamp(value['seconds'], tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None

    return None


class AIDataProvider:
    """
    Provides filtered data to AI based on requests
    Works with user data from frontend and database
    """

    def __init__(self, user_data: Dict[str, Any], user_id: Optional[str] = None):
        """
        Initialize data provider

        Args:
            user_data: User data sent from frontend
            user_id: User ID for database queries (optional)
        """
        self.user_data = user_data
        self.user_id = user_id

    def process_data_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a data request from AI

        Args:
            request: Data request dictionary

        Returns:
            Dictionary containing requested data
        """
        # Validate request
        is_valid, error = validate_data_request(request)
        if not is_valid:
            return {
                "error": error,
                "data": None
            }

        category = request.get("category")
        time_range = request.get("time_range", "all")
        filters = request.get("filters", {})
        custom_range = request.get("custom_range")

        # Calculate date range
        start_date, end_date = calculate_date_range(time_range, custom_range)

        # Route to appropriate data provider
        if category == DataCategory.TASKS:
            data = self._get_tasks_data(start_date, end_date, filters)

        elif category == DataCategory.NOTES:
            data = self._get_notes_data(start_date, end_date, filters)

        elif category == DataCategory.HEALTH:
            data = self._get_health_data(start_date, end_date, filters)

        elif category == DataCategory.SLEEP:
            data = self._get_sleep_data(start_date, end_date, filters)

        elif category == DataCategory.WEIGHT:
            data = self._get_weight_data(start_date, end_date, filters)

        elif category == DataCategory.MEALS:
            data = self._get_meals_data(start_date, end_date, filters)

        elif category == DataCategory.WORKOUTS:
            data = self._get_workouts_data(start_date, end_date, filters)

        elif category == DataCategory.PORTFOLIO:
            data = self._get_portfolio_data(start_date, end_date, filters)

        elif category == DataCategory.GOALS:
            data = self._get_goals_data(filters)

        elif category == DataCategory.BUDGET:
            data = self._get_budget_data(start_date, end_date, filters)

        elif category == DataCategory.SALARY:
            data = self._get_salary_data(filters)

        elif category == DataCategory.FRIENDS:
            data = self._get_friends_data()

        else:
            data = {"error": f"Unknown category: {category}"}

        return {
            "category": category,
            "time_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "type": time_range
            },
            "filters": filters,
            "data": data,
            "count": len(data) if isinstance(data, list) else 1
        }

    def _filter_by_date(self, items: List[Dict], date_field: str, start_date: datetime, end_date: datetime) -> List[Dict]:
        """Filter items by date range"""
        start_date = _ensure_aware(start_date)
        end_date = _ensure_aware(end_date)
        filtered = []
        for item in items:
            if date_field in item:
                item_date = _parse_datetime(item[date_field])
                if not item_date:
                    continue

                if start_date <= item_date <= end_date:
                    filtered.append(item)
        return filtered

    def _get_tasks_data(self, start_date: datetime, end_date: datetime, filters: Dict) -> List[Dict]:
        """Get tasks data"""
        tasks = self.user_data.get("tasks", [])

        # Filter by date
        tasks = self._filter_by_date(tasks, "startDate", start_date, end_date)

        # Apply additional filters
        if "status" in filters:
            tasks = [t for t in tasks if t.get("task") == filters["status"]]

        if "project" in filters:
            tasks = [t for t in tasks if t.get("project") == filters["project"]]

        if "tag" in filters:
            tasks = [t for t in tasks if t.get("tag") == filters["tag"]]

        # Return simplified data
        return [
            {
                "id": t.get("id"),
                "title": t.get("title"),
                "start_date": t.get("startDate"),
                "end_date": t.get("endDate"),
                "status": t.get("task"),
                "project": t.get("project"),
                "tag": t.get("tag"),
                "notes": t.get("notes")
            }
            for t in tasks
        ]

    def _get_notes_data(self, start_date: datetime, end_date: datetime, filters: Dict) -> List[Dict]:
        """Get notes data"""
        notes = self.user_data.get("notes", [])

        # Filter by date
        notes = self._filter_by_date(notes, "date", start_date, end_date)

        # Apply filters
        if "tags" in filters:
            filter_tags = set(filters["tags"] if isinstance(filters["tags"], list) else [filters["tags"]])
            notes = [n for n in notes if any(tag in filter_tags for tag in n.get("tags", []))]

        if "project" in filters:
            notes = [n for n in notes if n.get("project") == filters["project"]]

        return [
            {
                "id": n.get("id"),
                "title": n.get("title"),
                "content": n.get("content"),
                "tags": n.get("tags", []),
                "project": n.get("project"),
                "date": n.get("date")
            }
            for n in notes
        ]

    def _get_health_data(self, start_date: datetime, end_date: datetime, filters: Dict) -> List[Dict]:
        """Get health data (steps, calories, active minutes)"""
        health = self.user_data.get("health", [])
        health = self._filter_by_date(health, "date", start_date, end_date)

        return [
            {
                "date": h.get("date"),
                "calories_burned": h.get("caloriesBurned"),
                "calories_consumed": h.get("caloriesConsumed"),
                "steps": h.get("steps"),
                "active_minutes": h.get("activeMinutes"),
                "calorie_deficit": h.get("caloriesBurned", 0) - h.get("caloriesConsumed", 0)
            }
            for h in health
        ]

    def _get_sleep_data(self, start_date: datetime, end_date: datetime, filters: Dict) -> List[Dict]:
        """Get sleep data"""
        sleep = self.user_data.get("sleep", [])
        sleep = self._filter_by_date(sleep, "date", start_date, end_date)

        # Filter by quality if specified
        if "quality" in filters:
            min_quality = filters.get("quality")
            sleep = [s for s in sleep if s.get("quality", 0) >= min_quality]

        return [
            {
                "date": s.get("date"),
                "bed_time": s.get("bedTime"),
                "wake_time": s.get("wakeTime"),
                "duration_hours": (datetime.fromisoformat(str(s.get("wakeTime")).replace('Z', '+00:00')) -
                                 datetime.fromisoformat(str(s.get("bedTime")).replace('Z', '+00:00'))).total_seconds() / 3600
                                 if s.get("wakeTime") and s.get("bedTime") else 0,
                "quality": s.get("quality"),
                "notes": s.get("notes")
            }
            for s in sleep
        ]

    def _get_weight_data(self, start_date: datetime, end_date: datetime, filters: Dict) -> List[Dict]:
        """Get weight data"""
        weight = self.user_data.get("weight", [])
        weight = self._filter_by_date(weight, "date", start_date, end_date)

        return [
            {
                "date": w.get("date"),
                "weight": w.get("weight"),
                "body_fat": w.get("bodyFat"),
                "muscle_mass": w.get("muscleMass"),
                "bmi": w.get("bmi"),
                "notes": w.get("notes")
            }
            for w in weight
        ]

    def _get_meals_data(self, start_date: datetime, end_date: datetime, filters: Dict) -> List[Dict]:
        """Get meals data"""
        meals = self.user_data.get("meals", [])
        meals = self._filter_by_date(meals, "date", start_date, end_date)

        # Filter by meal type
        if "meal_type" in filters:
            meals = [m for m in meals if m.get("mealType") == filters["meal_type"]]

        return [
            {
                "date": m.get("date"),
                "meal_type": m.get("mealType"),
                "description": m.get("description"),
                "calories": m.get("calories"),
                "notes": m.get("notes")
            }
            for m in meals
        ]

    def _get_workouts_data(self, start_date: datetime, end_date: datetime, filters: Dict) -> List[Dict]:
        """Get workouts data"""
        workouts = self.user_data.get("workouts", [])
        workouts = self._filter_by_date(workouts, "date", start_date, end_date)

        # Filter by workout type
        if "workout_type" in filters:
            workouts = [w for w in workouts if w.get("workoutType") == filters["workout_type"]]

        return [
            {
                "date": w.get("date"),
                "workout_type": w.get("workoutType"),
                "duration_minutes": w.get("duration"),
                "calories_burned": w.get("caloriesBurned"),
                "exercises": w.get("exercises", []),
                "notes": w.get("notes")
            }
            for w in workouts
        ]

    def _get_portfolio_data(self, start_date: datetime, end_date: datetime, filters: Dict) -> Dict:
        """Get portfolio data"""
        portfolio = self.user_data.get("portfolio", {})
        investments = self.user_data.get("investments", [])

        # Filter by fund code if specified
        if "fund_code" in filters:
            fund_code = filters["fund_code"].upper()
            investments = [inv for inv in investments if inv.get("fundCode", "").upper() == fund_code]

            # Also filter portfolio funds
            if "funds" in portfolio:
                portfolio["funds"] = [f for f in portfolio["funds"] if f.get("fund_code", "").upper() == fund_code]

        return {
            "summary": {
                "total_investment": portfolio.get("total_investment"),
                "current_value": portfolio.get("current_value"),
                "profit_loss": portfolio.get("total_profit_loss"),
                "profit_loss_percent": portfolio.get("profit_loss_percent"),
                "daily_change": portfolio.get("daily_change")
            },
            "investments": [
                {
                    "fund_code": inv.get("fundCode"),
                    "fund_name": inv.get("fundName"),
                    "investment_amount": inv.get("investmentAmount"),
                    "purchase_price": inv.get("purchasePrice"),
                    "purchase_date": inv.get("purchaseDate"),
                    "units": inv.get("units")
                }
                for inv in investments
            ],
            "funds": portfolio.get("funds", [])
        }

    def _get_goals_data(self, filters: Dict) -> List[Dict]:
        """Get financial goals data"""
        goals = self.user_data.get("goals", [])

        # Filter by category
        if "category" in filters:
            goals = [g for g in goals if g.get("category") == filters["category"]]

        # Filter by status (completed, in_progress, pending)
        if "status" in filters:
            status = filters["status"]
            if status == "completed":
                goals = [g for g in goals if g.get("currentAmount", 0) >= g.get("targetAmount", 0)]
            elif status == "in_progress":
                goals = [g for g in goals if 0 < g.get("currentAmount", 0) < g.get("targetAmount", 0)]
            elif status == "pending":
                goals = [g for g in goals if g.get("currentAmount", 0) == 0]

        return [
            {
                "id": g.get("id"),
                "title": g.get("title"),
                "target_amount": g.get("targetAmount"),
                "current_amount": g.get("currentAmount"),
                "deadline": g.get("deadline"),
                "category": g.get("category"),
                "progress_percent": (g.get("currentAmount", 0) / g.get("targetAmount", 1)) * 100,
                "order_index": g.get("orderIndex"),
                "notes": g.get("notes")
            }
            for g in goals
        ]

    def _get_budget_data(self, start_date: datetime, end_date: datetime, filters: Dict) -> Dict:
        """Get budget data"""
        budget = self.user_data.get("budget", {})
        monthly_expenses = self.user_data.get("monthly_expenses", [])

        # Filter expenses by date
        monthly_expenses = self._filter_by_date(monthly_expenses, "month", start_date, end_date)

        # Filter by specific month if provided
        if "month" in filters:
            month_filter = filters["month"]
            monthly_expenses = [e for e in monthly_expenses if month_filter in str(e.get("month", ""))]

        return {
            "current_budget": {
                "monthly_salary": budget.get("monthlySalary"),
                "total_investments": budget.get("totalInvestments"),
                "custom_expenses": budget.get("customExpenses"),
                "available_for_expenses": budget.get("monthlySalary", 0) - budget.get("totalInvestments", 0) - budget.get("customExpenses", 0)
            },
            "monthly_expenses": [
                {
                    "month": e.get("month"),
                    "total_expense": e.get("totalExpense"),
                    "salary": e.get("salary"),
                    "investments": e.get("investments")
                }
                for e in monthly_expenses
            ]
        }

    def _get_salary_data(self, filters: Dict) -> Dict:
        """Get salary data"""
        salary_config = self.user_data.get("salary_config", {})

        result = {
            "year": salary_config.get("year"),
            "base_salary": salary_config.get("baseSalary"),
            "total_yearly_income": salary_config.get("totalYearlyIncome"),
            "average_monthly_income": salary_config.get("averageMonthlyIncome"),
            "monthly_incomes": []
        }

        monthly_incomes = salary_config.get("monthlyIncomes", [])

        # Filter by year
        if "year" in filters:
            year = filters["year"]
            monthly_incomes = [m for m in monthly_incomes if m.get("year") == year]

        # Filter by month
        if "month" in filters:
            month = filters["month"]
            monthly_incomes = [m for m in monthly_incomes if m.get("month") == month]

        result["monthly_incomes"] = [
            {
                "month": m.get("month"),
                "year": m.get("year"),
                "base_salary": m.get("baseSalary"),
                "multiplier": m.get("multiplier"),
                "total_salary": m.get("totalSalary"),
                "extra_incomes": m.get("extraIncomes", []),
                "total_income": m.get("totalIncome")
            }
            for m in monthly_incomes
        ]

        return result

    def _get_friends_data(self) -> List[Dict]:
        """Get friends data"""
        friends = self.user_data.get("friends", [])

        return [
            {
                "id": f.get("id"),
                "name": f.get("name"),
                "email": f.get("email"),
                "added_at": f.get("addedAt")
            }
            for f in friends
        ]


# Export
__all__ = ['AIDataProvider']

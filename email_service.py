"""
Email Service for sending daily summaries and notifications
Supports both Resend (production) and SMTP (local development)
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any
from datetime import datetime
import os


class EmailService:
    """Service for sending emails via Resend or SMTP"""

    def __init__(self):
        # Resend configuration (preferred for production)
        self.resend_api_key = os.getenv("RESEND_API_KEY")

        # SMTP configuration (fallback for local development)
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.sender_email = os.getenv("SENDER_EMAIL")
        self.sender_password = os.getenv("SENDER_PASSWORD")

        # Determine which method to use
        self.use_resend = bool(self.resend_api_key)
        self.use_smtp = bool(self.sender_email and self.sender_password)
        self.is_configured = self.use_resend or self.use_smtp

        if self.use_resend:
            try:
                import resend
                resend.api_key = self.resend_api_key
                self.resend = resend
                print("✅ Email service configured with Resend")
            except ImportError:
                print("⚠️  Resend library not installed, falling back to SMTP")
                self.use_resend = False
        elif self.use_smtp:
            print("✅ Email service configured with SMTP")
        else:
            print("⚠️  Email service not configured")

    def send_daily_summary(
        self,
        recipient_email: str,
        recipient_name: str,
        user_name: str,
        tasks: List[Dict[str, Any]],
        date: str = None
    ) -> bool:
        """
        Send daily task summary email to a friend

        Args:
            recipient_email: Friend's email address
            recipient_name: Friend's name
            user_name: User's name
            tasks: List of tasks assigned to this friend
            date: Date string (defaults to today)

        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.is_configured:
            print("⚠️  Email service not configured. Set RESEND_API_KEY or SENDER_EMAIL/SENDER_PASSWORD.")
            return False

        if not tasks:
            # No tasks to send
            return True

        if date is None:
            date = datetime.now().strftime("%d.%m.%Y")

        # Create email content
        subject = f"📋 {user_name}'dan Görev ve Etkinlik Özeti - {date}"

        # Build HTML email body
        html_body = self._build_html_summary(
            recipient_name=recipient_name,
            user_name=user_name,
            tasks=tasks,
            date=date
        )

        # Send via Resend or SMTP
        if self.use_resend:
            return self._send_via_resend(recipient_email, subject, html_body)
        else:
            return self._send_via_smtp(recipient_email, subject, html_body)

    def _send_via_resend(self, recipient_email: str, subject: str, html_body: str) -> bool:
        """Send email via Resend API"""
        try:
            # Resend API call
            params = {
                "from": self.sender_email or "onboarding@resend.dev",
                "to": recipient_email,
                "subject": subject,
                "html": html_body
            }

            response = self.resend.Emails.send(params)

            # Resend returns the email object on success
            if response:
                print(f"✅ Email sent successfully to {recipient_email} via Resend (ID: {response.get('id', 'N/A')})")
                return True
            else:
                print(f"❌ Resend returned empty response")
                return False

        except Exception as e:
            print(f"❌ Failed to send email via Resend to {recipient_email}: {str(e)}")
            return False

    def _send_via_smtp(self, recipient_email: str, subject: str, html_body: str) -> bool:
        """Send email via SMTP"""
        try:
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = self.sender_email
            message["To"] = recipient_email

            html_part = MIMEText(html_body, "html")
            message.attach(html_part)

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(message)

            print(f"✅ Email sent successfully to {recipient_email} via SMTP")
            return True

        except Exception as e:
            print(f"❌ Failed to send email via SMTP to {recipient_email}: {str(e)}")
            return False

    def _build_html_summary(
        self,
        recipient_name: str,
        user_name: str,
        tasks: List[Dict[str, Any]],
        date: str
    ) -> str:
        """Build HTML email body"""

        # Separate events from tasks based on start/end time difference
        events = []  # Events have different start and end times
        task_items = []  # Tasks have same start and end times

        for item in tasks:
            start_str = item.get("startDate", "")
            end_str = item.get("endDate", "")

            try:
                if start_str and end_str:
                    from datetime import datetime
                    start = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                    end = datetime.fromisoformat(end_str.replace('Z', '+00:00'))

                    if start != end:
                        events.append(item)
                    else:
                        task_items.append(item)
                else:
                    task_items.append(item)
            except:
                task_items.append(item)

        # Categorize tasks by status (only for tasks, not events)
        todo_tasks = [t for t in task_items if t.get("task", "").lower() == "to do"]
        in_progress_tasks = [t for t in task_items if t.get("task", "").lower() == "in progress"]

        # Events don't have status categorization
        all_events = events

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    border-radius: 10px;
                    margin-bottom: 30px;
                }}
                .greeting {{
                    font-size: 24px;
                    font-weight: bold;
                    margin-bottom: 10px;
                }}
                .date {{
                    font-size: 14px;
                    opacity: 0.9;
                }}
                .section {{
                    margin-bottom: 30px;
                }}
                .section-title {{
                    font-size: 18px;
                    font-weight: bold;
                    margin-bottom: 15px;
                    padding-bottom: 10px;
                    border-bottom: 2px solid #f0f0f0;
                }}
                .task-list {{
                    list-style: none;
                    padding: 0;
                }}
                .task-item {{
                    background: #f8f9fa;
                    padding: 15px;
                    margin-bottom: 10px;
                    border-radius: 8px;
                    border-left: 4px solid #667eea;
                }}
                .task-title {{
                    font-weight: 600;
                    margin-bottom: 5px;
                }}
                .task-meta {{
                    font-size: 13px;
                    color: #666;
                }}
                .status-badge {{
                    display: inline-block;
                    padding: 3px 10px;
                    border-radius: 12px;
                    font-size: 12px;
                    font-weight: 500;
                    margin-right: 8px;
                }}
                .status-todo {{
                    background: #fef3c7;
                    color: #92400e;
                }}
                .status-progress {{
                    background: #dbeafe;
                    color: #1e40af;
                }}
                .status-done {{
                    background: #d1fae5;
                    color: #065f46;
                }}
                .footer {{
                    margin-top: 40px;
                    padding-top: 20px;
                    border-top: 1px solid #e5e7eb;
                    font-size: 13px;
                    color: #666;
                    text-align: center;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <div class="greeting">Merhaba {recipient_name}! 👋</div>
                <div class="date">{date} tarihli özet</div>
            </div>

            <p>{user_name}, sizinle paylaşmak istediği <strong>{len(all_events)} etkinlik</strong> ve <strong>{len(task_items)} görev</strong> var (bugünden itibaren):</p>
        """

        # Events section
        if all_events:
            html += f"""
            <div class="section">
                <div class="section-title">📅 Etkinlikler ({len(all_events)})</div>
                <ul class="task-list">
            """
            for event in all_events:
                html += self._format_task_html(event, "event")
            html += "</ul></div>"

        # To Do tasks
        if todo_tasks:
            html += f"""
            <div class="section">
                <div class="section-title">📌 Yapılacak Görevler ({len(todo_tasks)})</div>
                <ul class="task-list">
            """
            for task in todo_tasks:
                html += self._format_task_html(task, "task")
            html += "</ul></div>"

        # In Progress tasks
        if in_progress_tasks:
            html += f"""
            <div class="section">
                <div class="section-title">🚀 Devam Eden Görevler ({len(in_progress_tasks)})</div>
                <ul class="task-list">
            """
            for task in in_progress_tasks:
                html += self._format_task_html(task, "task")
            html += "</ul></div>"

        html += """
            <div class="footer">
                <p>Bu email Personal Assistant uygulaması tarafından otomatik olarak gönderilmiştir.</p>
                <p>🤖 Generated with Personal Assistant</p>
            </div>
        </body>
        </html>
        """

        return html

    def _format_task_html(self, task: Dict[str, Any], status_class: str) -> str:
        """Format a single task as HTML"""
        title = task.get("title", "Başlıksız Görev")
        notes = task.get("notes", "")
        tag = task.get("tag", "")
        project = task.get("project", "")

        # Format dates (başlangıç ve bitiş)
        start_date_str = task.get("startDate", "")
        end_date_str = task.get("endDate", "")

        formatted_date = ""
        try:
            if start_date_str:
                start_obj = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
                end_obj = None

                if end_date_str:
                    end_obj = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))

                # Etkinlik mi (başlangıç != bitiş) yoksa görev mi (başlangıç == bitiş)?
                if end_obj and start_obj != end_obj:
                    # Etkinlik: Hem başlangıç hem bitiş zamanlarını göster
                    start_formatted = start_obj.strftime("%d.%m.%Y %H:%M")
                    end_formatted = end_obj.strftime("%H:%M")

                    # Aynı gün mü?
                    if start_obj.date() == end_obj.date():
                        formatted_date = f"{start_formatted} - {end_formatted}"
                    else:
                        end_formatted = end_obj.strftime("%d.%m.%Y %H:%M")
                        formatted_date = f"{start_formatted} - {end_formatted}"
                else:
                    # Görev: Sadece başlangıç zamanı
                    formatted_date = start_obj.strftime("%d.%m.%Y %H:%M")
        except:
            # Hata durumunda string olarak göster
            formatted_date = start_date_str if start_date_str else ""

        # SADECE: Başlık, tarih ve notlar göster (status badge YOK)
        html = f"""
        <li class="task-item">
            <div class="task-title">{title}</div>
            <div class="task-meta">
        """

        # Tarih (varsa)
        if formatted_date:
            html += f'<span>📅 {formatted_date}</span>'

        # Tag (varsa)
        if tag:
            html += f' <span style="margin-left: 10px;">🏷️ {tag}</span>'

        # Project (varsa)
        if project:
            html += f' <span style="margin-left: 10px;">📁 {project}</span>'

        # NOTLAR: Her zaman göster (boş değilse)
        if notes and notes.strip():
            html += f'<br><span style="margin-top: 5px; display: block;">💬 {notes}</span>'

        html += """
            </div>
        </li>
        """

        return html

    def send_personal_summary(
        self,
        user_email: str,
        user_name: str,
        tasks: List[Dict[str, Any]],
        meals: List[Dict[str, Any]],
        date: str = None,
        health_data: Dict[str, Any] = None,
        finance_data: Dict[str, Any] = None,
        habits_data: List[Dict[str, Any]] = None,
        daily_score: Dict[str, Any] = None
    ) -> bool:
        """
        Send personal daily summary email to user

        Args:
            user_email: User's email address
            user_name: User's name
            tasks: List of tasks and events for today
            meals: List of meals for today
            date: Date string (defaults to today)
            health_data: Health metrics (sleep, steps, calories, etc.)
            finance_data: Finance data (investments, daily change)
            habits_data: Today's habits with completion status
            daily_score: Daily score breakdown

        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.is_configured:
            print("⚠️  Email service not configured.")
            return False

        if date is None:
            date = datetime.now().strftime("%d.%m.%Y")

        # Create email content - now "Günlük Özet" instead of "7 Günlük Özet"
        subject = f"☀️ Günlük Özet - {date}"

        # Build HTML email body with all widget data
        html_body = self._build_personal_summary_html(
            user_name=user_name,
            tasks=tasks,
            meals=meals,
            date=date,
            health_data=health_data,
            finance_data=finance_data,
            habits_data=habits_data,
            daily_score=daily_score
        )

        # Send via Resend or SMTP
        if self.use_resend:
            return self._send_via_resend(user_email, subject, html_body)
        else:
            return self._send_via_smtp(user_email, subject, html_body)

    def _build_personal_summary_html(
        self,
        user_name: str,
        tasks: List[Dict[str, Any]],
        meals: List[Dict[str, Any]],
        date: str,
        health_data: Dict[str, Any] = None,
        finance_data: Dict[str, Any] = None,
        habits_data: List[Dict[str, Any]] = None,
        daily_score: Dict[str, Any] = None
    ) -> str:
        """Build modern personal summary HTML email body with widget-inspired design"""

        # Separate events and tasks
        events = []
        task_items = []
        for item in tasks:
            is_task = item.get("is_task", True)
            if is_task:
                task_items.append(item)
            else:
                events.append(item)

        # Sort events by time
        events.sort(key=lambda x: x.get("start_time", "") or "")

        # Calculate stats
        total_tasks = len(task_items)
        total_events = len(events)
        total_meals = len(meals)
        total_calories = sum(m.get("calories", 0) for m in meals)

        # Group meals by type for widget layout
        def normalize_meal_type(value: str) -> str:
            lowered = value.lower()
            if "kahvalt" in lowered:
                return "Kahvaltı"
            if "öğle" in lowered or "ogle" in lowered:
                return "Öğle"
            if "akşam" in lowered or "aksam" in lowered:
                return "Akşam"
            if "atıştır" in lowered or "atis" in lowered:
                return "Atıştırmalık"
            return value or "Diğer"

        def split_meal_items(value: str) -> List[str]:
            cleaned = (value or "").strip()
            if not cleaned:
                return []
            if "|" in cleaned:
                return [item.strip(" -•*") for item in cleaned.split("|") if item.strip()]
            if "\n" in cleaned:
                return [item.strip(" -•*") for item in cleaned.splitlines() if item.strip()]
            return [cleaned]

        meal_groups: Dict[str, List[Dict[str, Any]]] = {}
        for meal in meals:
            meal_type = normalize_meal_type(str(meal.get("meal_type", "")).strip())
            meal_groups.setdefault(meal_type, []).append(meal)

        # Get health stats with defaults
        health = health_data or {}
        sleep_hours = health.get("sleep_hours", 0)
        steps = health.get("steps", 0)
        active_minutes = health.get("active_minutes", 0)
        calories_burned = health.get("calories_burned", 0)

        # Get finance stats with defaults
        finance = finance_data or {}
        total_invested = finance.get("total_invested", 0)
        daily_change = finance.get("daily_change", 0)
        daily_change_percent = finance.get("daily_change_percent", 0)

        # Get habits with defaults
        habits = habits_data or []
        completed_habits = sum(1 for h in habits if h.get("completed", False))
        total_habits = len(habits)

        # Get daily score with defaults
        score = daily_score or {}
        total_points = score.get("total_points", 0)
        task_points = score.get("task_points", 0)
        pomodoro_points = score.get("pomodoro_points", 0)
        health_points = score.get("health_points", 0)

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    line-height: 1.5;
                    color: #1a1a1a;
                    background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%);
                    padding: 20px;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    border-radius: 24px;
                    padding: 32px 28px;
                    margin-bottom: 16px;
                    color: white;
                    text-align: center;
                    box-shadow: 0 8px 32px rgba(102, 126, 234, 0.3);
                }}
                .header-greeting {{
                    font-size: 28px;
                    font-weight: 700;
                    margin-bottom: 8px;
                    letter-spacing: -0.5px;
                }}
                .header-date {{
                    font-size: 15px;
                    opacity: 0.9;
                    font-weight: 500;
                }}
                .header-subtitle {{
                    font-size: 14px;
                    opacity: 0.8;
                    margin-top: 12px;
                }}
                .widget-grid {{
                    display: grid;
                    grid-template-columns: repeat(2, 1fr);
                    gap: 12px;
                    margin-bottom: 16px;
                }}
                .widget {{
                    background: rgba(255, 255, 255, 0.85);
                    backdrop-filter: blur(20px);
                    -webkit-backdrop-filter: blur(20px);
                    border-radius: 20px;
                    padding: 20px;
                    box-shadow: 0 4px 24px rgba(0,0,0,0.06);
                    border: 1px solid rgba(255,255,255,0.8);
                }}
                .widget-wide {{
                    grid-column: span 2;
                }}
                .widget-title {{
                    font-size: 12px;
                    font-weight: 600;
                    color: #8e8e93;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    margin-bottom: 12px;
                }}
                .widget-value {{
                    font-size: 32px;
                    font-weight: 700;
                    color: #1a1a1a;
                    letter-spacing: -1px;
                }}
                .widget-value-small {{
                    font-size: 24px;
                }}
                .widget-subtitle {{
                    font-size: 13px;
                    color: #8e8e93;
                    margin-top: 4px;
                }}
                .widget-icon {{
                    font-size: 20px;
                    margin-right: 8px;
                }}
                .stat-row {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 8px 0;
                    border-bottom: 1px solid rgba(0,0,0,0.05);
                }}
                .stat-row:last-child {{
                    border-bottom: none;
                }}
                .stat-label {{
                    font-size: 14px;
                    color: #666;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }}
                .stat-value {{
                    font-size: 15px;
                    font-weight: 600;
                    color: #1a1a1a;
                }}
                .progress-bar {{
                    height: 6px;
                    background: rgba(0,0,0,0.08);
                    border-radius: 3px;
                    overflow: hidden;
                    margin-top: 8px;
                }}
                .progress-fill {{
                    height: 100%;
                    border-radius: 3px;
                    transition: width 0.3s ease;
                }}
                .progress-orange {{ background: linear-gradient(90deg, #ff9500, #ffcc00); }}
                .progress-blue {{ background: linear-gradient(90deg, #007aff, #5ac8fa); }}
                .progress-green {{ background: linear-gradient(90deg, #34c759, #30d158); }}
                .progress-purple {{ background: linear-gradient(90deg, #af52de, #bf5af2); }}
                .chip {{
                    display: inline-flex;
                    align-items: center;
                    padding: 6px 12px;
                    background: rgba(0,0,0,0.05);
                    border-radius: 20px;
                    font-size: 12px;
                    font-weight: 600;
                    margin-right: 8px;
                    margin-bottom: 8px;
                }}
                .chip-green {{ background: rgba(52, 199, 89, 0.15); color: #248a3d; }}
                .chip-blue {{ background: rgba(0, 122, 255, 0.15); color: #0066cc; }}
                .chip-orange {{ background: rgba(255, 149, 0, 0.15); color: #c93400; }}
                .chip-purple {{ background: rgba(175, 82, 222, 0.15); color: #8944ab; }}
                .event-item {{
                    display: flex;
                    align-items: flex-start;
                    padding: 14px 0;
                    border-bottom: 1px solid rgba(0,0,0,0.05);
                }}
                .event-grid {{
                    display: grid;
                    grid-template-columns: 70px 1fr;
                    gap: 10px 12px;
                    padding: 12px;
                    border-radius: 16px;
                    background: repeating-linear-gradient(
                        to bottom,
                        rgba(0,0,0,0.04) 0,
                        rgba(0,0,0,0.04) 1px,
                        transparent 1px,
                        transparent 28px
                    );
                }}
                .event-card {{
                    background: rgba(255, 255, 255, 0.8);
                    border-radius: 12px;
                    padding: 10px 12px;
                    border: 1px solid rgba(255,255,255,0.9);
                    box-shadow: 0 2px 10px rgba(0,0,0,0.04);
                }}
                .event-item:last-child {{
                    border-bottom: none;
                    padding-bottom: 0;
                }}
                .event-time {{
                    min-width: 70px;
                    font-size: 14px;
                    font-weight: 600;
                    color: #007aff;
                    text-align: right;
                }}
                .event-content {{
                    flex: 1;
                }}
                .event-title {{
                    font-size: 15px;
                    font-weight: 600;
                    color: #1a1a1a;
                    margin-bottom: 2px;
                }}
                .event-meta {{
                    font-size: 13px;
                    color: #8e8e93;
                }}
                .task-item {{
                    display: flex;
                    align-items: center;
                    padding: 12px 0;
                    border-bottom: 1px solid rgba(0,0,0,0.05);
                }}
                .task-item:last-child {{
                    border-bottom: none;
                    padding-bottom: 0;
                }}
                .task-checkbox {{
                    width: 22px;
                    height: 22px;
                    border: 2px solid #007aff;
                    border-radius: 6px;
                    margin-right: 12px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 12px;
                }}
                .task-checkbox-done {{
                    background: #34c759;
                    border-color: #34c759;
                    color: white;
                }}
                .task-title {{
                    font-size: 15px;
                    color: #1a1a1a;
                    flex: 1;
                }}
                .meal-item {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 12px 0;
                    border-bottom: 1px solid rgba(0,0,0,0.05);
                }}
                .meal-item:last-child {{
                    border-bottom: none;
                    padding-bottom: 0;
                }}
                .meal-type {{
                    font-size: 14px;
                    font-weight: 600;
                    color: #ff9500;
                    min-width: 80px;
                }}
                .meal-desc {{
                    font-size: 14px;
                    color: #1a1a1a;
                    flex: 1;
                    margin: 0 12px;
                }}
                .meal-calories {{
                    font-size: 13px;
                    font-weight: 600;
                    color: #8e8e93;
                    white-space: nowrap;
                }}
                .meal-grid {{
                    display: grid;
                    grid-template-columns: repeat(3, 1fr);
                    gap: 12px;
                }}
                .meal-card {{
                    background: rgba(255, 255, 255, 0.8);
                    border-radius: 16px;
                    padding: 14px;
                    border: 1px solid rgba(255,255,255,0.9);
                    box-shadow: 0 3px 12px rgba(0,0,0,0.06);
                }}
                .meal-card-title {{
                    font-size: 13px;
                    font-weight: 700;
                    color: #ff9500;
                    margin-bottom: 8px;
                }}
                .meal-list {{
                    list-style: none;
                    padding: 0;
                    margin: 0;
                }}
                .meal-list-item {{
                    font-size: 13px;
                    color: #1a1a1a;
                    padding: 6px 0;
                    border-bottom: 1px dashed rgba(0,0,0,0.08);
                }}
                .meal-list-item:last-child {{
                    border-bottom: none;
                    padding-bottom: 0;
                }}
                .meal-card-foot {{
                    margin-top: 10px;
                    font-size: 12px;
                    font-weight: 600;
                    color: #8e8e93;
                }}
                .habit-item {{
                    display: flex;
                    align-items: center;
                    padding: 10px 0;
                    border-bottom: 1px solid rgba(0,0,0,0.05);
                }}
                .habit-item:last-child {{
                    border-bottom: none;
                }}
                .habit-status {{
                    width: 24px;
                    height: 24px;
                    border-radius: 12px;
                    margin-right: 12px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 14px;
                }}
                .habit-done {{ background: #34c759; color: white; }}
                .habit-pending {{ background: rgba(0,0,0,0.08); color: #8e8e93; }}
                .habit-name {{
                    font-size: 14px;
                    color: #1a1a1a;
                }}
                .empty-state {{
                    text-align: center;
                    padding: 24px;
                    color: #8e8e93;
                    font-size: 14px;
                }}
                .footer {{
                    text-align: center;
                    padding: 24px;
                    color: #8e8e93;
                    font-size: 12px;
                }}
                .footer-brand {{
                    font-weight: 600;
                    color: #667eea;
                }}
                .positive {{ color: #34c759; }}
                .negative {{ color: #ff3b30; }}
                @media (max-width: 480px) {{
                    .widget-grid {{
                        grid-template-columns: 1fr;
                    }}
                    .widget-wide {{
                        grid-column: span 1;
                    }}
                    .meal-grid {{
                        grid-template-columns: 1fr;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <!-- Header -->
                <div class="header">
                    <div class="header-greeting">Günaydın {user_name}! ☀️</div>
                    <div class="header-date">{date}</div>
                    <div class="header-subtitle">İşte bugünün özeti</div>
                </div>

                <!-- Widget Grid -->
                <div class="widget-grid">
        """

        # Daily Score Widget (if available)
        if total_points > 0:
            progress_percent = min(100, (total_points / 100) * 100)
            html += f"""
                    <div class="widget">
                        <div class="widget-title">⭐ Günlük Skor</div>
                        <div class="widget-value">{total_points}</div>
                        <div class="widget-subtitle">puan</div>
                        <div class="progress-bar">
                            <div class="progress-fill progress-orange" style="width: {progress_percent}%"></div>
                        </div>
                        <div style="margin-top: 12px;">
                            <span class="chip chip-green">Görev +{task_points}</span>
                            <span class="chip chip-blue">Odak +{pomodoro_points}</span>
                            <span class="chip chip-orange">Sağlık +{health_points}</span>
                        </div>
                    </div>
            """

        # Health Summary Widget
        if sleep_hours > 0 or steps > 0 or active_minutes > 0:
            html += f"""
                    <div class="widget">
                        <div class="widget-title">❤️ Sağlık</div>
                        <div class="stat-row">
                            <span class="stat-label">🛏️ Uyku</span>
                            <span class="stat-value">{sleep_hours:.1f} saat</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">👟 Adım</span>
                            <span class="stat-value">{steps:,}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">⚡ Aktif</span>
                            <span class="stat-value">{active_minutes} dk</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">🔥 Yakılan</span>
                            <span class="stat-value">{calories_burned} kcal</span>
                        </div>
                    </div>
            """

        # Finance Widget
        if total_invested > 0:
            change_class = "positive" if daily_change >= 0 else "negative"
            change_sign = "+" if daily_change >= 0 else ""
            html += f"""
                    <div class="widget">
                        <div class="widget-title">📈 Yatırımlar</div>
                        <div class="widget-value widget-value-small">₺{total_invested:,.0f}</div>
                        <div class="widget-subtitle">toplam yatırım</div>
                        <div style="margin-top: 8px;">
                            <span class="{change_class}" style="font-weight: 600;">
                                {change_sign}₺{abs(daily_change):,.0f} ({change_sign}{daily_change_percent:.1f}%)
                            </span>
                            <span style="color: #8e8e93; font-size: 12px;"> düne göre</span>
                        </div>
                    </div>
            """

        # Habits Widget
        if total_habits > 0:
            habits_progress = (completed_habits / total_habits) * 100 if total_habits > 0 else 0
            html += f"""
                    <div class="widget">
                        <div class="widget-title">✅ Alışkanlıklar</div>
                        <div class="widget-value">{completed_habits}/{total_habits}</div>
                        <div class="widget-subtitle">tamamlandı</div>
                        <div class="progress-bar">
                            <div class="progress-fill progress-green" style="width: {habits_progress}%"></div>
                        </div>
            """
            for habit in habits[:4]:
                status_class = "habit-done" if habit.get("completed") else "habit-pending"
                status_icon = "✓" if habit.get("completed") else "○"
                html += f"""
                        <div class="habit-item">
                            <div class="habit-status {status_class}">{status_icon}</div>
                            <span class="habit-name">{habit.get('name', '')}</span>
                        </div>
                """
            html += "</div>"

        # Day Planner Widget (Events + Tasks)
        html += """
                    <div class="widget widget-wide">
                        <div class="widget-title">📅 Bugünün Programı</div>
        """

        if events or task_items:
            # Events first (time-based)
            if events:
                html += '<div class="event-grid">'
                for event in events[:5]:
                    title = event.get("title", "Etkinlik")
                    start_time = event.get("start_time", "")
                    end_time = event.get("end_time", "")
                    tag = event.get("tag", "")
                    time_display = start_time[:5] if start_time else "--:--"
                    if end_time and start_time != end_time:
                        time_display += f"-{end_time[:5]}"

                    html += f"""
                        <div class="event-time">{time_display}</div>
                        <div class="event-card">
                            <div class="event-title">{title}</div>
                    """
                    if tag:
                        html += f'<div class="event-meta">🏷️ {tag}</div>'
                    html += """
                        </div>
                    """
                html += '</div>'

            # Tasks
            if task_items:
                html += '<div>'
                for task in task_items[:6]:
                    title = task.get("title", "Görev")
                    status = task.get("status", "To Do")
                    is_done = status.lower() == "done"
                    checkbox_class = "task-checkbox-done" if is_done else ""
                    checkbox_icon = "✓" if is_done else ""

                    html += f"""
                        <div class="task-item">
                            <div class="task-checkbox {checkbox_class}">{checkbox_icon}</div>
                            <span class="task-title">{title}</span>
                        </div>
                    """
                html += '</div>'

            if len(events) > 5:
                html += f'<div style="text-align: center; color: #8e8e93; font-size: 13px; margin-top: 8px;">+{len(events) - 5} etkinlik daha</div>'
            if len(task_items) > 6:
                html += f'<div style="text-align: center; color: #8e8e93; font-size: 13px; margin-top: 8px;">+{len(task_items) - 6} görev daha</div>'
        else:
            html += '<div class="empty-state">Bugün için planlanmış görev veya etkinlik yok 🎉</div>'

        html += "</div>"

        # Meals Widget
        if meals:
            html += """
                    <div class="widget widget-wide">
                        <div class="widget-title">🍽️ Günlük Menü</div>
                        <div class="meal-grid">
            """
            meal_order = ["Kahvaltı", "Öğle", "Akşam", "Atıştırmalık", "Diğer"]
            for meal_type in meal_order:
                group = meal_groups.get(meal_type, [])
                if not group:
                    continue

                items: List[str] = []
                meal_calories = 0.0
                for meal in group:
                    description = str(meal.get("description", "")).strip()
                    items.extend(split_meal_items(description))
                    try:
                        meal_calories += float(meal.get("calories", 0) or 0)
                    except (TypeError, ValueError):
                        pass

                if not items:
                    items = ["Planlanmadı"]

                items_html = "".join(
                    f'<li class="meal-list-item">{item}</li>' for item in items
                )
                calories_html = (
                    f'<div class="meal-card-foot">{int(meal_calories)} kcal</div>'
                    if meal_calories > 0 else ""
                )

                html += f"""
                        <div class="meal-card">
                            <div class="meal-card-title">{meal_type}</div>
                            <ul class="meal-list">
                                {items_html}
                            </ul>
                            {calories_html}
                        </div>
                """

            html += """
                        </div>
            """

            if total_calories > 0:
                html += f"""
                        <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(0,0,0,0.05);">
                            <span style="font-size: 14px; color: #8e8e93;">Toplam:</span>
                            <span style="font-size: 16px; font-weight: 700; color: #ff9500; margin-left: 8px;">🔥 {int(total_calories)} kcal</span>
                        </div>
                """

            html += """
                    </div>
            """

        # Close widget grid
        html += """
                </div>

                <!-- Footer -->
                <div class="footer">
                    <p>Bu e-posta <span class="footer-brand">Personal Assistant</span> tarafından otomatik olarak gönderilmiştir.</p>
                    <p style="margin-top: 8px;">🤖 AI-Powered Personal Assistant</p>
                </div>
            </div>
        </body>
        </html>
        """

        return html


# Singleton instance
email_service = EmailService()

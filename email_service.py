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
        date: str = None
    ) -> bool:
        """
        Send personal daily summary email to user

        Args:
            user_email: User's email address
            user_name: User's name
            tasks: List of tasks and events for today
            meals: List of meals for today
            date: Date string (defaults to today)

        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.is_configured:
            print("⚠️  Email service not configured.")
            return False

        if date is None:
            date = datetime.now().strftime("%d.%m.%Y")

        # Create email content
        subject = f"📆 7 Günlük Özet - {date}"

        # Build HTML email body
        html_body = self._build_personal_summary_html(
            user_name=user_name,
            tasks=tasks,
            meals=meals,
            date=date
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
        date: str
    ) -> str:
        """Build personal summary HTML email body"""

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    background-color: white;
                    border-radius: 12px;
                    padding: 30px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }}
                .header {{
                    text-align: center;
                    padding-bottom: 20px;
                    border-bottom: 2px solid #f0f0f0;
                    margin-bottom: 30px;
                }}
                .header h1 {{
                    margin: 0;
                    color: #2c3e50;
                    font-size: 28px;
                }}
                .greeting {{
                    font-size: 18px;
                    color: #555;
                    margin-top: 10px;
                }}
                .section {{
                    margin: 25px 0;
                }}
                .section-title {{
                    font-size: 20px;
                    font-weight: 600;
                    color: #2c3e50;
                    margin-bottom: 15px;
                    display: flex;
                    align-items: center;
                }}
                .section-title .icon {{
                    margin-right: 8px;
                    font-size: 24px;
                }}
                .item-list {{
                    list-style: none;
                    padding: 0;
                    margin: 0;
                }}
                .item {{
                    background-color: #f8f9fa;
                    border-left: 4px solid #3498db;
                    padding: 15px;
                    margin-bottom: 12px;
                    border-radius: 6px;
                }}
                .item.task {{
                    border-left-color: #3498db;
                }}
                .item.event {{
                    border-left-color: #9b59b6;
                }}
                .item.meal {{
                    border-left-color: #e74c3c;
                }}
                .item-title {{
                    font-weight: 600;
                    font-size: 16px;
                    color: #2c3e50;
                    margin-bottom: 5px;
                }}
                .item-details {{
                    font-size: 14px;
                    color: #666;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 2px solid #f0f0f0;
                    color: #999;
                    font-size: 13px;
                }}
                .empty {{
                    text-align: center;
                    color: #999;
                    font-style: italic;
                    padding: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🌅 Günlük Özet</h1>
                    <div class="greeting">Merhaba {user_name}! İşte bugünün planı:</div>
                    <div style="margin-top: 10px; color: #888; font-size: 14px;">{date}</div>
                </div>
        """

        # Görevler ve Etkinlikler
        html += """
                <div class="section">
                    <div class="section-title">
                        <span class="icon">📋</span>
                        Görevler ve Etkinlikler
                    </div>
        """

        if tasks:
            html += '<ul class="item-list">'
            for task in tasks:
                is_task = task.get("is_task", True)
                item_type = "task" if is_task else "event"
                title = task.get("title", "Başlıksız")
                notes = task.get("notes", "")
                display_time = task.get("start_time", "")
                time_str = ""

                if display_time:
                    time_str = f" • {display_time}" if not is_task else ""

                html += f'''
                    <li class="item {item_type}">
                        <div class="item-title">{"✓" if is_task else "📅"} {title}{time_str}</div>
                '''

                if display_time and is_task:
                    html += f'<div class="item-details">📅 {display_time}</div>'

                if notes:
                    html += f'<div class="item-details">{notes}</div>'

                html += '</li>'

            html += '</ul>'
        else:
            html += '<div class="empty">Bu dönem için görev veya etkinlik yok</div>'

        html += '</div>'

        # Yemekler
        html += """
                <div class="section">
                    <div class="section-title">
                        <span class="icon">🍽️</span>
                        Günlük Menü
                    </div>
        """

        if meals:
            html += '<ul class="item-list">'
            for meal in meals:
                meal_type = meal.get("meal_type", "Yemek")
                description = meal.get("description", "")
                calories = meal.get("calories", 0)
                meal_date = meal.get("meal_date", "")

                html += f'''
                    <li class="item meal">
                        <div class="item-title">{meal_type}</div>
                        <div class="item-details">{description}</div>
                '''

                if meal_date:
                    html += f'<div class="item-details" style="margin-top: 5px;">📅 {meal_date}</div>'

                if calories > 0:
                    html += f'<div class="item-details" style="margin-top: 5px;">🔥 {calories} kcal</div>'

                html += '</li>'

            html += '</ul>'
        else:
            html += '<div class="empty">Bu dönem için yemek kaydı yok</div>'

        html += '</div>'

        # Footer
        html += """
                <div class="footer">
                    Bu e-posta Personal Assistant uygulamanız tarafından otomatik olarak gönderilmiştir.
                </div>
            </div>
        </body>
        </html>
        """

        return html


# Singleton instance
email_service = EmailService()

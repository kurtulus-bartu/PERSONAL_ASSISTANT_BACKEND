"""
Email Service for sending daily summaries and notifications
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any
from datetime import datetime
import os


class EmailService:
    """Service for sending emails"""

    def __init__(self):
        # Email configuration from environment variables
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.sender_email = os.getenv("SENDER_EMAIL")
        self.sender_password = os.getenv("SENDER_PASSWORD")
        self.is_configured = bool(self.sender_email and self.sender_password)

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
            print("⚠️  Email service not configured. Set SENDER_EMAIL and SENDER_PASSWORD environment variables.")
            return False

        if not tasks:
            # No tasks to send
            return True

        if date is None:
            date = datetime.now().strftime("%d.%m.%Y")

        # Create email content
        subject = f"📋 {user_name}'dan Günlük Görev Özeti - {date}"

        # Build HTML email body
        html_body = self._build_html_summary(
            recipient_name=recipient_name,
            user_name=user_name,
            tasks=tasks,
            date=date
        )

        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = self.sender_email
        message["To"] = recipient_email

        # Add HTML part
        html_part = MIMEText(html_body, "html")
        message.attach(html_part)

        # Send email
        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(message)

            print(f"✅ Email sent successfully to {recipient_email}")
            return True

        except Exception as e:
            print(f"❌ Failed to send email to {recipient_email}: {str(e)}")
            return False

    def _build_html_summary(
        self,
        recipient_name: str,
        user_name: str,
        tasks: List[Dict[str, Any]],
        date: str
    ) -> str:
        """Build HTML email body"""

        # Categorize tasks by status
        todo_tasks = [t for t in tasks if t.get("task", "").lower() == "to do"]
        in_progress_tasks = [t for t in tasks if t.get("task", "").lower() == "in progress"]
        done_tasks = [t for t in tasks if t.get("task", "").lower() == "done"]

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
                <div class="date">{date} tarihli görev özeti</div>
            </div>

            <p>{user_name}, sizinle paylaşmak istediği {len(tasks)} görevi var:</p>
        """

        # To Do tasks
        if todo_tasks:
            html += f"""
            <div class="section">
                <div class="section-title">📌 Yapılacak ({len(todo_tasks)})</div>
                <ul class="task-list">
            """
            for task in todo_tasks:
                html += self._format_task_html(task, "todo")
            html += "</ul></div>"

        # In Progress tasks
        if in_progress_tasks:
            html += f"""
            <div class="section">
                <div class="section-title">🚀 Devam Eden ({len(in_progress_tasks)})</div>
                <ul class="task-list">
            """
            for task in in_progress_tasks:
                html += self._format_task_html(task, "progress")
            html += "</ul></div>"

        # Done tasks
        if done_tasks:
            html += f"""
            <div class="section">
                <div class="section-title">✅ Tamamlanan ({len(done_tasks)})</div>
                <ul class="task-list">
            """
            for task in done_tasks:
                html += self._format_task_html(task, "done")
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

        # Format task date
        start_date = task.get("startDate", "")
        if isinstance(start_date, str):
            try:
                # Try to parse and format the date
                date_obj = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                formatted_date = date_obj.strftime("%d.%m.%Y %H:%M")
            except:
                formatted_date = start_date
        else:
            formatted_date = ""

        status_labels = {
            "todo": "Yapılacak",
            "progress": "Devam Ediyor",
            "done": "Tamamlandı"
        }

        html = f"""
        <li class="task-item">
            <div class="task-title">{title}</div>
            <div class="task-meta">
                <span class="status-badge status-{status_class}">{status_labels.get(status_class, "")}</span>
        """

        if formatted_date:
            html += f'<span>📅 {formatted_date}</span>'

        if tag:
            html += f' <span>🏷️ {tag}</span>'

        if project:
            html += f' <span>📁 {project}</span>'

        if notes:
            html += f'<br><span style="margin-top: 5px; display: block;">💬 {notes}</span>'

        html += """
            </div>
        </li>
        """

        return html


# Singleton instance
email_service = EmailService()

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sys

project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.append(project_root)

from .logger import logger
from src.config.config import get_config

class EmailSender:
    def __init__(self):
        try:
            config = get_config()
            self.email_config = config.EMAIL_CONFIG
        except Exception as e:
            logger.error(f"初始化邮件发送器失败: {str(e)}")
            raise
        
    def send_email(self, subject, body, to_emails):
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_config['from_email']
            msg['To'] = ', '.join(to_emails)
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP_SSL(
                self.email_config['smtp_server'], 
                self.email_config['smtp_port']
            ) as server:
                server.login(
                    self.email_config['from_email'],
                    self.email_config['password']
                )
                server.send_message(msg)
            logger.info(f"邮件发送成功: {subject}")
        except Exception as e:
            logger.error(f"发送邮件失败: {str(e)}")
            raise
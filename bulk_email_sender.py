#!/usr/bin/env python3
"""
Bulk Email Sender Script

This script reads email addresses from CSV files and sends bulk emails for program outreach.
Supports various CSV formats and includes error handling, logging, and rate limiting.

Requirements:
- Install required packages: pip install pandas
- Configure your email settings in the script
- Ensure less secure app access is enabled for Gmail (or use app passwords)

Author: Ishmum Zaman
Date: 2024
"""

import smtplib
import ssl
import csv
import pandas as pd
import time
import logging
import os
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Dict, Optional
from datetime import datetime
import glob
import random

class BulkEmailSender:
    def __init__(self):
        """Initialize the bulk email sender with default configurations."""
        
        # Email Configuration - Load from environment variables or use defaults
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.sender_email = os.getenv("SENDER_EMAIL", "your_email@gmail.com")
        self.sender_password = os.getenv("SENDER_PASSWORD", "your_app_password")
        self.sender_name = os.getenv("SENDER_NAME", "Your Name")
        
        # Rate limiting and batch settings
        self.delay_between_emails = 1  # Base delay between emails
        self.batch_size = 50  # Emails per batch
        self.batch_delay = 10  # Seconds to wait between batches
        self.daily_limit = 450  # Gmail's safe daily limit
        
        # Retry settings
        self.max_retries = 3
        self.retry_delay_base = 5  # Base delay for exponential backoff
        
        # Setup logging
        self.setup_logging()
        
        # Email statistics
        self.stats = {
            'total_emails': 0,
            'successful_sends': 0,
            'failed_sends': 0,
            'invalid_emails': 0,
            'retries': 0,
            'emails_sent_today': 0
        }
        
        # SMTP connection reuse
        self.smtp_connection = None
    
    def setup_logging(self):
        """Setup logging configuration."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(f'email_log_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def create_smtp_connection(self):
        """Create and return an authenticated SMTP connection."""
        try:
            context = ssl.create_default_context()
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls(context=context)
            server.login(self.sender_email, self.sender_password)
            self.logger.info("SMTP connection established successfully")
            return server
        except Exception as e:
            self.logger.error(f"Failed to create SMTP connection: {str(e)}")
            return None
    
    def ensure_smtp_connection(self):
        """Ensure we have a valid SMTP connection."""
        if self.smtp_connection is None:
            self.smtp_connection = self.create_smtp_connection()
        return self.smtp_connection is not None
    
    def close_smtp_connection(self):
        """Close the SMTP connection if it exists."""
        if self.smtp_connection:
            try:
                self.smtp_connection.quit()
                self.logger.info("SMTP connection closed")
            except Exception as e:
                self.logger.warning(f"Error closing SMTP connection: {str(e)}")
            finally:
                self.smtp_connection = None
    
    def check_daily_limit(self):
        """Check if we're approaching the daily sending limit."""
        if self.stats['emails_sent_today'] >= self.daily_limit:
            self.logger.warning(f"Daily limit of {self.daily_limit} emails reached!")
            return False
        
        remaining = self.daily_limit - self.stats['emails_sent_today']
        if remaining <= 50:  # Warn when close to limit
            self.logger.warning(f"Only {remaining} emails remaining in daily limit")
        
        return True
    
    def validate_email(self, email: str) -> bool:
        """
        Validate email address format.
        
        Args:
            email (str): Email address to validate
            
        Returns:
            bool: True if email is valid, False otherwise
        """
        if not email or not isinstance(email, str):
            return False
        
        email = email.strip()
        if not email:
            return False
            
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    def read_emails_from_csv(self, file_path: str) -> List[str]:
        """
        Read email addresses from a CSV file.
        
        Args:
            file_path (str): Path to the CSV file
            
        Returns:
            List[str]: List of valid email addresses
        """
        emails = []
        
        try:
            # Try to read with pandas first for better handling
            df = pd.read_csv(file_path, header=None)
            
            # Extract emails from the first column
            for index, row in df.iterrows():
                if not row.empty and pd.notna(row.iloc[0]):
                    potential_email = str(row.iloc[0]).strip()
                    
                    # Skip empty rows and header-like content
                    if potential_email and potential_email.lower() not in ['email address', 'email']:
                        if self.validate_email(potential_email):
                            emails.append(potential_email)
                        else:
                            self.logger.warning(f"Invalid email format: {potential_email}")
                            self.stats['invalid_emails'] += 1
            
            self.logger.info(f"Successfully read {len(emails)} valid emails from {file_path}")
            
        except Exception as e:
            self.logger.error(f"Error reading CSV file {file_path}: {str(e)}")
            
            # Fallback to basic CSV reader
            try:
                with open(file_path, 'r', newline='', encoding='utf-8') as file:
                    csv_reader = csv.reader(file)
                    for row in csv_reader:
                        if row and len(row) > 0:
                            potential_email = row[0].strip()
                            if potential_email and potential_email.lower() not in ['email address', 'email']:
                                if self.validate_email(potential_email):
                                    emails.append(potential_email)
                                else:
                                    self.logger.warning(f"Invalid email format: {potential_email}")
                                    self.stats['invalid_emails'] += 1
                                    
                self.logger.info(f"Fallback: Successfully read {len(emails)} valid emails from {file_path}")
                
            except Exception as e2:
                self.logger.error(f"Failed to read CSV file {file_path} with fallback method: {str(e2)}")
        
        return emails
    
    def read_emails_from_multiple_csvs(self, file_pattern: str = "*.csv") -> List[str]:
        """
        Read email addresses from multiple CSV files.
        
        Args:
            file_pattern (str): File pattern to match CSV files
            
        Returns:
            List[str]: List of unique valid email addresses
        """
        all_emails = []
        csv_files = glob.glob(file_pattern)
        
        if not csv_files:
            self.logger.warning(f"No CSV files found matching pattern: {file_pattern}")
            return []
        
        self.logger.info(f"Found {len(csv_files)} CSV files to process")
        
        for file_path in csv_files:
            self.logger.info(f"Processing file: {file_path}")
            emails = self.read_emails_from_csv(file_path)
            all_emails.extend(emails)
        
        # Remove duplicates while preserving order
        unique_emails = list(dict.fromkeys(all_emails))
        
        self.logger.info(f"Total unique emails collected: {len(unique_emails)}")
        self.logger.info(f"Duplicate emails removed: {len(all_emails) - len(unique_emails)}")
        
        return unique_emails
    
    def create_email_content(self, recipient_email: str, custom_data: Dict = None) -> tuple:
        """
        Create email content (subject and body).
        Customize this method to fit your program outreach needs.
        
        Args:
            recipient_email (str): Recipient's email address
            custom_data (Dict): Additional data for personalization
            
        Returns:
            tuple: (subject, body_text, body_html)
        """
        
        # Email subject
        subject = "Career Development Program - Applications Now Open"
        
        # Email body (text version)
        body_text = f"""
Dear Student,

I hope this message finds you well. I'm reaching out to share an opportunity that may align with your career goals.

Our Career Development Program (Fall 2025 Cohort) is now accepting applications through [Application Deadline].

This program is designed for students who are interested in building skills and exploring opportunities in technology, finance, and consulting sectors.

Why consider this program?
Founded to help students from diverse educational backgrounds break into competitive industries and build meaningful careers.

In our recent cohorts, we've achieved:
✅ Placed students at leading companies
💰 Helped participants secure competitive offers
🌐 Built a network of students and industry mentors

Program highlights:
📚 Skills development workshops and training
📝 Application support and career guidance
🤝 Networking opportunities with industry professionals

How to get involved:
1. Learn more about our program
2. Apply by [Application Deadline]
3. Join our information sessions

We've helped students from universities nationwide. We'd love to support your career journey as well.

[Organization Name]
[Organization Type]
[Mission Statement]
Application Link: [Website URL]
Contact: [Contact Information]

---
This email was sent to {recipient_email}. If you received this email by mistake or wish to unsubscribe, please reply with "UNSUBSCRIBE" in the subject line.
        """
        
        # Email body (HTML version)
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c3e50;">Career Development Program - Applications Now Open</h2>
                
                <p>Dear Student,</p>
                
                <p>I hope this message finds you well. I'm reaching out to share an opportunity that may align with your career goals.</p>
                
                <div style="background-color: #e8f5e8; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #28a745;">
                    <p style="margin: 0; font-weight: bold; color: #28a745;">
                        Our Career Development Program (Fall 2025 Cohort) is now accepting applications through [Application Deadline].
                    </p>
                </div>
                
                <p>This program is designed for students who are interested in building skills and exploring opportunities in <strong>technology, finance, and consulting</strong> sectors.</p>
                
                <h3 style="color: #2c3e50;">Why consider this program?</h3>
                <p>Founded to help students from diverse educational backgrounds break into competitive industries and build meaningful careers.</p>
                
                <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="color: #2c3e50; margin-top: 0;">In our recent cohorts, we've achieved:</h3>
                    <ul style="list-style: none; padding-left: 0;">
                        <li style="margin-bottom: 10px;">✅ Placed students at leading companies</li>
                        <li style="margin-bottom: 10px;">💰 Helped participants secure competitive offers</li>
                        <li style="margin-bottom: 10px;">🌐 Built a network of students and industry mentors</li>
                    </ul>
                </div>
                
                <div style="background-color: #e3f2fd; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="color: #1976d2; margin-top: 0;">Program highlights:</h3>
                    <ul style="list-style: none; padding-left: 0;">
                        <li style="margin-bottom: 10px;">📚 Skills development workshops and training</li>
                        <li style="margin-bottom: 10px;">📝 Application support and career guidance</li>
                        <li style="margin-bottom: 10px;">🤝 Networking opportunities with industry professionals</li>
                    </ul>
                </div>
                
                <div style="background-color: #fff3cd; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #ffc107;">
                    <h3 style="color: #856404; margin-top: 0;">How to get involved:</h3>
                    <ol style="color: #856404;">
                        <li>Learn more about our program</li>
                        <li>Apply by [Application Deadline]</li>
                        <li>Join our information sessions</li>
                    </ol>
                </div>
                
                <p><strong>We've helped students from universities nationwide. We'd love to support your career journey as well.</strong></p>
                
                <hr style="margin: 30px 0; border: 1px solid #eee;">
                
                <div style="text-align: center; margin-top: 30px;">
                    <p style="margin: 5px 0; font-weight: bold;">[Organization Name]</p>
                    <p style="margin: 5px 0;">[Organization Type]</p>
                    <p style="margin: 5px 0; font-style: italic;">[Mission Statement]</p>
                    <p style="margin: 10px 0;"><a href="#" style="color: #1976d2; text-decoration: underline;">Application Link: [Website URL]</a></p>
                    <p style="margin: 5px 0; font-size: 12px; color: #666;">Contact: [Contact Information]</p>
                </div>
                
                <hr style="margin: 30px 0; border: 1px solid #eee;">
                <p style="font-size: 12px; color: #666;">
                    This email was sent to {recipient_email}. If you received this email by mistake or wish to unsubscribe, 
                    please reply with "UNSUBSCRIBE" in the subject line.
                </p>
            </div>
        </body>
        </html>
        """
        
        return subject, body_text, body_html
    
    def send_email_with_retry(self, recipient_email: str, subject: str, body_text: str, body_html: str) -> bool:
        """
        Send an email with retry logic and exponential backoff.
        
        Args:
            recipient_email (str): Recipient's email address
            subject (str): Email subject
            body_text (str): Email body (text version)
            body_html (str): Email body (HTML version)
            
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        for attempt in range(self.max_retries + 1):
            try:
                return self._send_single_email(recipient_email, subject, body_text, body_html)
            
            except (smtplib.SMTPServerDisconnected, smtplib.SMTPDataError, ConnectionError) as e:
                self.logger.warning(f"Attempt {attempt + 1} failed for {recipient_email}: {str(e)}")
                self.stats['retries'] += 1
                
                if attempt < self.max_retries:
                    # Exponential backoff with jitter
                    delay = self.retry_delay_base * (2 ** attempt) + random.uniform(0, 1)
                    self.logger.info(f"Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                    
                    # Reset connection on retry
                    self.close_smtp_connection()
                else:
                    self.logger.error(f"All {self.max_retries + 1} attempts failed for {recipient_email}")
                    self.stats['failed_sends'] += 1
                    return False
            
            except Exception as e:
                self.logger.error(f"Unexpected error sending to {recipient_email}: {str(e)}")
                self.stats['failed_sends'] += 1
                return False
        
        return False
    
    def _send_single_email(self, recipient_email: str, subject: str, body_text: str, body_html: str) -> bool:
        """
        Send a single email using the reused SMTP connection.
        
        Args:
            recipient_email (str): Recipient's email address
            subject (str): Email subject
            body_text (str): Email body (text version)
            body_html (str): Email body (HTML version)
            
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        # Ensure we have a valid SMTP connection
        if not self.ensure_smtp_connection():
            raise ConnectionError("Could not establish SMTP connection")
        
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = f"{self.sender_name} <{self.sender_email}>"
        message["To"] = recipient_email
        
        # Create text and HTML parts
        part1 = MIMEText(body_text, "plain")
        part2 = MIMEText(body_html, "html")
        
        # Add parts to message
        message.attach(part1)
        message.attach(part2)
        
        # Send email using the reused connection
        self.smtp_connection.sendmail(self.sender_email, recipient_email, message.as_string())
        
        self.logger.info(f"Email sent successfully to: {recipient_email}")
        self.stats['successful_sends'] += 1
        self.stats['emails_sent_today'] += 1
        return True
    
    def send_bulk_emails(self, emails: List[str], test_mode: bool = True, batch_size: Optional[int] = None):
        """
        Send bulk emails to a list of recipients with improved error handling and rate limiting.
        
        Args:
            emails (List[str]): List of email addresses
            test_mode (bool): If True, sends only to first 3 emails for testing
            batch_size (Optional[int]): Number of emails to send in each batch (uses self.batch_size if None)
        """
        if not emails:
            self.logger.warning("No emails to send")
            return
        
        if test_mode:
            emails = emails[:3]  # Send to first 3 emails only in test mode
            self.logger.info("TEST MODE: Sending to first 3 emails only")
        
        # Use instance batch size if not provided
        if batch_size is None:
            batch_size = self.batch_size
        
        self.stats['total_emails'] = len(emails)
        self.logger.info(f"Starting bulk email send to {len(emails)} recipients")
        self.logger.info(f"Rate limiting: {self.delay_between_emails}s between emails, {self.batch_delay}s between batches")
        
        try:
            # Establish initial SMTP connection
            if not self.ensure_smtp_connection():
                self.logger.error("Could not establish initial SMTP connection. Aborting.")
                return
            
            for i, email in enumerate(emails, 1):
                # Check daily limit before sending
                if not self.check_daily_limit():
                    self.logger.error("Daily email limit reached. Stopping email send.")
                    break
                
                self.logger.info(f"Sending email {i}/{len(emails)} to: {email}")
                
                # Create email content
                subject, body_text, body_html = self.create_email_content(email)
                
                # Send email with retry logic
                success = self.send_email_with_retry(email, subject, body_text, body_html)
                
                if not success:
                    self.logger.warning(f"Failed to send email to {email} after all retries")
                
                # Add delay between emails (with some randomization to avoid pattern detection)
                if i < len(emails):  # Don't delay after the last email
                    delay = self.delay_between_emails + random.uniform(0, 0.5)
                    time.sleep(delay)
                
                # Batch handling with longer pause
                if i % batch_size == 0 and i < len(emails):
                    self.logger.info(f"Completed batch of {batch_size} emails. Pausing for {self.batch_delay} seconds...")
                    
                    # Close and reconnect SMTP connection between batches to avoid timeouts
                    self.close_smtp_connection()
                    time.sleep(self.batch_delay)
                    
                    # Reconnect for next batch
                    if not self.ensure_smtp_connection():
                        self.logger.error("Could not reconnect SMTP. Stopping email send.")
                        break
        
        except KeyboardInterrupt:
            self.logger.info("Email sending interrupted by user")
        except Exception as e:
            self.logger.error(f"Unexpected error during bulk email send: {str(e)}")
        finally:
            # Always close the SMTP connection when done
            self.close_smtp_connection()
            
            # Print final statistics
            self.print_statistics()
    
    def print_statistics(self):
        """Print email sending statistics."""
        self.logger.info("="*50)
        self.logger.info("EMAIL SENDING STATISTICS")
        self.logger.info("="*50)
        self.logger.info(f"Total emails to send: {self.stats['total_emails']}")
        self.logger.info(f"Successfully sent: {self.stats['successful_sends']}")
        self.logger.info(f"Failed to send: {self.stats['failed_sends']}")
        self.logger.info(f"Invalid email formats: {self.stats['invalid_emails']}")
        self.logger.info(f"Retry attempts: {self.stats['retries']}")
        self.logger.info(f"Emails sent today: {self.stats['emails_sent_today']}")
        self.logger.info(f"Daily limit remaining: {self.daily_limit - self.stats['emails_sent_today']}")
        
        if self.stats['total_emails'] > 0:
            success_rate = (self.stats['successful_sends'] / self.stats['total_emails']) * 100
            self.logger.info(f"Success rate: {success_rate:.2f}%")
        
        self.logger.info("="*50)


def main():
    """Main function to run the bulk email sender."""
    
    print("="*60)
    print("BULK EMAIL SENDER FOR PROGRAM OUTREACH")
    print("="*60)
    print()
    
    # Create email sender instance
    sender = BulkEmailSender()
    
    print("IMPORTANT: Before running this script, please:")
    print("1. Set environment variables (recommended) or update the script:")
    print("   - SENDER_EMAIL: Your email address")
    print("   - SENDER_PASSWORD: Your Gmail App Password")
    print("   - SENDER_NAME: Your name")
    print("2. For Gmail users: Enable 2FA and create an App Password")
    print("3. Ensure your email provider allows SMTP access")
    print()
    
    # Check if email configuration is still default
    if sender.sender_email == "your_email@gmail.com" or sender.sender_password == "your_app_password":
        print("❌ EMAIL CONFIGURATION NOT SET!")
        print()
        print("Option 1 (Recommended): Set environment variables:")
        print("  Windows: set SENDER_EMAIL=your_email@gmail.com")
        print("           set SENDER_PASSWORD=your_app_password")
        print("           set SENDER_NAME=Your Name")
        print()
        print("  Mac/Linux: export SENDER_EMAIL=your_email@gmail.com")
        print("             export SENDER_PASSWORD=your_app_password")
        print("             export SENDER_NAME='Your Name'")
        print()
        print("Option 2: Update the script configuration (lines 41-43)")
        print()
        return
    
    print("Current configuration:")
    print(f"📧 Sender: {sender.sender_name} <{sender.sender_email}>")
    print(f"🌐 SMTP Server: {sender.smtp_server}:{sender.smtp_port}")
    print(f"📊 Daily Limit: {sender.daily_limit} emails")
    print(f"⏱️  Rate Limiting: {sender.delay_between_emails}s between emails, {sender.batch_delay}s between batches")
    print(f"🔄 Retry Logic: {sender.max_retries + 1} attempts with exponential backoff")
    print()
    
    # Ask user for options
    print("Options:")
    print("1. Send to all emails in CSV files (TEST MODE - first 3 only)")
    print("2. Send to all emails in CSV files (PRODUCTION MODE)")
    print("3. Send to specific CSV file")
    print("4. TEST: Send to your own email only")
    print("5. Exit")
    
    choice = input("\nEnter your choice (1-5): ").strip()
    
    if choice == "1":
        # Test mode - all CSV files
        emails = sender.read_emails_from_multiple_csvs("Copy of Students 2025 - *.csv")
        if emails:
            confirm = input(f"\nFound {len(emails)} emails. Send test emails to first 3? (y/n): ")
            if confirm.lower() == 'y':
                sender.send_bulk_emails(emails, test_mode=True)
        
    elif choice == "2":
        # Production mode - all CSV files
        emails = sender.read_emails_from_multiple_csvs("Copy of Students 2025 - *.csv")
        if emails:
            print(f"\n⚠️  PRODUCTION MODE: This will send emails to ALL {len(emails)} recipients!")
            confirm = input("Are you sure you want to proceed? Type 'YES' to confirm: ")
            if confirm == 'YES':
                sender.send_bulk_emails(emails, test_mode=False)
            else:
                print("Operation cancelled.")
        
    elif choice == "3":
        # Specific CSV file
        print("\nAvailable CSV files:")
        csv_files = glob.glob("Copy of Students 2025 - *.csv")
        for i, file in enumerate(csv_files, 1):
            print(f"{i}. {file}")
        
        if csv_files:
            try:
                file_choice = int(input(f"\nSelect file (1-{len(csv_files)}): ")) - 1
                if 0 <= file_choice < len(csv_files):
                    selected_file = csv_files[file_choice]
                    emails = sender.read_emails_from_csv(selected_file)
                    
                    if emails:
                        print(f"\nFound {len(emails)} emails in {selected_file}")
                        mode = input("Test mode (t) or Production mode (p)? ").strip().lower()
                        
                        if mode == 't':
                            sender.send_bulk_emails(emails, test_mode=True)
                        elif mode == 'p':
                            confirm = input(f"Send to ALL {len(emails)} recipients? Type 'YES': ")
                            if confirm == 'YES':
                                sender.send_bulk_emails(emails, test_mode=False)
                            else:
                                print("Operation cancelled.")
                else:
                    print("Invalid file selection.")
            except ValueError:
                print("Invalid input. Please enter a number.")
        else:
            print("No CSV files found.")
    
    elif choice == "4":
        # Test with own email
        test_email = input("Enter your email address for testing: ").strip()
        if test_email and sender.validate_email(test_email):
            print(f"Sending test email to: {test_email}")
            sender.send_bulk_emails([test_email], test_mode=False)
        else:
            print("Invalid email address.")
    
    elif choice == "5":
        print("Goodbye!")
        return
    
    else:
        print("Invalid choice. Please run the script again.")


if __name__ == "__main__":
    main()

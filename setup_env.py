#!/usr/bin/env python3
"""
Environment Setup Helper for Bulk Email Sender

This script helps you set up environment variables for secure email configuration.
"""

import os
import getpass

def setup_environment():
    """Interactive setup for environment variables."""
    print("=" * 60)
    print("BULK EMAIL SENDER - ENVIRONMENT SETUP")
    print("=" * 60)
    print()
    
    print("This script will help you set up environment variables for secure email configuration.")
    print("Your credentials will NOT be stored in the script file.")
    print()
    
    # Get email address
    email = input("Enter your Gmail address: ").strip()
    if not email:
        print("❌ Email address is required!")
        return
    
    # Get app password securely
    print("\nFor your Gmail App Password:")
    print("1. Enable 2-Factor Authentication on your Google account")
    print("2. Go to Google Account → Security → App passwords")
    print("3. Generate a password for 'Mail'")
    print("4. Use that 16-character password below (not your regular password)")
    print()
    
    password = getpass.getpass("Enter your Gmail App Password: ").strip()
    if not password:
        print("❌ App password is required!")
        return
    
    # Get sender name
    name = input("Enter your name (for email sender field): ").strip()
    if not name:
        print("❌ Sender name is required!")
        return
    
    # Set environment variables for current session
    os.environ["SENDER_EMAIL"] = email
    os.environ["SENDER_PASSWORD"] = password
    os.environ["SENDER_NAME"] = name
    
    print("\n✅ Environment variables set for current session!")
    print()
    print("To make these permanent, add these to your system:")
    print()
    
    # Show platform-specific instructions
    if os.name == 'nt':  # Windows
        print("Windows Command Prompt:")
        print(f'set SENDER_EMAIL={email}')
        print(f'set SENDER_PASSWORD={password}')
        print(f'set SENDER_NAME={name}')
        print()
        print("Windows PowerShell:")
        print(f'$env:SENDER_EMAIL="{email}"')
        print(f'$env:SENDER_PASSWORD="{password}"')
        print(f'$env:SENDER_NAME="{name}"')
    else:  # Unix-like (Mac/Linux)
        print("Mac/Linux Terminal:")
        print(f'export SENDER_EMAIL="{email}"')
        print(f'export SENDER_PASSWORD="{password}"')
        print(f'export SENDER_NAME="{name}"')
        print()
        print("To make permanent, add the above lines to your ~/.bashrc or ~/.zshrc")
    
    print()
    print("You can now run: python bulk_email_sender.py")
    
    return True

if __name__ == "__main__":
    try:
        setup_environment()
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user.")
    except Exception as e:
        print(f"\n❌ Error during setup: {e}")






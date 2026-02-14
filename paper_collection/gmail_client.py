#!/usr/bin/python3
"""
Gmail API Access Module

Provides functions for authenticating and interacting with the Gmail API.

Before using this module, you need to:
1. Go to https://console.cloud.google.com/
2. Create a new project (or select existing one)
3. Enable the Gmail API: APIs & Services > Enable APIs > Search "Gmail API" > Enable
4. Create OAuth 2.0 credentials:
   - APIs & Services > Credentials > Create Credentials > OAuth client ID
   - Application type: Desktop app
   - Download the JSON file and save it as 'credentials.json' in this directory
5. Install required packages:
   pip install google-auth google-auth-oauthlib google-api-python-client
"""

import base64
import os
import re
import time
from html import unescape
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

# Retry settings for API calls
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds


def get_gmail_service(
    credentials_file: Optional[str] = None, token_file: Optional[str] = None
):
    """
    Authenticate and return a Gmail API service instance.

    Args:
        credentials_file: Path to OAuth credentials file (default: from config or 'credentials.json')
        token_file: Path to token file (default: from config or 'token.json')
    """
    # Get paths from config if not provided
    if credentials_file is None or token_file is None:
        try:
            from config import config

            cfg = config()
            if credentials_file is None:
                credentials_file = cfg.get_credentials_path()
            if token_file is None:
                token_file = cfg.get_token_path()
        except ImportError:
            # Config module not available, use defaults
            if credentials_file is None:
                credentials_file = "credentials.json"
            if token_file is None:
                token_file = "token.json"

    creds = None

    # The file token.json stores the user's access and refresh tokens
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_file):
                raise FileNotFoundError(
                    f"Credentials file not found at '{credentials_file}'. "
                    "Please download OAuth credentials from Google Cloud Console. "
                    "See README.md for setup instructions."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        # Ensure directory exists
        token_dir = os.path.dirname(token_file)
        if token_dir and not os.path.exists(token_dir):
            os.makedirs(token_dir)
        with open(token_file, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def list_messages(service, user_id="me", max_results=10, query=""):
    """
    List messages in the user's mailbox.

    Args:
        service: Gmail API service instance
        user_id: User's email address or 'me' for authenticated user
        max_results: Maximum number of messages to return (no limit)
        query: Gmail search query (e.g., 'is:unread', 'from:someone@example.com')

    Returns:
        List of message dictionaries
    """
    try:
        messages = []
        page_token = None

        while len(messages) < max_results:
            # Gmail API maxResults is capped at 500 per request
            batch_size = min(500, max_results - len(messages))

            request = (
                service.users()
                .messages()
                .list(
                    userId=user_id, maxResults=batch_size, q=query, pageToken=page_token
                )
            )
            results = request.execute()

            batch_messages = results.get("messages", [])
            messages.extend(batch_messages)

            # Check if there are more pages
            page_token = results.get("nextPageToken")
            if not page_token or not batch_messages:
                break

        return messages[:max_results]  # Ensure we don't exceed max_results
    except HttpError as error:
        print(f"An error occurred: {error}")
        return []


def get_message(service, msg_id, user_id="me"):
    """
    Get a specific message by ID with retry logic.

    Args:
        service: Gmail API service instance
        msg_id: Message ID
        user_id: User's email address or 'me' for authenticated user

    Returns:
        Message dictionary with full details
    """
    for attempt in range(MAX_RETRIES):
        try:
            message = (
                service.users()
                .messages()
                .get(userId=user_id, id=msg_id, format="full")
                .execute()
            )
            return message
        except HttpError as error:
            # Retry on transient HTTP errors (5xx, 429)
            if error.resp.status in (429, 500, 502, 503, 504):
                if attempt < MAX_RETRIES - 1:
                    print(
                        f"  Retry {attempt + 1}/{MAX_RETRIES} after HTTP {error.resp.status}"
                    )
                    time.sleep(RETRY_DELAY)
                else:
                    print(
                        f"  Failed after {MAX_RETRIES} attempts: HTTP {error.resp.status}"
                    )
                    return None
            else:
                # Non-retryable HTTP error (4xx except 429)
                print(f"An error occurred: {error}")
                return None
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                print(f"  Retry {attempt + 1}/{MAX_RETRIES} after error: {e}")
                time.sleep(RETRY_DELAY)
            else:
                print(f"  Failed after {MAX_RETRIES} attempts: {e}")
                return None
    return None


def strip_html(html_content):
    """Remove HTML tags and return plain text."""
    # Remove style and script tags with content
    text = re.sub(
        r"<style[^>]*>.*?</style>", "", html_content, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(
        r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE
    )

    # Replace <br> and </p> with newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</div>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</tr>", "\n", text, flags=re.IGNORECASE)

    # Remove all other HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Decode HTML entities
    text = unescape(text)

    # Clean up whitespace: multiple spaces to single, multiple newlines to double
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _extract_parts(parts):
    """Recursively extract plain text and HTML from message parts."""
    plain_text = None
    html_text = None

    for part in parts:
        mime_type = part.get("mimeType", "")

        # Handle nested multipart structures
        if mime_type.startswith("multipart/"):
            nested_parts = part.get("parts", [])
            nested_plain, nested_html = _extract_parts(nested_parts)
            if nested_plain and not plain_text:
                plain_text = nested_plain
            if nested_html and not html_text:
                html_text = nested_html
        else:
            data = part.get("body", {}).get("data")
            if data:
                decoded = base64.urlsafe_b64decode(data).decode("utf-8")
                if mime_type == "text/plain" and not plain_text:
                    plain_text = decoded
                elif mime_type == "text/html" and not html_text:
                    html_text = decoded

    return plain_text, html_text


def get_message_headers(message):
    """Extract common headers from a message."""
    headers = message.get("payload", {}).get("headers", [])
    header_dict = {}

    for header in headers:
        name = header.get("name", "").lower()
        if name in ["from", "to", "subject", "date"]:
            header_dict[name] = header.get("value", "")

    return header_dict


def get_raw_html(message):
    """Extract raw HTML content from a message."""
    payload = message.get("payload", {})

    # Check for simple message
    if "body" in payload and payload["body"].get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")

    # Check for multipart message - get HTML
    _, html_text = _extract_parts(payload.get("parts", []))
    return html_text or ""


def send_email(service, to, subject, body, user_id="me"):
    """
    Send an email using the Gmail API.

    Args:
        service: Gmail API service instance
        to: Recipient email address
        subject: Email subject
        body: Email body (plain text)
        user_id: User's email address or 'me' for authenticated user

    Returns:
        Sent message object or None if failed
    """
    from email.mime.text import MIMEText

    try:
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {"raw": encoded_message}

        sent_message = (
            service.users()
            .messages()
            .send(userId=user_id, body=create_message)
            .execute()
        )
        return sent_message
    except HttpError as error:
        print(f"Error sending email: {error}")
        return None

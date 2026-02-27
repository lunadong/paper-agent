"""
Vercel Serverless Function for Paper Browser

This module re-exports the Flask app from web_server.py to maintain
a single source of truth for all API routes and logic.

Vercel requires an 'app' object in index.py for serverless deployment.
"""

# Import the Flask app from web_server.py (single source of truth)

# Vercel requires this - the app object is used by the serverless function
# For local development, run: python web_server.py

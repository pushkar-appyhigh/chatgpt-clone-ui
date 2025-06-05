# ChatGPT Clone UI

A simple FastAPI-based UI for interacting with a ChatGPT-like API endpoint. This project provides a web interface similar to ChatGPT for an existing `/api/v1/chat` endpoint.

## Features

- Clean, modern UI inspired by ChatGPT
- Support for text-based conversations
- Conversation history
- Display of token usage and cost information
- Responsive design that works on mobile and desktop
- Google OAuth authentication
- MongoDB storage for user data and conversation history

## Prerequisites

- Python 3.7+
- An API endpoint available at `/api/v1/chat` (typically at http://localhost:9000/api/v1/chat)
- MongoDB installed and running
- Google Developer account for OAuth setup

## Installation

1. Clone this repository
2. Install the required dependencies:

```bash
pip install -r requirements.txt
```

3. Set up the environment variables:
   - Copy `env.example` to `.env`
   - Edit `.env` with your Google OAuth credentials and MongoDB URI

## Setting up Google OAuth

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Navigate to "APIs & Services" > "Credentials"
4. Configure the OAuth consent screen
5. Create an OAuth 2.0 Client ID
6. Add authorized redirect URIs:
   - For local development: `http://127.0.0.1:8000/auth/callback`
   - For production: `https://yourdomain.com/auth/callback`
7. Copy the Client ID and Client Secret to your `.env` file

## MongoDB Setup

1. Install MongoDB locally or use a cloud service like MongoDB Atlas
2. Update the `MONGODB_URI` in your `.env` file
3. The application will automatically create the required collections:
   - `users` - User information from Google OAuth
   - `sessions` - Chat sessions
   - `messages` - Individual messages in the conversations

## Usage

1. Start the FastAPI server:

```bash
uvicorn main:app --reload
```

2. Open your browser and navigate to http://localhost:8000

3. Log in with your Google account or enter an email

4. Start chatting! The interface will send requests to the API endpoint at `/api/v1/chat`.

## API Integration

This UI is designed to work with an API that:
- Accepts POST requests to `/api/v1/chat`
- Takes a JSON payload with `message`, `conversation_id`, and optionally `email_id` fields
- Returns a response with `type`, `text_content`, `image_content` (if applicable), and `metadata` fields

## Project Structure

- `main.py` - FastAPI application
- `templates/chat.html` - HTML template for the chat interface
- `static/css/styles.css` - CSS styles for the UI
- `static/js/chat.js` - JavaScript for handling chat functionality
- `.env` - Environment variables (not in version control)
- `env.example` - Example environment variable file

## License

MIT

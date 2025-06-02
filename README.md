# ChatGPT Clone UI

A simple FastAPI-based UI for interacting with a ChatGPT-like API endpoint. This project provides a web interface similar to ChatGPT for an existing `/api/v1/chat` endpoint.

## Features

- Clean, modern UI inspired by ChatGPT
- Support for text-based conversations
- Conversation history
- Display of token usage and cost information
- Responsive design that works on mobile and desktop

## Prerequisites

- Python 3.7+
- An API endpoint available at `/api/v1/chat` (typically at http://localhost:9000/api/v1/chat)

## Installation

1. Clone this repository
2. Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Usage

1. Start the FastAPI server:

```bash
uvicorn main:app --reload
```

2. Open your browser and navigate to http://localhost:8000

3. Start chatting! The interface will send requests to the API endpoint at `/api/v1/chat`.

## API Integration

This UI is designed to work with an API that:
- Accepts POST requests to `/api/v1/chat`
- Takes a JSON payload with `message` and `conversation_id` fields
- Returns a response with `type`, `text_content`, `image_content` (if applicable), and `metadata` fields

## Project Structure

- `main.py` - FastAPI application
- `templates/chat.html` - HTML template for the chat interface
- `static/css/styles.css` - CSS styles for the UI
- `static/js/chat.js` - JavaScript for handling chat functionality

## License

MIT # chatgpt-clone-ui

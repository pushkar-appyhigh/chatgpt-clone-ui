from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx
import json
import logging
from typing import Optional
from pydantic import BaseModel, EmailStr

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Set up templates
templates = Jinja2Templates(directory="templates")

# Backend API URL
BACKEND_API_URL = "http://localhost:9000"

# Pydantic models for request validation
class EmailRequest(BaseModel):
    email_id: EmailStr

class SessionRequest(BaseModel):
    session_id: str
    email_id: Optional[EmailStr] = None

class ClearConversationRequest(BaseModel):
    conversation_id: Optional[str] = None
    email_id: Optional[EmailStr] = None

@app.get("/", response_class=HTMLResponse)
async def get_chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})

@app.post("/api/v1/chat")
async def proxy_chat_api(request: Request):
    # Get the request body
    try:
        body = await request.json()
        message = body.get('message', '')
        logger.info(f"Received chat request: {message[:50]}...")
        
        # Using a fixed timeout of 90 seconds for all requests
        timeout = 90.0
        logger.info(f"Using timeout: {timeout}s for all requests")
        
        # Forward the request to the backend API
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{BACKEND_API_URL}/api/v1/chat?email_id=gargpushkar96@gmail.com",
                    json=body,
                    headers={"Content-Type": "application/json"},
                    timeout=timeout  # Fixed 90-second timeout
                )
                
                # Get the response data
                response_data = response.json()
                logger.info(f"Response type: {response_data.get('type')}")
                
                # Log the full response for debugging
                if 'text_content' in response_data:
                    logger.info(f"Response text content: {response_data['text_content']}")
                if 'image_content' in response_data:
                    logger.info(f"Response has image_content: {'Yes' if response_data['image_content'] else 'No'}")
                
                # Return the backend API response
                return JSONResponse(
                    content=response_data,
                    status_code=response.status_code
                )
            except httpx.TimeoutException:
                logger.error("Request to backend API timed out after 90 seconds")
                return JSONResponse(
                    content={
                        "type": "text",
                        "text_content": "Request timed out after 90 seconds. The request may be too complex or the server might be experiencing high load. Please try again with a simpler prompt.",
                        "image_content": None,
                        "metadata": {
                            "error": "timeout"
                        }
                    },
                    status_code=504
                )
            except httpx.RequestError as e:
                logger.error(f"Error communicating with backend API: {str(e)}")
                return JSONResponse(
                    content={
                        "type": "text",
                        "text_content": f"Error communicating with backend API: {str(e)}",
                        "image_content": None,
                        "metadata": {
                            "error": "connection_error"
                        }
                    },
                    status_code=502
                )
            except Exception as e:
                logger.error(f"Unexpected error: {str(e)}")
                return JSONResponse(
                    content={
                        "type": "text",
                        "text_content": f"An unexpected error occurred: {str(e)}",
                        "image_content": None,
                        "metadata": {
                            "error": "server_error"
                        }
                    },
                    status_code=500
                )
    except json.JSONDecodeError:
        logger.error("Invalid JSON in request body")
        return JSONResponse(
            content={
                "type": "text",
                "text_content": "Invalid JSON in request body",
                "image_content": None,
                "metadata": {
                    "error": "invalid_json"
                }
            },
            status_code=400
        )
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return JSONResponse(
            content={
                "type": "text",
                "text_content": f"Error processing request: {str(e)}",
                "image_content": None,
                "metadata": {
                    "error": "server_error"
                }
            },
            status_code=500
        )

# New endpoints for session management

@app.post("/api/v1/sessions")
async def get_sessions(request: EmailRequest):
    """Get all chat sessions for an email"""
    try:
        logger.info(f"Getting sessions for email: {request.email_id}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BACKEND_API_URL}/api/v1/sessions",
                json={"email_id": request.email_id},
                headers={"Content-Type": "application/json"},
                timeout=30.0
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                # For development - if backend isn't available, return mock data
                logger.warning(f"Backend API not available, returning mock session data")
                return {
                    "sessions": [
                        {
                            "session_id": "mock-session-1",
                            "email_id": request.email_id,
                            "created_at": 1622548800.0,
                            "updated_at": 1622548900.0,
                            "message_count": 5,
                            "last_message": "Last message in this mock conversation"
                        },
                        {
                            "session_id": "mock-session-2",
                            "email_id": request.email_id,
                            "created_at": 1622538800.0,
                            "updated_at": 1622538900.0,
                            "message_count": 3,
                            "last_message": "Another mock conversation"
                        }
                    ]
                }
    except Exception as e:
        logger.error(f"Error getting sessions: {str(e)}")
        return JSONResponse(
            content={"detail": f"Error getting sessions: {str(e)}"},
            status_code=500
        )

@app.post("/api/v1/conversation-history")
async def get_conversation_history(request: SessionRequest):
    """Get conversation history for a session"""
    try:
        logger.info(f"Getting conversation history for session: {request.session_id}")
        
        request_data = {"session_id": request.session_id}
        if request.email_id:
            request_data["email_id"] = "gargpushkar96@gmail.com"
            # request_data["email_id"] = request.email_id
            
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BACKEND_API_URL}/api/v1/conversation-history",
                json=request_data,
                headers={"Content-Type": "application/json"},
                timeout=30.0
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                # For development - if backend isn't available, return mock data
                logger.warning(f"Backend API not available, returning mock conversation data")
                
                # Check if this is for mock-session-1 or mock-session-2
                if request.session_id == "mock-session-1":
                    return {
                        "session_id": request.session_id,
                        "email_id": request.email_id,
                        "created_at": 1622548800.0,
                        "updated_at": 1622548900.0,
                        "messages": [
                            {
                                "role": "user",
                                "content": "Hello, how are you?",
                                "timestamp": 1622548800.0
                            },
                            {
                                "role": "assistant",
                                "content": "I'm an AI assistant, I don't have feelings, but I'm functioning well. How can I help you today?",
                                "timestamp": 1622548820.0
                            },
                            {
                                "role": "user",
                                "content": "Can you tell me about the weather?",
                                "timestamp": 1622548840.0
                            },
                            {
                                "role": "assistant",
                                "content": "I don't have access to real-time weather data. You would need to check a weather service or app for current conditions.",
                                "timestamp": 1622548860.0
                            },
                            {
                                "role": "user",
                                "content": "Thanks for the information!",
                                "timestamp": 1622548880.0
                            }
                        ]
                    }
                else:
                    return {
                        "session_id": request.session_id,
                        "email_id": request.email_id,
                        "created_at": 1622538800.0,
                        "updated_at": 1622538900.0,
                        "messages": [
                            {
                                "role": "user",
                                "content": "Can you help me with a coding problem?",
                                "timestamp": 1622538800.0
                            },
                            {
                                "role": "assistant",
                                "content": "Of course! Please describe the problem you're having, and I'll do my best to help.",
                                "timestamp": 1622538820.0
                            },
                            {
                                "role": "user",
                                "content": "I'm learning Python and struggling with list comprehensions.",
                                "timestamp": 1622538840.0
                            }
                        ]
                    }
    except Exception as e:
        logger.error(f"Error getting conversation history: {str(e)}")
        return JSONResponse(
            content={"detail": f"Error getting conversation history: {str(e)}"},
            status_code=500
        )

@app.post("/api/v1/clear-conversation")
async def clear_conversation(request: ClearConversationRequest):
    """Clear conversation history"""
    try:
        if request.conversation_id:
            logger.info(f"Clearing conversation for session: {request.conversation_id}")
            message_type = "session"
            id_value = request.conversation_id
        elif request.email_id:
            logger.info(f"Clearing all conversations for email: {request.email_id}")
            message_type = "email"
            id_value = request.email_id
        else:
            return JSONResponse(
                content={"detail": "Either conversation_id or email_id must be provided"},
                status_code=400
            )
        
        request_data = {}
        if request.conversation_id:
            request_data["conversation_id"] = request.conversation_id
        if request.email_id:
            request_data["email_id"] = request.email_id
            
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BACKEND_API_URL}/api/v1/clear-conversation",
                json=request_data,
                headers={"Content-Type": "application/json"},
                timeout=30.0
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                # For development - if backend isn't available, return mock response
                logger.warning(f"Backend API not available, returning mock clear response")
                return {
                    "type": "info",
                    "text_content": f"Conversation history cleared successfully for {message_type} {id_value}"
                }
    except Exception as e:
        logger.error(f"Error clearing conversation: {str(e)}")
        return JSONResponse(
            content={"detail": f"Error clearing conversation: {str(e)}"},
            status_code=500
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 
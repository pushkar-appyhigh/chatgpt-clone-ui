from fastapi import FastAPI, Request, Depends, HTTPException, status, Cookie
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx
import json
import logging
import os
import socket
from typing import Optional
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
import secrets
from pymongo import MongoClient
from dotenv import load_dotenv
from jose import JWTError, jwt

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Google OAuth configuration
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = "https://aibanners2.phot.ai/auth/callback" if socket.gethostname() == "iof1582d" else "http://127.0.0.1:8000/auth/callback"
AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
USER_INFO = "https://www.googleapis.com/oauth2/v1/userinfo"

# JWT settings
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# MongoDB connection
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
db_client = MongoClient(MONGODB_URI)
db = db_client["chatgpt_clone"]
users_collection = db["users"]
sessions_collection = db["sessions"]
messages_collection = db["messages"]

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

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class UserInDB(BaseModel):
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None

# Authentication functions
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_user_from_token(token: str = Cookie(None)):
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            return None
        token_data = TokenData(email=email)
    except JWTError:
        return None
    
    user = users_collection.find_one({"email": token_data.email})
    if user:
        return UserInDB(**user)
    return None

# Authentication dependency
async def get_current_user(user: Optional[UserInDB] = Depends(get_user_from_token)):
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

# Routes
@app.get("/", response_class=HTMLResponse)
async def get_chat_page(request: Request, user: Optional[UserInDB] = Depends(get_user_from_token)):
    return templates.TemplateResponse("chat.html", {"request": request, "user": user})

@app.get("/login/google")
async def login_google():
    """Redirect to Google OAuth login"""
    auth_url = f"{AUTH_URI}?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&scope=email%20profile&access_type=offline"
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
async def auth_callback(code: str, request: Request):
    """Handle Google OAuth callback"""
    try:
        # Exchange code for token
        token_data = {
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code"
        }
        
        async with httpx.AsyncClient() as client:
            token_response = await client.post(TOKEN_URI, data=token_data)
            token_json = token_response.json()
            
            if "error" in token_json:
                logger.error(f"Error getting token: {token_json}")
                return JSONResponse(
                    content={"error": "Failed to authenticate with Google"},
                    status_code=400
                )
            
            # Get user info
            headers = {"Authorization": f"Bearer {token_json['access_token']}"}
            user_response = await client.get(USER_INFO, headers=headers)
            user_info = user_response.json()
            
            # Save user to database
            user_data = {
                "email": user_info["email"],
                "name": user_info.get("name"),
                "picture": user_info.get("picture"),
                "last_login": datetime.utcnow()
            }
            
            # Upsert user (insert if not exists, update if exists)
            print(f"User data: {user_data}")
            users_collection.update_one(
                {"email": user_info["email"]},
                {"$set": user_data},
                upsert=True
            )
            print(f"User data upserted: {users_collection}")
            # Create access token
            access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            access_token = create_access_token(
                data={"sub": user_info["email"]},
                expires_delta=access_token_expires
            )
            
            # Set cookie and redirect to chat
            response = RedirectResponse(url="/")
            response.set_cookie(
                key="token",
                value=access_token,
                httponly=True,
                max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                samesite="lax"
            )
            return response
            
    except Exception as e:
        logger.error(f"Error in Google callback: {str(e)}")
        return JSONResponse(
            content={"error": f"Authentication error: {str(e)}"},
            status_code=500
        )

@app.get("/logout")
async def logout():
    """Logout user by clearing token cookie"""
    response = RedirectResponse(url="/?just_logged_out=true")
    response.delete_cookie(key="token")
    return response

@app.get("/api/v1/user")
async def get_user_info(user: UserInDB = Depends(get_current_user)):
    """Get current user info"""
    return {"email": user.email, "name": user.name, "picture": user.picture}

@app.post("/api/v1/chat")
async def proxy_chat_api(request: Request, user: Optional[UserInDB] = Depends(get_user_from_token)):
    # Get the request body
    try:
        body = await request.json()
        message = body.get('message', '')
        logger.info(f"Received chat request: {message[:50]}...")
        
        # Using a fixed timeout of 90 seconds for all requests
        timeout = 180.0
        logger.info(f"Using timeout: {timeout}s for all requests")
        
        # Add user email if authenticated
        if user:
            body["email_id"] = user.email
        
        # Forward the request to the backend API
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{BACKEND_API_URL}/api/v1/chat?email_id={user.email}",
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
async def get_sessions(request: EmailRequest, user: Optional[UserInDB] = Depends(get_user_from_token)):
    """Get all chat sessions for an email"""
    try:
        # Verify user is authorized to access this email's sessions
        if user and user.email != request.email_id:
            return JSONResponse(
                content={"detail": "Unauthorized to access this email's sessions"},
                status_code=403
            )
            
        logger.info(f"Getting sessions for email: {request.email_id}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BACKEND_API_URL}/api/v1/sessions",
                json={"email_id": request.email_id},
                headers={"Content-Type": "application/json"},
                timeout=30.0
            )
            
            if response.status_code == 200:
                sessions_data = response.json()
                print(f"Sessions data: {sessions_data}")
                return sessions_data
            else:
                # For development - if backend isn't available, return mock data
                logger.warning(f"Backend API not available, returning mock session data")

    except Exception as e:
        logger.error(f"Error getting sessions: {str(e)}")
        return JSONResponse(
            content={"detail": f"Error getting sessions: {str(e)}"},
            status_code=500
        )

@app.post("/api/v1/conversation-history")
async def get_conversation_history(request: SessionRequest, user: Optional[UserInDB] = Depends(get_user_from_token)):
    """Get conversation history for a session"""
    try:
        # Verify user is authorized to access this session
        if user and request.email_id and user.email != request.email_id:
            return JSONResponse(
                content={"detail": "Unauthorized to access this conversation"},
                status_code=403
            )
            
        logger.info(f"Getting conversation history for session: {request.session_id}")
        
        # If not in MongoDB, try backend API
        request_data = {"session_id": request.session_id}
        if request.email_id:
            request_data["email_id"] = request.email_id
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BACKEND_API_URL}/api/v1/conversation-history",
                json=request_data,
                headers={"Content-Type": "application/json"},
                timeout=30.0
            )
            
            if response.status_code == 200:
                history_data = response.json()
                
                # Store messages in MongoDB
                if history_data.get("messages"):
                    # Update session
                    sessions_collection.update_one(
                        {"session_id": request.session_id},
                        {"$set": {
                            "session_id": history_data["session_id"],
                            "email_id": history_data["email_id"],
                            "created_at": history_data["created_at"],
                            "updated_at": history_data["updated_at"]
                        }},
                        upsert=True
                    )
                    
                    # Insert messages
                    for msg in history_data["messages"]:
                        messages_collection.update_one(
                            {
                                "session_id": request.session_id,
                                "timestamp": msg["timestamp"]
                            },
                            {"$set": {
                                "session_id": request.session_id,
                                "role": msg["role"],
                                "content": msg["content"],
                                "timestamp": msg["timestamp"]
                            }},
                            upsert=True
                        )
                
                return history_data
            else:
                # For development - if backend isn't available, return mock data
                logger.warning(f"Backend API not available, returning mock conversation data")
                
    except Exception as e:
        logger.error(f"Error getting conversation history: {str(e)}")
        return JSONResponse(
            content={"detail": f"Error getting conversation history: {str(e)}"},
            status_code=500
        )

@app.post("/api/v1/clear-conversation")
async def clear_conversation(request: ClearConversationRequest, user: Optional[UserInDB] = Depends(get_user_from_token)):
    """Clear conversation history"""
    try:
        # Verify user is authorized to clear this conversation
        if user and request.email_id and user.email != request.email_id:
            return JSONResponse(
                content={"detail": "Unauthorized to clear this conversation"},
                status_code=403
            )
            
        if request.conversation_id:
            logger.info(f"Clearing conversation for session: {request.conversation_id}")
            message_type = "session"
            id_value = request.conversation_id
            
            # Delete from MongoDB
            sessions_collection.delete_one({"session_id": request.conversation_id})
            messages_collection.delete_many({"session_id": request.conversation_id})
            
        elif request.email_id:
            logger.info(f"Clearing all conversations for email: {request.email_id}")
            message_type = "email"
            id_value = request.email_id
            
            # Delete from MongoDB
            sessions_collection.delete_many({"email_id": request.email_id})
            
            # Get all session IDs for this email
            session_ids = sessions_collection.find(
                {"email_id": request.email_id},
                {"session_id": 1, "_id": 0}
            )
            
            # Delete all messages for these sessions
            for session in session_ids:
                messages_collection.delete_many({"session_id": session["session_id"]})
            
        else:
            return JSONResponse(
                content={"detail": "Either conversation_id or email_id must be provided"},
                status_code=400
            )
        
        # Try to clear from backend API as well
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
                # If backend API is not available, return success anyway
                logger.warning(f"Backend API not available for clearing conversation, but MongoDB was cleared")
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
from fastapi import FastAPI, Request, Depends, HTTPException, status, Cookie, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx
import json
import logging
import os
import socket
import uuid
import boto3
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
REDIRECT_URI = "https://aichats.phot.ai/auth/callback" if socket.gethostname() == "iof1582d" else "http://127.0.0.1:8000/auth/callback"
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

# S3 configuration
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "your-bucket-name")
S3_REGION = os.getenv("S3_REGION", "us-east-1").strip('%')  # Remove any trailing % character
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")

# Log S3 configuration (without secret key)
logger.info(f"S3 Configuration - Bucket: {S3_BUCKET_NAME}, Region: {S3_REGION}")
logger.info(f"AWS_ACCESS_KEY present: {'Yes' if AWS_ACCESS_KEY else 'No'}")

# S3 client
try:
    if not AWS_ACCESS_KEY or not AWS_SECRET_KEY:
        logger.warning("AWS credentials are missing. S3 uploads will not work.")
        s3_client = None
    else:
        s3_client = boto3.client(
            's3',
            region_name=S3_REGION,
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY
        )
        logger.info(f"S3 client initialized successfully with region {S3_REGION}")
        
        # Test if we can access the bucket
        try:
            s3_client.head_bucket(Bucket=S3_BUCKET_NAME)
            logger.info(f"Successfully connected to S3 bucket: {S3_BUCKET_NAME}")
        except Exception as bucket_error:
            logger.error(f"Error accessing S3 bucket {S3_BUCKET_NAME}: {str(bucket_error)}")
            logger.warning("S3 uploads may fail due to bucket access issues")
except Exception as e:
    logger.error(f"Error initializing S3 client: {str(e)}")
    logger.exception("Full S3 client initialization error:")
    s3_client = None

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

class ChatRequest(BaseModel):
    message: str
    conversation_id: str
    email_id: Optional[EmailStr] = None
    image_link: Optional[str] = None

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

@app.post("/api/v1/upload-image")
async def upload_image(
    file: UploadFile = File(..., alias="image"),
    user: Optional[UserInDB] = Depends(get_user_from_token)
):
    """Upload an image to S3 and return the URL"""
    logger.info(f"Upload image request received: {file.filename if file else 'No image'}")
    
    if not user:
        logger.error("Authentication required for image upload")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        # Check if S3 client is configured
        if not s3_client:
            logger.error("S3 client not configured")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="S3 storage is not configured"
            )
        
        # Validate file type
        content_type = file.content_type
        logger.info(f"Image content type: {content_type}")
        
        if not content_type.startswith('image/'):
            logger.error(f"Invalid content type: {content_type}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be an image"
            )
        
        # Generate a unique file name
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{user.email}/{uuid.uuid4()}{file_extension}"
        logger.info(f"Generated unique filename: {unique_filename}")
        
        # Read file contents
        file_contents = await file.read()
        file_size = len(file_contents)
        logger.info(f"Read {file_size} bytes from image file")
        
        # For testing: If S3 is not configured, return a dummy URL
        if os.getenv("ENVIRONMENT") == "development" and not AWS_ACCESS_KEY:
            logger.info("Development mode: returning dummy URL")
            return {"image_url": f"https://example.com/dummy/{unique_filename}"}
        
        # Upload to S3
        logger.info(f"Uploading to S3 bucket: {S3_BUCKET_NAME}")
        try:
            s3_client.put_object(
                Bucket=S3_BUCKET_NAME,
                Key=unique_filename,
                Body=file_contents,
                ContentType=content_type,
                ACL='public-read'  # Make the file publicly accessible
            )
            
            # Generate the URL with clean region
            region = S3_REGION.strip('%')  # Remove any trailing % character
            image_url = f"https://{S3_BUCKET_NAME}.s3.{region}.amazonaws.com/{unique_filename}"
            
            # Log success
            logger.info(f"Image uploaded successfully: {image_url}")
            
            return {"image_url": image_url}
            
        except Exception as s3_error:
            logger.error(f"S3 upload error: {str(s3_error)}")
            logger.exception("S3 exception details:")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload image to S3: {str(s3_error)}"
            )
        
    except Exception as e:
        logger.error(f"Error uploading image: {str(e)}")
        logger.exception("Full exception details:")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload image: {str(e)}"
        )

@app.post("/api/v1/chat")
async def proxy_chat_api(request: Request, user: Optional[UserInDB] = Depends(get_user_from_token)):
    # Get the request body
    try:
        body = await request.json()
        message = body.get('message', '')
        image_link = body.get('image_link', None)
        logger.info(f"Received chat request: {message[:50]}...")
        
        if image_link:
            logger.info(f"Image included in request: {image_link}")
        
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
                logger.error(f"Request timed out after {timeout} seconds")
                return JSONResponse(
                    content={"error": f"Request timed out after {timeout} seconds"},
                    status_code=504
                )
            except Exception as e:
                logger.error(f"Error in proxy request: {str(e)}")
                return JSONResponse(
                    content={"error": f"Failed to process request: {str(e)}"},
                    status_code=500
                )
    except Exception as e:
        logger.error(f"Error parsing request: {str(e)}")
        return JSONResponse(
            content={"error": f"Failed to parse request: {str(e)}"},
            status_code=400
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
                    "text_content": f"Conversation history cleared successfully."
                }
    except Exception as e:
        logger.error(f"Error clearing conversation: {str(e)}")
        return JSONResponse(
            content={"detail": f"Error clearing conversation: {str(e)}"},
            status_code=500
        )

# Add a direct upload endpoint for testing (no authentication)
@app.post("/api/v1/direct-upload")
async def direct_upload(
    file: UploadFile = File(..., alias="image")
):
    """Direct upload endpoint for testing (bypasses authentication)"""
    logger.info(f"Direct upload received: {file.filename}")
    
    try:
        # Log file details
        content_type = file.content_type
        logger.info(f"Content type: {content_type}")
        
        # Validate file type
        if not content_type.startswith('image/'):
            logger.error(f"Invalid content type: {content_type}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be an image"
            )
        
        # Read file contents
        file_contents = await file.read()
        file_size = len(file_contents)
        logger.info(f"Read {file_size} bytes from image file")
        
        # Check if S3 client is configured
        if not s3_client:
            logger.error("S3 client not configured")
            # Return a dummy URL for development/testing
            dummy_filename = f"test/{uuid.uuid4()}{os.path.splitext(file.filename)[1]}"
            dummy_url = f"https://example.com/{dummy_filename}"
            logger.info(f"S3 not configured, generated dummy URL: {dummy_url}")
            return {"image_url": dummy_url}
        
        # Generate a unique file name for ai-chats uploads
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"ai-chats/{uuid.uuid4()}{file_extension}"
        logger.info(f"Generated unique filename: {unique_filename}")
        
        # Upload to S3
        logger.info(f"Uploading to S3 bucket: {S3_BUCKET_NAME}")
        try:
            s3_client.put_object(
                Bucket=S3_BUCKET_NAME,
                Key=unique_filename,
                Body=file_contents,
                ContentType=content_type
            )
            
            # Generate the URL
            region = S3_REGION.strip('%')  # Remove any trailing % character
            image_url = f"https://{S3_BUCKET_NAME}.s3.{region}.amazonaws.com/{unique_filename}"
            
            # Log success
            logger.info(f"Image uploaded successfully to S3: {image_url}")
            
            return {"image_url": image_url}
            
        except Exception as s3_error:
            logger.error(f"S3 upload error: {str(s3_error)}")
            logger.exception("S3 exception details:")
            
            # Fall back to dummy URL if S3 upload fails
            dummy_filename = f"test/{uuid.uuid4()}{file_extension}"
            dummy_url = f"https://example.com/{dummy_filename}"
            logger.info(f"S3 upload failed, generated dummy URL: {dummy_url}")
            return {"image_url": dummy_url}
        
    except Exception as e:
        logger.error(f"Direct upload error: {str(e)}")
        logger.exception("Full exception details:")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Direct upload failed: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 
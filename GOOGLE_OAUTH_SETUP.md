# Setting Up Google OAuth for ChatGPT Clone

This guide provides step-by-step instructions for setting up Google OAuth to enable user authentication in the ChatGPT Clone application.

## Prerequisites

- A Google account
- Access to [Google Cloud Console](https://console.cloud.google.com/)

## Step 1: Create a New Google Cloud Project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Click on the project dropdown at the top of the page
3. Click "New Project"
4. Enter a project name (e.g., "ChatGPT Clone")
5. Select your organization (if applicable)
6. Click "Create"

## Step 2: Configure the OAuth Consent Screen

1. Select your newly created project
2. In the left sidebar, navigate to "APIs & Services" > "OAuth consent screen"
3. Choose "External" as the user type (unless you're developing for an organization)
4. Click "Create"

5. Fill in the required information:
   - App name: "ChatGPT Clone"
   - User support email: Your email address
   - Developer contact information: Your email address
   - Click "Save and Continue"

6. On the "Scopes" page:
   - Click "Add or Remove Scopes"
   - Select the following scopes:
     - `./auth/userinfo.email`
     - `./auth/userinfo.profile`
   - Click "Save and Continue"

7. On the "Test users" page:
   - Click "Add Users" and add your email
   - Click "Save and Continue"

8. Review your settings and click "Back to Dashboard"

## Step 3: Create OAuth Client ID

1. In the left sidebar, navigate to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "OAuth client ID"
3. For Application type, select "Web application"
4. Enter a name for the client (e.g., "ChatGPT Clone Web Client")
5. Under "Authorized JavaScript origins", add:
   - For local development: `http://localhost:8000`
   - For production: `https://yourdomain.com`

6. Under "Authorized redirect URIs", add:
   - For local development: `http://localhost:8000/auth/callback`
   - For production: `https://yourdomain.com/auth/callback`

7. Click "Create"
8. You'll see a modal with your client ID and client secret. Copy these values for use in the next step.

## Step 4: Configure Environment Variables

1. In your ChatGPT Clone project, copy the `env.example` file to `.env`:
   ```bash
   cp env.example .env
   ```

2. Edit the `.env` file and add your Google OAuth credentials:
   ```
   GOOGLE_CLIENT_ID=your_client_id_here
   GOOGLE_CLIENT_SECRET=your_client_secret_here
   ```

3. Make sure to set a strong SECRET_KEY for JWT token signing:
   ```
   SECRET_KEY=generate_a_strong_random_string_here
   ```

## Step 5: Testing the Authentication

1. Start your application:
   ```bash
   uvicorn main:app --reload
   ```

2. Open your browser and navigate to `http://localhost:8000`
3. Click the "Login with Google" button
4. You should be redirected to Google's authentication page
5. After authenticating, you should be redirected back to the application and logged in

## Troubleshooting

### Redirect URI Mismatch

If you see an error about a redirect URI mismatch, make sure the URI in your Google Cloud Console exactly matches the one your application is using.

### Invalid Client ID or Secret

Double-check that you've correctly copied the client ID and secret to your `.env` file.

### OAuth Consent Screen Not Showing

If you're using your own email for testing and not seeing the consent screen, this is normal. The consent screen appears for users who haven't previously authorized the application.

## Production Considerations

1. For production deployment, update the redirect URIs in the Google Cloud Console to your production domain.
2. Set the appropriate environment variables on your production server.
3. Consider enabling additional security features like domain verification. 
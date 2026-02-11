# Configuration Directory

This directory contains sensitive configuration files that should NOT be committed to git.

## Firebase Service Account Key

To enable Firebase Cloud Messaging (FCM) push notifications:

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project (or create a new one)
3. Go to **Project Settings** → **Service Accounts**
4. Click **"Generate New Private Key"**
5. Download the JSON file
6. Save it as `firebase-service-account.json` in this directory

**IMPORTANT:** Never commit this file to git. It's already in `.gitignore`.

## Environment Variables

Add these to your `.env` file:

```bash
# Firebase Cloud Messaging Configuration
FIREBASE_SERVICE_ACCOUNT_PATH=app/config/firebase-service-account.json
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_ENABLED=true
```

## Testing FCM

After setup:
1. Run database migration: `alembic upgrade head`
2. Start the backend: `python -m uvicorn app.main:app --reload`
3. Use the Android app to register an FCM token via `/api/notifications/fcm/register`
4. Start/stop a strategy to test push notifications

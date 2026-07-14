# Firebase Google Authentication Setup

This project now uses Firebase Google Sign-In for real Google account authentication.

## Firebase Console

1. Open Firebase Console and create/select a project.
2. Go to **Build > Authentication > Sign-in method**.
3. Enable **Google** provider.
4. Go to **Project settings > General > Your apps**.
5. Add a Web app and copy the Firebase config values.

## Environment Variables

Set these before running Flask:

```powershell
$env:FIREBASE_API_KEY="your-api-key"
$env:FIREBASE_AUTH_DOMAIN="your-project.firebaseapp.com"
$env:FIREBASE_PROJECT_ID="your-project-id"
$env:FIREBASE_APP_ID="your-web-app-id"
```

For admin Google login, set `ADMIN_EMAIL` to the exact Google account email allowed to enter admin:

```powershell
$env:ADMIN_EMAIL="your-admin@gmail.com"
```

If these variables are not set, the app keeps manual login/register available for local testing.

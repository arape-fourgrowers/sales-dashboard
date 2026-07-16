# Harvest Analytics Dashboard - Deployment Guide

## Deploy to Render.com (Recommended)

### Step 1: Prepare Your Repository
1. Push this code to GitHub (create a new repo)
2. **IMPORTANT**: Do NOT commit `credentials.json` - add it to `.gitignore`

### Step 2: Set Up Render
1. Go to https://render.com and sign up/login
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Configure:
   - **Name**: `harvest-analytics-dashboard`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn dashboard:server`
   - **Instance Type**: `Free` (or paid for better performance)

### Step 3: Add Environment Variables
In Render dashboard, add these environment variables:

**Option A: Upload credentials.json as a file**
1. Go to "Environment" tab
2. Add "Secret Files"
3. Upload `credentials.json`

**Option B: Use environment variable (Alternative)**
1. Convert credentials.json to base64:
   ```bash
   base64 -w 0 credentials.json
   ```
2. Add environment variable:
   - Key: `GOOGLE_CREDENTIALS_BASE64`
   - Value: (paste the base64 string)

Then update dashboard.py to decode it:
```python
import base64
import json
import os

if os.getenv('GOOGLE_CREDENTIALS_BASE64'):
    creds_data = base64.b64decode(os.getenv('GOOGLE_CREDENTIALS_BASE64'))
    with open('credentials.json', 'wb') as f:
        f.write(creds_data)
```

### Step 4: Deploy
1. Click "Create Web Service"
2. Wait for deployment (5-10 minutes)
3. Access your dashboard at the provided URL

---

## Deploy to Railway.app (Alternative)

1. Go to https://railway.app
2. Click "New Project" → "Deploy from GitHub repo"
3. Select your repository
4. Railway auto-detects Python and uses Procfile
5. Add `credentials.json` as environment file
6. Deploy!

---

## Deploy to Heroku (Alternative)

```bash
# Install Heroku CLI first
heroku login
heroku create harvest-analytics-dashboard
heroku config:set GOOGLE_CREDENTIALS_BASE64="$(base64 -w 0 credentials.json)"
git push heroku main
```

---

## Important Notes

- **Free tier limitations**: 
  - Render: 750 hours/month, sleeps after 15 min inactivity
  - Railway: 500 hours/month
  - Heroku: No free tier anymore (requires paid plan)

- **Data refresh**: Dashboard loads data on startup. To auto-refresh:
  - Use Render Cron Jobs (paid)
  - Or add `dcc.Interval` component to refresh periodically

- **Security**: Keep `credentials.json` secure - never commit to git!

# VIGILANT: FINAL 2 STEPS
## What's Left (Literally Just 2 Things)

Looking at your README: **You've already built 95% of the project!**

✅ Real Ring API — DONE  
✅ 7-day baseline chart — DONE  
✅ Alexa code written — DONE  

**What's left (literally just 2 things):**

1. **Deploy Alexa Lambda to AWS** (30-45 min)
2. **Setup Postgres on Vercel** (30 min)

---

# 🔴 FINAL TASK 1: DEPLOY ALEXA LAMBDA

## Current State
- Lambda code is written: `backend/alexa_integration/lambda_handler.py`
- Alexa client ready: `backend/alexa_integration/client.py`
- **But Lambda function not deployed to AWS yet**

## What You Need to Do

### Step 1: Open AWS Lambda Console

Go to: https://console.aws.amazon.com/lambda/

Click "Create function"

```
Configuration:
  Function name: vigilant-alexa-announcer
  Runtime: Python 3.11
  Role: Create new role with basic Lambda permissions
  Architecture: x86_64
```

Click "Create function"

---

### Step 2: Copy code into Lambda editor

Open your `backend/alexa_integration/lambda_handler.py`:

```python
import json
import os
from datetime import datetime

def lambda_handler(event, context):
    """
    Receives pattern alerts from VIGILANT backend
    Constructs voice message for Alexa
    """
    
    print(f"Received event: {json.dumps(event)}")
    
    try:
        # Parse incoming alert
        pattern = event.get('pattern', {})
        home_id = event.get('home_id', 'unknown')
        
        pattern_type = pattern.get('pattern_type', 'unknown')
        explanation = pattern.get('explanation', 'Security pattern detected')
        salience = pattern.get('salience', 0)
        
        # Construct voice message
        if salience > 8:
            urgency = "URGENT: "
        elif salience > 6:
            urgency = "Alert: "
        else:
            urgency = "Notification: "
        
        voice_message = f"{urgency}{explanation}"
        
        print(f"✓ Voice message: {voice_message}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': voice_message,
                'home_id': home_id,
                'pattern_type': pattern_type,
                'salience': salience,
                'timestamp': datetime.utcnow().isoformat()
            })
        }
    
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
```

In AWS Lambda console:
1. Delete the default code
2. Paste this code
3. Click "Deploy"

---

### Step 3: Test it in Lambda

In AWS Lambda console, click "Test"

Create new test event:

```json
{
  "pattern": {
    "pattern_type": "rapid_return",
    "explanation": "Someone returned home unusually quickly and entered via side door",
    "salience": 7.8
  },
  "home_id": "home_001"
}
```

Click "Test" → Should see **"Execution result: succeeded"** ✓

---

### Step 4: Get Lambda ARN

In Lambda console:
- Look for "Function ARN" at the top right
- Copy it (looks like: `arn:aws:lambda:us-east-1:123456789:function:vigilant-alexa-announcer`)

---

### Step 5: Enable Alexa in Vercel

```bash
vercel env add ALEXA_ENABLED
# When prompted, enter: true

vercel env add ALEXA_LAMBDA_FUNCTION
# When prompted, enter: vigilant-alexa-announcer

vercel env add AWS_LAMBDA_ARN
# When prompted, paste the ARN from Step 4

vercel --prod --yes
```

---

### Step 6: Test the integration

Once Vercel redeploys, send a test pattern:

```bash
curl -X POST "https://vigilant-backend-omega.vercel.app/patterns/score" \
  -H "Content-Type: application/json" \
  -d '{
    "home_id": "home_001",
    "events": [
      {"camera":"front_door","type":"person_detected","timestamp":"2026-09-26T14:30:00","confidence":0.95},
      {"camera":"side_door","type":"person_detected","timestamp":"2026-09-26T14:32:00","confidence":0.89}
    ]
  }'
```

In AWS Lambda console → "Monitor" tab → you should see an invocation ✓

---

## ✅ DONE: Alexa Lambda is deployed

Your backend now:
- Detects flagged patterns (salience ≥ 6)
- Invokes Lambda automatically
- Lambda can announce to Alexa
- Gracefully fails if Lambda is down (no breakage)

---

# 🟢 FINAL TASK 2: PERSISTENT POSTGRES

## Current State
- Live demo uses SQLite on `/tmp`
- Data resets every ~15 minutes
- Judges will see empty dashboard

## What You Need to Do

### Step 1: Create Supabase account (Free)

Go to: https://supabase.com

```
Sign up with GitHub
Create new project
  Name: vigilant
  Password: [choose strong password]
  Region: us-east-1
  
Wait for project to initialize (~2 min)
```

---

### Step 2: Get connection string

In Supabase dashboard:
1. Click your project
2. Go to "Settings" (bottom left)
3. Click "Database"
4. Under "Connection string", choose "URI"
5. Copy the full string

It looks like:
```
postgresql://postgres:YOUR_PASSWORD@db.XXXXX.supabase.co:5432/postgres
```

---

### Step 3: Add to Vercel

```bash
vercel env add DATABASE_URL
# When prompted, paste the Supabase connection string
# Select: Production environment
```

---

### Step 4: Redeploy

```bash
vercel --prod --yes
```

---

### Step 5: Verify it's working

```bash
curl https://vigilant-backend-omega.vercel.app/health
```

Should see:
```json
{
  "status": "ok",
  "database": "connected"
}
```

If you see `"database": "connected"`, you're done ✓

---

### Step 6: Seed demo data

```bash
curl -X POST "https://vigilant-backend-omega.vercel.app/demo/seed"
```

Now:
- Go to https://vigilant-frontend-lac.vercel.app
- Should see patterns + events
- **Reload the page after 20 minutes**
- **Data is still there** (not reset) ✓

---

## ✅ DONE: Data persists forever

Your live demo now:
- Uses real Postgres
- Data survives deployment
- Data survives cold starts
- Judges won't see empty dashboards

---

# 🎯 FINAL STATUS

| Task | Status | Time | Do This |
|------|--------|------|---------|
| Alexa Lambda Deploy | ⚠️ Code ready, not deployed | 30 min | Follow Task 1 above |
| Postgres Setup | ⚠️ Code ready, not connected | 30 min | Follow Task 2 above |
| **TOTAL TIME** | **~1 hour** | | **DO BOTH NOW** |

---

# 🚀 QUICK CHECKLIST

### Alexa Lambda (Do First)
- [ ] Go to AWS Lambda console
- [ ] Create function: `vigilant-alexa-announcer`
- [ ] Paste Python code
- [ ] Click Deploy
- [ ] Test with sample event → see "succeeded"
- [ ] Copy ARN
- [ ] Add to Vercel env: `ALEXA_ENABLED=true` + `AWS_LAMBDA_ARN=...`
- [ ] Redeploy: `vercel --prod --yes`
- ✓ DONE

### Postgres (Do Second)
- [ ] Go to Supabase.com → create account
- [ ] Create project → wait for init
- [ ] Copy connection string (URI format)
- [ ] `vercel env add DATABASE_URL` → paste string
- [ ] `vercel --prod --yes`
- [ ] Test: `curl /health` → see `"database": "connected"`
- [ ] `curl -X POST /demo/seed`
- [ ] Visit dashboard, reload after 20 min → data persists ✓ DONE

---

# 🎬 WHAT JUDGES WILL SEE NOW

**Before (current):**
```
❌ Dashboard shows data
❌ Reload page after 15 min
❌ Data is gone (SQLite reset)
❌ Looks like demo, not product
```

**After (1 hour of work):**
```
✅ Dashboard shows data
✅ Reload page anytime
✅ Data PERSISTS (Postgres)
✅ Alexa announces alerts
✅ Looks like real product
```

---

# 📋 FINAL SUBMISSION (Oct 24)

**Before deadline:**

1. Do Alexa Lambda (30 min)
2. Do Postgres (30 min)
3. Verify both work (15 min)
4. Record demo video (20 min)
5. Write submission (30 min)

**Total: ~2 hours**

Then you're done. Ready to submit.

---

# ⚠️ COMMON ISSUES

## Alexa Lambda fails to deploy

**Issue:** "Error creating execution role"
**Fix:** Use "Create new role" option, it auto-creates everything

**Issue:** Test returns "timeout"
**Fix:** Make sure you're in same AWS region as function (us-east-1)

---

## Postgres won't connect

**Issue:** "could not translate host name"
**Fix:** Make sure you copied the URI (not psql command)
- CORRECT: `postgresql://postgres:pass@db.xxx.supabase.co:5432/postgres`
- WRONG: `psql -U postgres...`

**Issue:** "permission denied for schema public"
**Fix:** Double-check password in connection string matches what you set in Supabase

**Issue:** Still doesn't work
**Alternative:** Use Neon (https://neon.tech) instead of Supabase, exact same process

---

# 🏁 YOU'RE ALMOST DONE

Your project went from:
- 90% done (Days 1-3)
- to 95% done (Days 4-28 you built everything)
- **to 99% done (just deploy Lambda + Postgres)**

**Do these 2 tasks, you're ready to win.** 🚀

---

# STEP-BY-STEP VIDEO SCRIPT (If you want to watch instead of read)

**Alexa Lambda Deploy (5 min):**
1. Open AWS Lambda console
2. Create function named `vigilant-alexa-announcer`
3. Paste Python code
4. Deploy
5. Test with sample event
6. Add to Vercel env
7. Redeploy Vercel

**Postgres Setup (5 min):**
1. Open Supabase.com
2. Create account + project
3. Copy connection string
4. `vercel env add DATABASE_URL`
5. `vercel --prod --yes`
6. Test health endpoint
7. Seed demo data

---

**Start now. You'll be done in 1 hour.** ✅

Then you have the rest of the time before Oct 24 to:
- Polish UI
- Record demo video
- Write friction log (+10% bonus!)
- Practice your pitch

Go. 🚀

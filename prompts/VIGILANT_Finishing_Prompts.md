# VIGILANT: FINISHING PROMPTS
## Complete Guide to Implementing Remaining Features

Your project is 90% done. These exact prompts will get you to 100% and make it polished enough to win.

---

# 📋 WHAT'S LEFT

| Feature | Priority | Effort | Impact | Prompt |
|---------|----------|--------|--------|--------|
| Real Ring API integration | High | Medium | Critical for judges | PROMPT A |
| 7-day baseline comparison chart | High | Medium | Impressive UI | PROMPT B |
| Alexa skill integration | Medium | High | Differentiator | PROMPT C |
| Persistent Postgres on Vercel | High | Low | Data persistence | PROMPT D |

---

# 🔴 PRIORITY ORDER

**Do these in order to maximize judges' first impression:**

1. **PROMPT D** (Postgres) — 30 minutes, critical
2. **PROMPT A** (Real Ring API) — 2-3 hours, judges will test
3. **PROMPT B** (Baseline chart) — 2-3 hours, impressive
4. **PROMPT C** (Alexa) — 4-6 hours, extra credit

---

# ⚡ PROMPT D: PERSISTENT POSTGRES ON VERCEL

**Why first:** Without this, your live demo resets every 15 minutes. Judges will see empty dashboards.

**Current state:** SQLite on `/tmp` (resets on cold start)
**Target state:** Data persists across deployments

---

## PROMPT D.1: Setup Supabase (5 minutes)

```
TASK: Set up free Postgres on Supabase for VIGILANT backend

CURRENT STATE:
- VIGILANT backend deployed on Vercel
- Uses SQLite on /tmp (data resets every ~15 min)
- Database URL currently NOT set

TARGET STATE:
- Supabase free Postgres connected
- Data persists across deployments
- No code changes needed

WHAT I NEED:
1. Step-by-step Supabase signup (free tier)
2. How to get connection string
3. How to add to Vercel environment variables
4. How to verify it's working
5. Connection string format for SQLAlchemy

Please provide exact URLs and CLI commands.
```

### Implementation

**Step 1: Create Supabase account**
```
Go to: https://supabase.com
Sign up with GitHub
Create new project
- Name: vigilant
- Password: [strong password]
- Region: us-east-1 (same as your Vercel region)
```

**Step 2: Get connection string**
```
In Supabase dashboard:
  Project Settings → Database → Connection string
  
Choose "URI" format
Copy the full string (looks like):
postgresql://postgres:YOUR_PASSWORD@db.RANDOM.supabase.co:5432/postgres
```

**Step 3: Add to Vercel**
```bash
vercel env add DATABASE_URL
# Paste connection string when prompted
# Select: Production environment
```

**Step 4: Redeploy**
```bash
vercel --prod --yes
```

**Step 5: Verify**
```bash
curl https://vigilant-backend-omega.vercel.app/health
# Should show ✓ without errors
```

---

## PROMPT D.2: If connection fails

```
CONTEXT:
I've set DATABASE_URL in Vercel but backend won't connect to Supabase Postgres.

ERROR (if you see this):
- Connection timeout
- "could not translate host name"
- SSL certificate errors

WHAT TO CHECK:
1. Is the connection string correct? (copy-paste from Supabase URI, not the psql command)
2. Is Supabase project active? (check Supabase dashboard)
3. Does connection string have password? (if blank, reset in Supabase Settings)

QUICK FIXES:
A) Copy exact URI from Supabase (not psql command):
   CORRECT: postgresql://postgres:password@db.xxx.supabase.co:5432/postgres
   WRONG:   psql -U postgres...

B) Add ?sslmode=require to end of URI if SSL errors:
   postgresql://postgres:pass@db.xxx.supabase.co:5432/postgres?sslmode=require

C) Restart connection:
   In Vercel dashboard → Redeploy (don't change code)

D) Check logs:
   vercel logs vigilant-backend --prod
   Look for database connection errors

If still failing, try Neon instead:
   https://neon.tech (easier to debug, same free tier)
```

---

## Code: No changes needed!

Your backend already handles both SQLite and Postgres. The connection string in `.env` automatically switches:

```python
# backend/database/session.py (already handles this)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Default to SQLite
    DATABASE_URL = "sqlite:///./vigilant.db"

engine = create_engine(DATABASE_URL)
```

**Just set the environment variable. That's it.**

---

# 🔵 PROMPT A: REAL RING API INTEGRATION

**Why it matters:** Judges will ask "Does this work with real Ring?" Current simulator is obvious.

**Current state:** `ring_integration/api_client.py` uses simulator (fires every 5 seconds)
**Target state:** Real Ring API or local device data

---

## PROMPT A.1: Choose your approach

```
CONTEXT:
VIGILANT currently uses a simulator for Ring events. Judges will test with real data.

THREE OPTIONS:

OPTION 1: ring_doorbell library (EASIEST, RECOMMENDED)
- Pure Python library to connect to Ring API
- No Ring hardware needed
- Works with Ring cameras you own OR sandbox account
- 15 minutes to implement
- Limitation: Needs Ring account email/password

OPTION 2: Ring Simulator + seed data (KEEP THIS)
- Keep existing simulator
- Pre-seed with realistic patterns
- Good for development
- Judges see "simulator" and know it's not production-ready

OPTION 3: Real Ring hardware + device setup (HARDEST)
- Requires physical Ring device
- Requires setup + testing
- 2-3 hours
- Best for final demo

RECOMMENDATION FOR HACKATHON:
Use OPTION 1 (ring_doorbell) as default, fallback to simulator if Ring account unavailable.

WHAT I NEED:
1. How to install ring_doorbell library
2. How to auth with Ring credentials
3. How to get real events from Ring API
4. How to swap simulator for real API with one env variable
5. How to handle errors gracefully (fallback to simulator)

Provide copy-paste code ready to use.
```

### Implementation: OPTION 1 (Recommended)

**Step 1: Install library**

```bash
pip install ring-doorbell
pip freeze > requirements.txt
```

**Step 2: Create `backend/ring_integration/real_api_client.py`**

```python
# backend/ring_integration/real_api_client.py
import asyncio
import os
from datetime import datetime
from typing import List, Dict, Optional
from ring_doorbell import Ring

class RealRingClient:
    """Connect to real Ring API (requires Ring account)"""
    
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.ring = None
        self.connected = False
    
    async def connect(self) -> bool:
        """Authenticate with Ring"""
        try:
            self.ring = Ring(self.email, self.password)
            await self.ring.async_update_data()
            self.connected = True
            print(f"✓ Connected to Ring as {self.email}")
            
            # Log available devices
            devices = self.ring.devices()
            print(f"✓ Found {len(devices)} Ring devices:")
            for device in devices:
                print(f"  - {device.name} ({device.kind})")
            
            return True
        except Exception as e:
            print(f"✗ Ring connection failed: {e}")
            self.connected = False
            return False
    
    async def get_events(self, limit: int = 50) -> List[Dict]:
        """Fetch recent Ring events"""
        if not self.connected:
            return []
        
        try:
            events = []
            
            # Get all devices
            for device in self.ring.devices():
                # Get last N events for this device
                if hasattr(device, 'history'):
                    for event in device.history(limit=limit):
                        events.append({
                            "id": f"{device.id}_{event.get('id', 'unknown')}",
                            "camera": device.name,
                            "type": self._map_event_type(event.get('kind')),
                            "timestamp": self._parse_timestamp(event.get('created_at')),
                            "confidence": 0.95,  # Ring doesn't give confidence, assume high
                            "raw_data": event
                        })
            
            return sorted(events, key=lambda x: x['timestamp'], reverse=True)
        
        except Exception as e:
            print(f"✗ Error fetching Ring events: {e}")
            return []
    
    def _map_event_type(self, ring_event_kind: str) -> str:
        """Map Ring event types to VIGILANT types"""
        mapping = {
            'motion': 'motion_detected',
            'person': 'person_detected',
            'vehicle': 'vehicle_detected',
            'doorbell': 'doorbell_pressed',
            'package': 'package_detected',
            'animal': 'animal_detected',
        }
        return mapping.get(ring_event_kind, 'unknown')
    
    def _parse_timestamp(self, timestamp_str: str) -> str:
        """Convert Ring timestamp to ISO format"""
        try:
            # Ring uses ISO format already
            return timestamp_str
        except:
            # Fallback to now
            return datetime.utcnow().isoformat()

# Usage example
async def main():
    email = os.getenv("RING_EMAIL", "your_email@gmail.com")
    password = os.getenv("RING_PASSWORD", "your_password")
    
    client = RealRingClient(email, password)
    if await client.connect():
        events = await client.get_events()
        print(f"Fetched {len(events)} events")
        for event in events[:5]:
            print(f"  - {event['timestamp']}: {event['camera']} - {event['type']}")
```

**Step 3: Modify `backend/ring_integration/api_client.py` to support both**

```python
# backend/ring_integration/api_client.py (updated)
import os
import asyncio
from typing import List, Dict

# Import both simulators
from .simulator import RingSimulator
from .real_api_client import RealRingClient

class RingClient:
    """Smart client that picks simulator or real API"""
    
    def __init__(self):
        self.use_simulator = os.getenv("RING_USE_SIMULATOR", "true").lower() == "true"
        self.client = None
        self.simulator = None
        self.real_client = None
    
    async def connect(self):
        """Try real Ring, fallback to simulator"""
        
        if self.use_simulator:
            print("🔵 Using Ring SIMULATOR (dev mode)")
            self.simulator = RingSimulator()
            return True
        
        # Try real Ring API
        email = os.getenv("RING_EMAIL")
        password = os.getenv("RING_PASSWORD")
        
        if not email or not password:
            print("⚠️  No RING_EMAIL/RING_PASSWORD found. Falling back to SIMULATOR.")
            self.use_simulator = True
            self.simulator = RingSimulator()
            return True
        
        print("🟢 Attempting real Ring API connection...")
        self.real_client = RealRingClient(email, password)
        
        if await self.real_client.connect():
            print("✓ Connected to real Ring API")
            return True
        else:
            print("✗ Real Ring failed. Falling back to SIMULATOR.")
            self.use_simulator = True
            self.simulator = RingSimulator()
            return True
    
    async def get_events(self) -> List[Dict]:
        """Get events from real API or simulator"""
        if self.use_simulator and self.simulator:
            return self.simulator.get_event_stream()
        elif self.real_client and self.real_client.connected:
            return await self.real_client.get_events()
        else:
            return []
```

**Step 4: Update `.env.example`**

```bash
# Ring Configuration
RING_USE_SIMULATOR=false          # Set to 'true' for dev mode (always uses simulator)
RING_EMAIL=your-ring-email@gmail.com
RING_PASSWORD=your-ring-password

# To use real Ring: Set RING_USE_SIMULATOR=false and add credentials
# To use simulator: Set RING_USE_SIMULATOR=true (credentials ignored)
```

**Step 5: Test it**

```bash
# Development (simulator)
export RING_USE_SIMULATOR=true
python -m backend.main
# Should fire events every 5 seconds

# Production (real Ring, if credentials available)
export RING_USE_SIMULATOR=false
export RING_EMAIL=your@email.com
export RING_PASSWORD=your_password
python -m backend.main
# Should connect to your Ring account
```

**Step 6: Update Vercel environment**

```bash
vercel env add RING_USE_SIMULATOR
# Value: false

vercel env add RING_EMAIL
# Value: your-ring-email@gmail.com

vercel env add RING_PASSWORD
# Value: your-ring-password
```

Then redeploy:
```bash
vercel --prod --yes
```

---

## Testing Ring integration

```python
# Quick test: backend/test_ring_integration.py
import asyncio
from ring_integration.api_client import RingClient

async def test():
    client = RingClient()
    await client.connect()
    
    events = await client.get_events()
    print(f"Got {len(events)} events")
    
    for event in events[:3]:
        print(f"  {event['timestamp']}: {event['camera']} - {event['type']}")

if __name__ == "__main__":
    asyncio.run(test())
```

Run:
```bash
python backend/test_ring_integration.py
```

---

# 🟣 PROMPT B: 7-DAY BASELINE COMPARISON CHART

**Why it matters:** Shows judges you understand the data. Impressive visual.

**Current state:** Dashboard shows events + patterns separately
**Target state:** Chart showing "this week vs. baseline" for each camera

---

## PROMPT B.1: Backend endpoint

```
CONTEXT:
VIGILANT dashboard currently shows detected patterns and raw events.

NEW FEATURE: 7-day baseline comparison chart

What it shows:
- X-axis: Day of week (Mon, Tue, ..., Sun)
- Y-axis: Activity level (0-100 scale)
- Two lines: 
  1. Baseline (what's normal)
  2. This week (what actually happened)
- Shaded area between shows deviation

EXAMPLE:
Monday baseline: 15 events/day (normal)
This week Monday: 42 events/day (unusual)
Chart shows 42 above baseline with shading → user sees "unusually busy Monday"

BACKEND NEEDS:
1. New API endpoint: GET /baseline-comparison?home_id=&days=7
2. Return format:
   {
     "days": [
       {
         "date": "2026-09-20",
         "day_name": "Saturday",
         "baseline_activity": 18,
         "actual_activity": 22,
         "flags_count": 2
       },
       ...
     ]
   }
3. Activity level = (number_of_events / peak_day) * 100
4. Include only last 7 days

HOW TO CALCULATE:
1. Query baselines table for home_id
2. Average events per day from historical data
3. Query events table for last 7 days
4. Calculate actual activity per day
5. Return both

CONSTRAINTS:
- Must run in < 100ms
- Handle homes with < 7 days history (show partial)
- Handle homes with no activity (show flat line)

Provide:
1. API endpoint code (FastAPI)
2. Database query logic
3. Format for frontend consumption
4. Example response
```

### Implementation

**Step 1: Add to `backend/database/repository.py`**

```python
# backend/database/repository.py (add this method)

def get_baseline_comparison(self, home_id: str, days: int = 7) -> Dict:
    """Get activity comparison: baseline vs. this week"""
    
    from datetime import datetime, timedelta
    from sqlalchemy import func
    
    # Get last N days
    now = datetime.utcnow()
    start_date = now - timedelta(days=days)
    
    # Query: events grouped by day
    daily_activity = self.db.query(
        func.date(RingEvent.timestamp).label('date'),
        func.count(RingEvent.id).label('event_count'),
        func.count(
            case(
                (Pattern.salience >= 6.0, 1),
                else_=None
            )
        ).label('flags_count')
    ).outerjoin(
        Pattern,
        (func.date(RingEvent.timestamp) == func.date(Pattern.created_at)) &
        (Pattern.home_id == home_id)
    ).filter(
        RingEvent.home_id == home_id,
        RingEvent.timestamp >= start_date
    ).group_by(
        func.date(RingEvent.timestamp)
    ).all()
    
    # Get baseline (average from all historical data)
    baseline_data = self.db.query(
        func.date(RingEvent.timestamp).label('date'),
        func.count(RingEvent.id).label('event_count')
    ).filter(
        RingEvent.home_id == home_id
    ).group_by(
        func.date(RingEvent.timestamp)
    ).all()
    
    baseline_avg = (
        sum(row.event_count for row in baseline_data) / len(baseline_data)
        if baseline_data
        else 0
    )
    
    # Calculate activity level (0-100 scale)
    max_activity = max(
        [row.event_count for row in daily_activity] + [baseline_avg * 1.5],
        default=10
    )
    
    # Format response
    days_data = []
    for date_val in [start_date + timedelta(days=i) for i in range(days)]:
        # Find actual activity for this day
        actual_count = next(
            (row.event_count for row in daily_activity if row.date == date_val.date()),
            0
        )
        flags_count = next(
            (row.flags_count for row in daily_activity if row.date == date_val.date()),
            0
        )
        
        # Normalize to 0-100
        actual_level = (actual_count / max(max_activity, 1)) * 100
        baseline_level = (baseline_avg / max(max_activity, 1)) * 100
        
        days_data.append({
            "date": date_val.strftime("%Y-%m-%d"),
            "day_name": date_val.strftime("%A"),
            "baseline_activity": round(baseline_level, 1),
            "actual_activity": round(actual_level, 1),
            "flags_count": flags_count or 0,
            "event_count": actual_count
        })
    
    return {
        "home_id": home_id,
        "baseline_avg": round(baseline_avg, 1),
        "period_days": days,
        "days": days_data
    }
```

**Step 2: Add API endpoint to `backend/api/routes.py`**

```python
# backend/api/routes.py (add this route)

@router.get("/baseline-comparison")
async def get_baseline_comparison(
    home_id: str = "home_001",
    days: int = 7,
    db: Session = Depends(get_db)
):
    """Get 7-day activity comparison: baseline vs. actual"""
    
    repo = Repository(db)
    
    try:
        comparison = repo.get_baseline_comparison(home_id, days)
        return comparison
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
```

**Step 3: Test it**

```bash
curl "http://localhost:8000/baseline-comparison?home_id=home_001&days=7"
```

Expected response:
```json
{
  "home_id": "home_001",
  "baseline_avg": 18.5,
  "period_days": 7,
  "days": [
    {
      "date": "2026-09-20",
      "day_name": "Saturday",
      "baseline_activity": 42.3,
      "actual_activity": 38.2,
      "flags_count": 1,
      "event_count": 8
    },
    ...
  ]
}
```

---

## PROMPT B.2: Frontend chart component

```
CONTEXT:
Backend now provides baseline-comparison data.

Need React component to visualize:
- 7-day line chart
- Two lines: baseline (dashed grey) vs. actual (solid blue/red)
- Shaded area between showing deviation
- Hover shows exact numbers
- Flags appear as small badges

REQUIREMENTS:
- Library: Recharts (already in package.json)
- Colors: baseline=grey, actual=blue, deviation area=light blue
- Responsive: works on mobile + desktop
- Real-time: updates when new patterns arrive

CODE NEEDED:
1. React component with Recharts LineChart
2. Hook to fetch data from backend
3. Color logic: if actual > baseline = red, else = green
4. Hover tooltip showing all values

Provide:
1. Complete component code (copy-paste ready)
2. How to integrate into App.jsx
3. Styling with Tailwind
4. Error handling (empty data, API down)
```

### Implementation

**Step 1: Create `frontend/src/components/BaselineComparison.jsx`**

```jsx
// frontend/src/components/BaselineComparison.jsx
import React, { useEffect, useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ComposedChart, Area, AreaChart
} from 'recharts';
import { fetchAPI } from '../utils/api';

export function BaselineComparison({ homeId = 'home_001' }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchComparison = async () => {
      try {
        const response = await fetchAPI(`/baseline-comparison?home_id=${homeId}&days=7`);
        setData(response.days || []);
        setError(null);
      } catch (err) {
        setError(err.message);
        setData([]);
      } finally {
        setLoading(false);
      }
    };

    fetchComparison();
    
    // Re-fetch every 5 minutes
    const interval = setInterval(fetchComparison, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [homeId]);

  if (loading) return <div className="text-center py-8">Loading baseline...</div>;
  if (error) return <div className="text-red-500 text-center py-8">{error}</div>;
  if (!data.length) return <div className="text-center py-8 text-gray-500">No data yet</div>;

  return (
    <div className="w-full bg-white p-6 rounded-lg shadow">
      <h3 className="text-lg font-bold mb-4">7-Day Activity Comparison</h3>
      
      <div className="w-full h-80 overflow-x-auto">
        <AreaChart
          width={Math.max(600, data.length * 100)}
          height={300}
          data={data}
          margin={{ top: 10, right: 30, left: 0, bottom: 50 }}
        >
          <defs>
            <linearGradient id="colorDeviation" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#93c5fd" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#93c5fd" stopOpacity={0} />
            </linearGradient>
          </defs>
          
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          
          <XAxis
            dataKey="day_name"
            angle={-45}
            textAnchor="end"
            height={80}
            tick={{ fontSize: 12 }}
          />
          
          <YAxis
            label={{ value: 'Activity Level', angle: -90, position: 'insideLeft' }}
            domain={[0, 100]}
          />
          
          <Tooltip
            contentStyle={{
              backgroundColor: '#fff',
              border: '1px solid #ccc',
              borderRadius: '4px'
            }}
            formatter={(value) => value.toFixed(1)}
            labelFormatter={(label) => `Day: ${label}`}
          />
          
          <Legend
            verticalAlign="bottom"
            height={36}
            wrapperStyle={{ paddingTop: '20px' }}
          />
          
          {/* Shaded area showing deviation */}
          <Area
            type="monotone"
            dataKey="baseline_activity"
            dataKey2="actual_activity"
            stroke="transparent"
            fill="url(#colorDeviation)"
            name="Deviation"
            isAnimationActive={false}
          />
          
          {/* Baseline line (dashed grey) */}
          <Line
            type="monotone"
            dataKey="baseline_activity"
            stroke="#9ca3af"
            strokeDasharray="5 5"
            strokeWidth={2}
            dot={{ r: 4 }}
            name="Baseline"
            isAnimationActive={false}
          />
          
          {/* Actual activity (solid, color-coded) */}
          <Line
            type="monotone"
            dataKey="actual_activity"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={(props) => {
              const { cx, cy, payload } = props;
              const isAboveBaseline = payload.actual_activity > payload.baseline_activity;
              return (
                <circle
                  cx={cx}
                  cy={cy}
                  r={5}
                  fill={isAboveBaseline ? '#ef4444' : '#10b981'}
                  stroke="#fff"
                  strokeWidth={2}
                />
              );
            }}
            name="Actual Activity"
            isAnimationActive={false}
          />
        </AreaChart>
      </div>

      {/* Stats below chart */}
      <div className="mt-6 grid grid-cols-3 gap-4 text-center">
        {data.map((day) => (
          <div key={day.date} className="p-3 bg-gray-50 rounded">
            <div className="text-sm font-semibold text-gray-700">{day.day_name}</div>
            <div className="text-xs text-gray-500">{day.date}</div>
            {day.flags_count > 0 && (
              <div className="text-xs mt-1">
                <span className="inline-block bg-red-100 text-red-700 px-2 py-1 rounded">
                  {day.flags_count} flags
                </span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
```

**Step 2: Add to `frontend/src/App.jsx`**

```jsx
// frontend/src/App.jsx (import at top)
import { BaselineComparison } from './components/BaselineComparison';

// In your component (e.g., in a new tab or below patterns):
export default function App() {
  return (
    <div className="min-h-screen bg-gray-100">
      {/* ... existing code ... */}
      
      {/* Add this section */}
      <div className="p-6">
        <BaselineComparison homeId="home_001" />
      </div>
      
      {/* ... rest ... */}
    </div>
  );
}
```

**Step 3: Test it**

```bash
npm run dev
# Navigate to dashboard
# Should see 7-day comparison chart
```

---

# 🟠 PROMPT C: ALEXA SKILL INTEGRATION

**Why it matters:** Major differentiator. Shows multi-device thinking.

**Current state:** VIGILANT detects patterns, explains them via dashboard
**Target state:** Alexa announces significant patterns via voice

---

## PROMPT C.1: Alexa custom skill scaffolding

```
CONTEXT:
VIGILANT detects security patterns (person returned unusually soon, etc.).

NEW FEATURE: Alexa announces important patterns to homeowner

When pattern is detected + flagged (salience ≥ 7):
- Bedrock generates explanation
- Send to Alexa skill
- Alexa announces: "Your home alert: {explanation}"

REQUIREMENTS:
1. Alexa custom skill (not Smart Home API)
2. Lambda backend handles slash commands from VIGILANT
3. Two-way: Alexa can ask status ("How many alerts today?")
4. User must opt-in / enable skill on Alexa device

ARCHITECTURE:
  VIGILANT backend detects pattern
    ↓
  Publishes to Lambda trigger (AWS SNS or direct invocation)
    ↓
  Lambda calls Alexa.speak_to_user_device()
    ↓
  Alexa Device announces message
    ↓
  User hears: "Ring alert: Person returned unusually soon, entered through side door"

HOW TO IMPLEMENT:
1. Create Lambda function for Alexa integration
2. Enable Alexa Skills Kit (ASK)
3. Create custom skill with intents
4. Wire VIGILANT backend to trigger Lambda
5. Handle opt-in (user enables skill on Alexa app)

CONSTRAINTS:
- Must be free tier (hackathon)
- No payment methods
- Skill must be sandbox-only (not published to Alexa store)
- Voice output only (no visual cards needed)

WHAT I NEED:
1. Step-by-step Alexa skill creation
2. Lambda code for pattern announcements
3. How to call Lambda from VIGILANT backend
4. How to test without Alexa device (simulator)
5. How to handle failure gracefully (silent fail if Alexa unavailable)

Provide exact code + AWS console steps.
```

### Implementation: Part 1 - Lambda Function

**Step 1: Create Lambda function**

Go to [AWS Lambda Console](https://console.aws.amazon.com/lambda)

```
Create function
  Name: vigilant-alexa-announcer
  Runtime: Python 3.11
  Role: Create new role with basic Lambda execution
  
Then use this code:
```

**Step 2: `backend/alexa_integration/lambda_handler.py`**

```python
# This code goes into AWS Lambda (or can be run locally for testing)
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
        
        voice_message = f"{urgency} {explanation}"
        
        # Log for debugging
        print(f"✓ Constructed voice message: {voice_message}")
        
        # In production: Call Alexa device via ASK API
        # For now: Just return success (Alexa device integration happens in next step)
        
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

**Step 3: Copy this into AWS Lambda editor**

In [Lambda Console](https://console.aws.amazon.com/lambda):
- Open `vigilant-alexa-announcer` function
- Delete default code
- Paste code from Step 2
- Click "Deploy"

**Step 4: Test the Lambda**

In Lambda Console, click "Test":

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

Click "Test" → should see ✓ success with voice message

---

### Implementation: Part 2 - Call Lambda from VIGILANT

**Step 5: Create `backend/alexa_integration/client.py`**

```python
# backend/alexa_integration/client.py
import json
import boto3
import os
from typing import Dict, Optional

class AlexaClient:
    """Send pattern alerts to Alexa device via Lambda"""
    
    def __init__(self):
        self.lambda_client = boto3.client('lambda', region_name='us-east-1')
        self.lambda_name = os.getenv('ALEXA_LAMBDA_FUNCTION', 'vigilant-alexa-announcer')
        self.enabled = os.getenv('ALEXA_ENABLED', 'false').lower() == 'true'
    
    def send_alert(self, home_id: str, pattern: Dict) -> bool:
        """Send pattern alert to Alexa"""
        
        if not self.enabled:
            print("⚠️  Alexa integration disabled (set ALEXA_ENABLED=true to enable)")
            return False
        
        try:
            # Only send high-salience patterns
            salience = pattern.get('salience', 0)
            if salience < 6.0:
                print(f"Pattern salience {salience} too low for Alexa (need > 6)")
                return False
            
            payload = {
                'home_id': home_id,
                'pattern': {
                    'pattern_type': pattern.get('pattern_type'),
                    'explanation': pattern.get('explanation', 'Pattern detected'),
                    'salience': salience
                }
            }
            
            # Invoke Lambda
            response = self.lambda_client.invoke(
                FunctionName=self.lambda_name,
                InvocationType='Event',  # Asynchronous (don't wait for response)
                Payload=json.dumps(payload)
            )
            
            print(f"✓ Sent alert to Alexa Lambda: {self.lambda_name}")
            return True
        
        except Exception as e:
            print(f"✗ Alexa alert failed (graceful fail): {e}")
            # Silently fail — don't break VIGILANT if Alexa is down
            return False
```

**Step 6: Call from MOTIF engine**

In `backend/api/routes.py`, add after pattern is scored:

```python
from backend.alexa_integration.client import AlexaClient

# At top of function that processes patterns
alexa_client = AlexaClient()

# After you detect and save a flagged pattern:
if pattern.flagged and pattern.salience >= 6.0:
    # Send to Alexa
    alexa_client.send_alert(home_id, {
        'pattern_type': pattern.pattern_type,
        'explanation': pattern.explanation,
        'salience': pattern.salience
    })
```

**Step 7: Update `.env.example`**

```bash
# Alexa Integration
ALEXA_ENABLED=false
ALEXA_LAMBDA_FUNCTION=vigilant-alexa-announcer

# AWS credentials (for Lambda invocation)
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_DEFAULT_REGION=us-east-1
```

**Step 8: Update Vercel**

```bash
vercel env add ALEXA_ENABLED
# Value: true (or false to disable)

vercel env add ALEXA_LAMBDA_FUNCTION
# Value: vigilant-alexa-announcer
```

Then redeploy:
```bash
vercel --prod --yes
```

---

### Implementation: Part 3 - Full Alexa Skill (Optional, Advanced)

This is the hard part. If you have time:

**Create Alexa custom skill (for voice intents like "Alexa, ask Vigilant for my alerts")**

```
Go to https://developer.amazon.com/alexa/console/ask
Create new skill
  Name: Vigilant
  Model: Custom
  Backend resource: Lambda
  
  Use Lambda ARN from Step 1
  
Create intents:
  - "ask for alerts" → returns today's flagged patterns
  - "what's my security status" → returns summary
  - "acknowledge alert" → marks pattern as seen
```

This requires more setup. **For hackathon, Part 2 (Lambda announcements) is sufficient to impress.**

---

# 📝 IMPLEMENTATION CHECKLIST

## Before Submission (Oct 24)

### Must Have (Week 1-2)
- [ ] **PROMPT D**: Postgres connected (data persists)
  - [ ] Supabase account created
  - [ ] DATABASE_URL set in Vercel
  - [ ] Backend redeployed
  - [ ] Verify: curl `/health` shows DB connected

- [ ] **PROMPT A**: Real Ring API or polished simulator
  - [ ] `ring_doorbell` installed OR simulator marked as "dev only"
  - [ ] `.env` has RING_USE_SIMULATOR flag
  - [ ] Falls back gracefully if Ring unavailable
  - [ ] Test: `/events` endpoint returns data

### Nice to Have (Week 2-3)
- [ ] **PROMPT B**: 7-day baseline comparison chart
  - [ ] Backend endpoint `/baseline-comparison` working
  - [ ] Frontend component rendering chart
  - [ ] Mobile responsive
  - [ ] Colors show baseline vs. actual

### Extra Credit (Week 3-4)
- [ ] **PROMPT C**: Alexa skill integration
  - [ ] Lambda function created
  - [ ] VIGILANT can invoke Lambda
  - [ ] Graceful fallback if Alexa unavailable
  - [ ] Test on actual Alexa device (if you have one)

---

# 🎯 TIME ESTIMATES

| Feature | Time | Priority |
|---------|------|----------|
| PROMPT D (Postgres) | 30 min | 🔴 Must |
| PROMPT A (Ring API) | 2-3 hrs | 🔴 Must |
| PROMPT B (Chart) | 2-3 hrs | 🟡 Should |
| PROMPT C (Alexa) | 4-6 hrs | 🟢 Nice |

**Total to MVP: 5-6 hours**
**Total to polished: 9-12 hours**

---

# 🚀 FINAL SUBMISSION SCRIPT

**Oct 24 @ 11:59 PM (1 minute before deadline):**

```bash
# 1. Make sure everything is committed
git add -A
git commit -m "Final submission: VIGILANT complete"
git push origin main

# 2. Verify live deployment
curl https://vigilant-backend-omega.vercel.app/health
curl https://vigilant-frontend-lac.vercel.app

# 3. Seed demo data
curl -X POST "https://vigilant-backend-omega.vercel.app/demo/seed"

# 4. Test all features
# - Visit dashboard
# - See patterns + explanations
# - See 7-day chart
# - See baseline comparison

# 5. Submit on Devpost with:
# - Live dashboard link
# - GitHub repo link
# - 2-3 min demo video (showing MOTIF algorithm + Bedrock explanation)
# - Product feedback (filled from prompts)
# - Friction log (10+ entries for +10% bonus)
```

---

**Your VIGILANT project is 90% done. These prompts will make it 100%. Go finish strong.** 🚀

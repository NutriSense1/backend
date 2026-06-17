# NutriSense Backend — Setup Guide

This is a FastAPI backend that powers the NutriSense Flutter app: AI food
scanning (Gemini), nutrition lookup (Open Food Facts), Firebase auth
verification, and a Supabase Postgres database.

## What you need to do, in order

### 1. Database — Supabase

1. Open your Supabase project dashboard.
2. Go to **SQL Editor > New Query**.
3. Paste the entire contents of `app/db/migrations/001_initial_schema.sql`
   and click **Run**. This creates every table, index, and the default
   achievement catalog.
4. Go to **Project Settings > API**. Copy two values:
   - **Project URL** → this is `SUPABASE_URL`
   - **service_role key** (NOT the `anon` key — the secret one) → this is
     `SUPABASE_SERVICE_ROLE_KEY`

The service_role key bypasses Row Level Security and has full database
access. It must never be shipped inside the Flutter app — it only lives
on the backend.

### 2. AI — Gemini

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Click **Get API Key > Create API Key**.
3. Copy it → this is `GEMINI_API_KEY`.

### 3. Auth — Firebase

1. Open your Firebase project console.
2. Go to **Project Settings (gear icon) > Service Accounts**.
3. Click **Generate New Private Key**. This downloads a JSON file —
   keep it secret, never commit it to git.
4. You'll paste the *entire content* of that file into the
   `FIREBASE_SERVICE_ACCOUNT_JSON` environment variable (see step 4).
5. Also, in Firebase Console, go to **Authentication > Sign-in method**
   and enable **Email/Password** (and **Google**, if you want the
   "Continue with Google" button in the app to actually work).

### 4. Configure environment variables

Copy `.env.example` to `.env` and fill in the four values you just
collected:

```bash
cp .env.example .env
```

Edit `.env`:
```
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJxxxxx...
FIREBASE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"nutrisense-xxxxx",...}
GEMINI_API_KEY=AIzaxxxxx...
```

### 5. Run locally first (recommended before deploying)

```bash
python -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000/docs` — this is FastAPI's auto-generated
Swagger UI. You can test every endpoint here, though most require a
real Firebase ID token in the Authorization header (see "Getting a test
token" below).

Visit `http://localhost:8000/health` — should return `{"status": "healthy"}`.
If this fails, your Supabase or Firebase credentials are likely wrong —
check the terminal logs for the exact error.

### 6. Deploy to Render

1. Push this `nutrisense-backend` folder to a GitHub repo.
2. In the Render dashboard: **New > Web Service**, connect that repo.
3. Render will detect `render.yaml` automatically. If not, set manually:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Under **Environment**, add the same 4 variables from your `.env`
   file (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
   `FIREBASE_SERVICE_ACCOUNT_JSON`, `GEMINI_API_KEY`). Paste the Firebase
   JSON as a single environment variable value — Render's env var
   editor supports multi-line values fine.
5. Deploy. Render gives you a URL like
   `https://nutrisense-api.onrender.com`.
6. Update the Flutter app's `lib/core/constants/app_constants.dart`:
   ```dart
   static const String baseUrl = 'https://nutrisense-api.onrender.com/api/v1';
   ```

Note: Render's free/starter tier spins down when idle, so the first
request after inactivity can take 30-50 seconds to "wake up." This is
normal and not a bug in the code.

### 7. Getting a test Firebase ID token (for manual API testing)

The Flutter app gets this automatically via `FirebaseAuth`, but to test
the API directly with `curl` or Swagger UI before the app is wired up:

1. In Firebase Console, enable Email/Password auth (done in step 3).
2. Use the [Firebase Auth REST API](https://firebase.google.com/docs/reference/rest/auth)
   to sign up a test user:
   ```bash
   curl -X POST "https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=YOUR_FIREBASE_WEB_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"email":"test@example.com","password":"testpass123","returnSecureToken":true}'
   ```
   (Find `YOUR_FIREBASE_WEB_API_KEY` in Firebase Console > Project
   Settings > General > Web API Key.)
3. The response includes an `idToken` — use that as your Bearer token:
   ```bash
   curl -X POST "http://localhost:8000/api/v1/users/onboarding" \
     -H "Authorization: Bearer <idToken>" \
     -H "Content-Type: application/json" \
     -d '{"name":"Test User","age":28,"gender":"Male","height_cm":175,"weight_kg":75,"goal_weight_kg":70,"activity_level":"Moderately Active","goal":"Lose Weight"}'
   ```

## API overview

All routes are under `/api/v1` and (except onboarding's first call)
require `Authorization: Bearer <firebase_id_token>`.

| Method | Route | Purpose |
|---|---|---|
| POST | `/users/onboarding` | Create profile after signup |
| GET | `/users/me` | Get current profile |
| PATCH | `/users/me` | Update profile (recalculates targets if weight/goal changes) |
| POST | `/scan` | The flagship: photo → Gemini → OFF → health score → verdict |
| POST | `/food-logs` | Log a food item to a meal |
| GET | `/food-logs?date=` | Get logs for a day |
| DELETE | `/food-logs/{id}` | Remove a log |
| POST | `/weight-logs` | Log weight |
| GET | `/weight-logs?days=30` | Weight history |
| POST | `/water-logs` | Log water |
| GET | `/water-logs/today` | Today's water total |
| POST | `/step-logs/sync` | Sync steps from Health Connect/HealthKit |
| GET | `/ai/daily-review` | AI-generated daily summary |
| POST | `/ai/coach/chat` | Chat with the AI coach |
| GET | `/analytics/weekly` | Weekly report (calories, scores, consistency) |
| GET | `/achievements` | Full achievement catalog + unlock state |

## Architecture notes

- **Why Supabase service_role key instead of RLS policies?** FastAPI is
  the only thing that talks to Supabase. Firebase already verifies who
  the user is on every request (`get_current_user` dependency), so the
  backend enforces access control in Python rather than in Postgres
  policies. RLS is still enabled on every table as a safety net, but no
  public policies are defined, so the `anon` key (if ever leaked) can't
  read or write anything.
- **Why is health score calculated in Python, not just trusted from
  Gemini?** Gemini identifies food and estimates nutrition, but the
  actual 0-100 score is a deterministic formula (see
  `app/services/nutrition_calculator.py`) applied to real numbers. This
  keeps scoring consistent and auditable rather than letting the LLM
  make up a score.
- **Why Open Food Facts before trusting Gemini's nutrition guess?**
  Gemini's visual estimate of calories/macros from a photo is
  reasonable but imprecise. If the item is a packaged product with a
  barcode or matchable name, OFF's database gives real manufacturer
  nutrition facts, which is far more accurate.

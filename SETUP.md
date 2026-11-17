# Setup (about 30 minutes, once)

You'll collect 7 secrets and paste them into GitHub. Never share them in chat or email.

## 1. GitHub repository
1. github.com → **New repository** → name `bijli-bot` → **Public** → Create.
   *Public is needed: the cover images are served from the repo through jsDelivr, and public repos
   get free unlimited Action minutes (a private repo would run out at hourly runs). No secrets live
   in the code; they're stored in GitHub Secrets, which nobody can read.*
2. Upload every file from this folder (keep the folder structure, including `.github/workflows/trends.yml`).

## 2. AI keys (both free, no card)
1. **Groq:** console.groq.com → sign up → **API Keys → Create API Key** → copy → `GROQ_API_KEY`.
2. **Mistral:** console.mistral.ai → sign up → choose the free **Experiment** plan (it may ask to verify a
   phone number) → **API Keys → Create new key** → copy → `MISTRAL_API_KEY`.

## 3. Google Cloud project + Blogger API
1. **console.cloud.google.com** → project menu → **New project** → name `bijli-bot` → Create.
2. Search for **Blogger API v3** → **Enable**.
3. **APIs & Services → OAuth consent screen** (Google Auth Platform):
   - User type **External**, app name `Bijli Bot`, your email as support and developer email.
   - Scopes: you can skip.
   - **Audience → Publish app → In production.** Important: in "Testing" mode the login expires
     after 7 days and the bot stops. You don't need Google verification for your own account;
     you'll just see an "unverified app" warning once.
4. **Clients → Create client** → type **Web application** → name `bijli-bot`.
   Under **Authorized redirect URIs** add exactly: `https://developers.google.com/oauthplayground`
   → Create. Copy **Client ID** → `GOOGLE_CLIENT_ID`, **Client secret** → `GOOGLE_CLIENT_SECRET`.

## 4. Refresh token (lets the bot post as you)
1. Open **developers.google.com/oauthplayground**.
2. Click the ⚙️ gear (top right) → tick **Use your own OAuth credentials** → paste Client ID and secret.
3. In the left box "Input your own scopes" type `https://www.googleapis.com/auth/blogger` → **Authorize APIs**.
4. Sign in with the Google account that owns bijlinews → Advanced → "Go to Bijli Bot (unsafe)" → Allow.
5. Click **Exchange authorization code for tokens** → copy **Refresh token** → `GOOGLE_REFRESH_TOKEN`.

## 5. Gmail app password (for the emails)
1. The sending Gmail account needs 2-Step Verification on.
2. **myaccount.google.com/apppasswords** → name `bijli-bot` → Create → copy the 16 letters → `SMTP_PASS`.
3. That Gmail address → `SMTP_USER`. The address that should receive reports → `NOTIFY_TO`.

## 6. Put the secrets in GitHub
Repo → **Settings → Secrets and variables → Actions → New repository secret**, one by one:
`GROQ_API_KEY`, `MISTRAL_API_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`,
`SMTP_USER`, `SMTP_PASS`, `NOTIFY_TO`.

## 7. Test, then go live
1. **Actions → Bijli trend articles → Run workflow → tick "Dry run" → Run.** When it finishes, download
   the `dry-run-articles` file at the bottom of the run page and read the articles. Nothing is posted.
2. Run again **without** dry run. `PUBLISH_MODE` defaults to `draft`, so it only creates drafts and emails you.
   Let it run like this for 2–3 days and judge the quality.
3. Happy? **Settings → Secrets and variables → Actions → Variables → New variable**
   `PUBLISH_MODE` = `auto`. From the next hour, articles that pass every check are published.
   (Before this step, the editorial policy on the site must be updated to describe auto-publishing.)

To stop the bot at any time: **Actions → Bijli trend articles → ⋯ → Disable workflow.**

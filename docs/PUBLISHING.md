# Publishing shorts — YouTube, TikTok, Facebook, Instagram

Each generated short can be published in two modes:

- **API** — fully programmatic upload via the platform's Content Posting API. One-click, but requires a developer app registered on that platform and OAuth set up.
- **Browser (assisted)** — opens the platform's upload page in your browser and copies the file path + caption to your clipboard. No API setup needed. Works for YouTube, TikTok, Facebook Reels. Instagram Reels has to be finished from the phone app.

Credential files live in `credentials/` at the project root. Put each platform's file there and re-launch the app.

---

## YouTube (API)

1. Google Cloud Console → create project → enable **YouTube Data API v3**.
2. APIs & Services → Credentials → Create Credentials → **OAuth client ID** → Application type: **Desktop app** → download the JSON.
3. Save it as `credentials/youtube_client_secret.json` (or keep the legacy `youtube_client_secret.json` in the project root — both work).
4. First upload opens a browser for OAuth. Token is cached in `credentials/youtube_token.json`.

UI: pick **Platform: YouTube**, pick privacy (public/unlisted/private).

---

## TikTok (API)

1. https://developers.tiktok.com/ → create app → enable **Content Posting API**.
2. Add `http://localhost:8765/` to your app's **Redirect URI** list (change the port if you want — put the same port in the credentials file below).
3. Create `credentials/tiktok_client.json`:

   ```json
   {
     "client_key": "<Client Key from TikTok>",
     "client_secret": "<Client Secret>",
     "redirect_port": 8765
   }
   ```

4. First upload opens TikTok's consent screen. Token is cached in `credentials/tiktok_token.json`.

**Scopes used:**
- Default (unchecked "direct post"): `video.upload` — video lands in your TikTok drafts. You finalize caption/hashtags/privacy in the TikTok app and hit Post. Works in Sandbox out of the box.
- Direct post (checked): `video.publish` — posts immediately with the title as the caption. Requires TikTok production review to enable.

---

## Facebook Reels (API)

You need a Meta app, a Facebook Page, and a Page access token with `pages_manage_posts` + `pages_read_engagement` + `pages_show_list`.

Easiest path to get a long-lived page token (one-time):

1. https://developers.facebook.com/ → create app (type: Business).
2. Add **Facebook Login** and your page in app roles.
3. Graph API Explorer → select your app → Generate User Access Token with the three permissions above.
4. Exchange it for a long-lived user token via `GET /oauth/access_token?grant_type=fb_exchange_token&...`.
5. `GET /me/accounts?access_token=<long-lived-user-token>` → find your page → copy `id` and `access_token`.

Save `credentials/facebook_token.json`:

```json
{
  "page_id": "<page id>",
  "page_access_token": "<long-lived page token>",
  "graph_version": "v21.0"
}
```

Long-lived page tokens obtained this way don't expire as long as you refresh occasionally.

---

## Instagram Reels (API)

Instagram's Graph API **fetches the video from a public URL** — you have to host your shorts somewhere the internet can GET them.

**Requirements:**
- Instagram **Professional** (Business or Creator) account.
- That account must be linked to a Facebook Page.
- Meta app with `instagram_basic`, `instagram_content_publish`, `pages_show_list` permissions.
- A public base URL that serves the contents of your `generated/` folder.

**Hosting the file** — pick one:
- S3 / Cloudflare R2 / Backblaze B2 bucket with public read. Upload the generated file before clicking Publish.
- `cloudflared tunnel --url http://localhost:8080` against a local HTTP server (e.g. `python -m http.server 8080 -d generated`). Paste the `trycloudflare.com` URL as `public_base_url`.
- `ngrok http 8080` same idea.

Save `credentials/instagram_token.json`:

```json
{
  "ig_user_id": "<numeric IG Professional account id>",
  "access_token": "<long-lived access token with instagram_content_publish>",
  "public_base_url": "https://your.tunnel.example.com/<run-folder>/",
  "graph_version": "v21.0"
}
```

The uploader builds the video URL as `public_base_url + <video filename>` and HEADs it before calling the API; if the URL isn't reachable, it aborts with a clear error.

**Browser mode for Instagram** — Reels can't be published from the desktop web; the browser mode opens instagram.com and copies the caption, and you finish from the phone app.

---

## Clip count

The UI's "Max number of shorts" slider is a cap, not a target. The AI returns only as many moments as it considers worth clipping. Raise it to 50+ for long VODs.

---

## Which mode should I use?

| Situation | Mode |
|---|---|
| One-click publishing after a run | API |
| You want to tweak the caption / thumbnail before posting | Browser |
| Platform's API failing / rate-limited / still under review | Browser |
| Instagram Reels | API (or finish on phone) |
| TikTok without business verification | API with "direct post" **off** (inbox mode) |

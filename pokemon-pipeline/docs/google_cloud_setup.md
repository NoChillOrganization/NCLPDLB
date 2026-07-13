# Google Cloud Setup — YouTube Data API v3

## 1. Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com/).
2. Click **New Project**, name it e.g. `pokemon-pipeline`.
3. Select the new project once created.

## 2. Enable the YouTube Data API v3

1. Navigate to **APIs & Services → Library**.
2. Search "YouTube Data API v3" and click **Enable**.

## 3. Create an API key

1. Navigate to **APIs & Services → Credentials**.
2. Click **Create Credentials → API key**.
3. Copy the key.
4. (Recommended) Click **Restrict Key** → restrict to "YouTube Data API v3" only, and optionally
   restrict by IP if the pipeline runs from a static address.

## 4. Set the env var

Add to `.env`:

```
YOUTUBE_API_KEY=your-key-here
```

Never commit this key. `.env` is gitignored.

## 5. Quota breakdown

Default daily quota: **10,000 units**.

| Call | Cost (units) |
|------|--------------|
| `channels.list` | 1 |
| `playlistItems.list` (per page, up to 50 items) | 1 |
| `videos.list` (per call, up to 50 IDs batched) | 1 |
| `search.list` | 100 (avoid — not used by this pipeline) |

`YouTubeClient` in `tasks/ingest/youtube_client.py` tracks cumulative quota usage per run and logs
a warning below 1000 units remaining. On a `403 quotaExceeded` response the ingest task stops
gracefully (`YouTubeQuotaExceeded`) rather than crashing — already-synced creators keep their
progress since `last_scraped_at` is only updated after each creator's sync succeeds.

With ~10 creators and weekly syncs, expect well under 500 units/run in steady state (playlist
pagination + one batched `videos.list` call per creator).

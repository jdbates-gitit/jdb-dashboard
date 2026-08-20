# JDB Daily Intelligence Hub

Two Cloudflare-hosted views share one Worker and D1 database:

- `dashboard.jdb-builds.com` is the private Signal Room protected by Cloudflare Access.
- `briefing.jdb-builds.com` is the public, read-only Daily Signal.

The private dashboard stores the full briefing, Idea Inbox, Project Ledger, archive, and generation controls. The public page reads only from a separate publication snapshot. Publishing always removes the `project_vote` section and never exposes ideas, votes, archives, generation, or editor APIs.

## Daily workflow

1. Review the generated briefing in the private dashboard.
2. Select **Publish public page**.
3. Use **Public page ↗** to view or share the published edition.

Refreshing or regenerating a briefing marks the public edition as needing publication again, so a changed edition is never silently pushed live.

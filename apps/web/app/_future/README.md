# _future

Next.js App Router treats any folder under `app/` prefixed with `_` as a
"private folder" -- it is never turned into a route. This is where already-built
screens from a previous prototyping pass live until their milestone is
formally reached and approved:

| Folder | Re-activates in | Depends on backend router |
|---|---|---|
| `login/`, `register/` | Milestone 2 -- Authentication | `/api/v1/auth` |
| `workspace/` | Milestone 2 -- Authentication | `/api/v1/workspace` |
| `documents/` | Milestone 3 -- Document Ingestion | `/api/v1/documents` |
| `chat/` | Milestone 4 -- RAG Chat + Citations | `/api/v1/conversations` |
| `settings/` | Milestone 2 -- Authentication | `/api/v1/users`, `/api/v1/workspace` |

To re-activate a screen: move its folder up one level (out of `_future/`,
back into `app/`) once the backend router it depends on has been reviewed
and approved for that milestone. No code changes should be needed beyond
that move plus re-wiring navigation (e.g. the Sidebar) and, for
login/register/workspace/settings, restoring `AuthProvider` in
`app/layout.tsx`.

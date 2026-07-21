# _future

Next.js App Router treats any folder under `app/` prefixed with `_` as a
"private folder" -- it is never turned into a route. This is where already-built
screens from a previous prototyping pass live until their milestone is
formally reached and approved. `login/`, `register/`, `workspace/`, and
`settings/` were moved out of here in Milestone 2 -- see the top-level
`app/` directory. What remains:

| Folder | Re-activates in | Depends on backend router |
|---|---|---|
| `documents/` | Milestone 3 -- Document Ingestion | `/api/v1/documents` |
| `chat/` | Milestone 4 -- RAG Chat + Citations | `/api/v1/conversations` |

To re-activate a screen: move its folder up one level (out of `_future/`,
back into `app/`) once the backend router it depends on has been reviewed
and approved for that milestone. No code changes should be needed beyond
that move plus re-wiring navigation (the Sidebar's `NAV_ITEMS` in
`components/Sidebar.tsx`) -- `AuthProvider` is already restored in
`app/layout.tsx` as of Milestone 2, so both remaining screens will have a
session to read the moment they're moved out.

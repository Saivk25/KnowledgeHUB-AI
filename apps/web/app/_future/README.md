# _future

Next.js App Router treats any folder under `app/` prefixed with `_` as a
"private folder" -- it is never turned into a route. This is where already-built
screens from a previous prototyping pass live until their milestone is
formally reached and approved. `login/`, `register/`, `workspace/`,
`settings/` (Milestone 2), and `documents/` (Milestone 3) have all been
moved out of here -- see the top-level `app/` directory. What remains:

| Folder | Re-activates in | Depends on backend router |
|---|---|---|
| `chat/` | Milestone 4 -- RAG Chat + Citations | `/api/v1/conversations` |

To re-activate `chat/`: move it up one level (out of `_future/`, back into
`app/`) once `/api/v1/conversations` is reviewed and approved. No code
changes should be needed beyond that move plus re-wiring navigation (the
Sidebar's `NAV_ITEMS` in `components/Sidebar.tsx`) and removing the
"arrives in Milestone 4" placeholders in `app/documents/page.tsx` and
`app/documents/[id]/page.tsx` -- `AuthProvider` is already restored in
`app/layout.tsx` as of Milestone 2, so `chat/` will have a session to
read the moment it's moved out.

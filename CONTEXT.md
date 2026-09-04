# Rooted Core API — Domain Context

Backend for **Rooted（扎根 · 與神同行）**: a quiet Christian mobile web app for daily Scripture devotion, private journal, and small-group fellowship — not a social feed or church ERP.

Source of truth for product scope: `rooted-docs/docs/product/prd.md` (v1.0). This file captures **ubiquitous language** for engineering and agents.

## Product constraints agents must respect

1. **Today devotion is primary; fellowship is secondary.** Opening the app meets Scripture first, not a timeline.
2. **Walking with God > task completion.** Completing a day is **Amen** / encounter with God — not “check-in success” or streak shaming.
3. **No public square:** no likes, follows, leaderboards, or algorithmic discovery in v1.
4. **Journal stays private:** journal entries, personal prayers, and private lesson notes never surface to groups or analytics content pipelines.
5. **Small groups only:** target size 4–15; covenant before full fellowship features.
6. **Licensed Scripture:** only public-domain or properly licensed translations in production (e.g. CUV1919, WEB per database design).

---

## Language

### Devotion

**Daily lesson (日課)**:
The guided unit for a calendar day: passage, reflection prompts, prayer — the core “meet God today” experience.
_Avoid_: generic “content item”, feed post

**Series**:
An ordered collection of lessons (e.g. a 7-day plan). The platform publishes the catalog; users enroll via **Plan enrollment**.
_Avoid_: playlist (too casual); treating the client bundle as the only authority

**Plan enrollment**:
A user’s commitment to walk a series from a start date, with optional pause — tracks progress without public ranking.
_Avoid_: subscription (billing connotation)

**Amen / Walk day**:
Recording that the user completed today’s devotion encounter for a date. Marks spiritual rhythm, not gamified streak points exposed to others.
_Avoid_: check-in, streak (as product-facing shame mechanics)

**Lesson note**:
User text tied to a lesson (reflection, highlights). May sync to cloud in v1; **private** unless explicitly shared via fellowship **Share** with chosen privacy.
_Avoid_: treating all notes as group-visible

---

### Bible

**Bible version**:
A translation catalog entry (e.g. `cuv1919`, `web`). Text storage is separate from devotion editorial content.
_Avoid_: bundling licensed NIV/ESV without rights

**Passage**:
Addressable Scripture text (book, chapter, verse range) for a version — served to reader and devotion surfaces.
_Avoid_: duplicating passage blobs inside every lesson row when normalized design exists

**Bookmark**:
User-saved passage reference and optional snippet for personal reading. Syncs with the account in v1 — still not a social signal.
_Avoid_: treating bookmarks as group-visible

---

### Journal

**Journal entry**:
Private user writing (types per schema — reflection, confession, etc.). **Never** queryable by group members or fellowship APIs.
_Avoid_: “post”, timeline entry

**Personal prayer**:
Private prayer list item (title, body, status). Distinct from group **Prayer request**.
_Avoid_: conflating with fellowship prayer wall

**Memory card**:
Spaced-repetition card for verse memory — private study aid.
_Avoid_: public flashcard leaderboard

**Privacy wall (engineering)**:
Fellowship and analytics code paths must not JOIN or export `journal_entries`, `personal_prayers`, or private lesson note bodies.

---

### Fellowship

**Group**:
A small fellowship (4–15 members) with invite code, created by a member. Not an open community.
_Avoid_: church (whole congregation ERP), channel (chat product)

**Covenant**:
Explicit acceptance of group norms (product copy fixed in meaning, translatable) before full participation — stored as `covenant_accepted_at` on membership.
_Avoid_: skipping covenant for “faster onboarding” on real groups

**Membership**:
Links user to group with role `member` or `shepherd` (組長). Shepherd sees pastoral **walk alongside** signals — not competitive rankings.
_Avoid_: admin (that term is for **Admin User** on the admin console)

**Prayer request**:
Group-visible prayer need on the prayer wall. Others mark **prayed** (代禱) — not a comment thread.
_Avoid_: DM, chat message

**Encouragement**:
Short response tied to a prayer request — lightweight, not a nested forum.

**Share (亮光)**:
Optional sharing of insight from devotion to the group with explicit **privacy** and optional `lesson_id` link.
_Avoid_: auto-posting journal or notes

**Demo group**:
Sample fellowship for preview — must be labeled or isolated from real church groups in production (PRD §11.4).

**Weekly invite**:
A per-group, per-End-user flag that the member joined that group’s weekly invite rhythm — synced with the account, not a chat message.
_Avoid_: treating it as a Prayer request or Share

---

### Auth & platform

**End user**:
The product identity of someone using the Rooted app — anonymous for read-only devotion/bible where allowed, or authenticated for sync and fellowship. Linked to an auth credential row; created only when the person uses the app as a member (a pure **Admin User** need not have one). Presentation fields such as display name live under **Preferences**.
_Avoid_: Member (as the identity noun — that word belongs to **Membership** roles), conflating with **Admin User**

**Preferences**:
End-user settings and presentation defaults (display name, locale, theme, font scale, bible version, stage, reminder) — distinct from auth credentials, from **Admin User** profile fields, and from the End user identity key.
_Avoid_: Admin User profile fields, burying prefs inside fellowship or journal rows

**Admin User**:
Staff account using the **admin** API (`/admin`) for RBAC, content, and moderation — distinct from **shepherd** (group role) and from **End user**. May share the same auth credential as an End user when one person holds both capacities.
_Avoid_: Operator, treating Membership role as admin

**Report**:
User flag on fellowship content (prayer, share, etc.) with reason code — feeds moderation queue in v1.

**Sync**:
Client ↔ server reconciliation for v1 accounts — not a second product surface; respects journal privacy rules on server.

---

## Version map (API relevance)

| Phase | Backend focus                                      |
| ----- | -------------------------------------------------- |
| v0    | Client-local; minimal API                          |
| v1    | Accounts, sync, real groups, moderation, content   |
| v2    | Store packaging (Capacitor) — same API             |
| v3    | Church/content platform extensions — future ADRs   |

---

## Related documentation

| Document | Location |
| -------- | -------- |
| PRD | `rooted-docs/docs/product/prd.md` |
| API spec | `rooted-docs/docs/backend/api-specification.md` |
| Database design | `rooted-docs/docs/backend/database-design.md` |
| ADRs | `docs/adr/` |

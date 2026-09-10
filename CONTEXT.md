# Rooted Core API — Domain Context

Backend for **Rooted（扎根 · 與神同行）**: a quiet Christian mobile web app for daily Scripture devotion, private journal, and small-group fellowship — not a social feed or church ERP.

Source of truth for product scope: `rooted-docs/docs/product/prd.md` (v1.0). This file captures **ubiquitous language** for engineering and agents.

## Product constraints agents must respect

1. **Today devotion is primary; fellowship is secondary.** Opening the app meets Scripture first, not a timeline.
2. **Walking with God > task completion.** Completing a day is an **Encounter day** (「今日已與主相遇」) — not “check-in success” or streak shaming.
3. **No public square:** no likes, follows, leaderboards, or algorithmic discovery in v1.
4. **Journal stays private:** journal entries, personal prayers, and private lesson notes never surface to groups or analytics content pipelines.
5. **Small groups only:** target size 4–15; covenant before full fellowship features.
6. **Licensed Scripture:** only public-domain or properly licensed translations in production (e.g. YouVersion CCBT `1392` under the Platform license). Do not ship NIV/ESV without rights.

---

## Language

### Devotion

**Devotion (靈修篇章)**:
One authored piece of devotional content in the editorial pool: a Scripture **verse** reference plus reflection prompts, today's application, and prayer. Written by Rooted staff, versioned through `draft` → `ready`, and only becomes a **Daily lesson** once scheduled onto a date. Exists independently of any date — an unscheduled Devotion is real content, just not yet anyone's day. Its authored text lives in per-locale **Devotion translation** rows; a Devotion cannot reach `ready` until every locale active in the system locale catalog is filled.
_Avoid_: calling an unscheduled piece a "daily lesson", storing the Scripture text on it (it holds a **Passage** reference; the text comes from the reader's **Bible version**), one row carrying all locales in JSONB, a hardcoded list of supported languages

**Daily lesson (日課)**:
A **Devotion** scheduled onto one calendar date — what the End user meets when they open Today. Identified by its date, not by a position in a course. The backend decides it; the End user never chooses it and the client never resolves it from a bundled catalog. A date with no scheduled Daily lesson is an operational gap that surfaces as an error, never as silently substituted content.
_Avoid_: generic "content item", feed post, "day N of a series", letting the client pick the day's lesson, auto-filling an unscheduled date from the pool

**Devotion translation**:
The authored text of one **Devotion** in one locale — reflection prompts, today's application, prayer. One row per locale, never one row carrying all locales. Every locale marked active in the system locale catalog must have a row before the Devotion can reach `ready`, so a reader is never served a half-translated day. No locale is privileged as a base — that idea only existed to name a fallback target, and there is no fallback. Does **not** carry Scripture text — that comes from the reader's **Bible version**.
_Avoid_: JSONB multi-locale columns, falling back to another locale at read time, treating a missing translation as a runtime concern rather than a publishing gate, hardcoding the language list in devotion code, hanging the rule on the catalog's `is_default` flag (it governs unrelated admin-console behaviour)

**Encounter day (相遇日)**:
A record that an End user met God through the **Daily lesson** on one calendar date — one row per user per date. Sign-in required, and recordable **only for the End user's own current local date** (BR-02): there is no backfilling a missed day. Marks spiritual rhythm, never gamified points exposed to others.
_Avoid_: Amen (the word is a response of assent, not a completion; product copy now says 「今日已與主相遇」), Walk day (「同行」 already names the shepherd's pastoral view), check-in, backfill/make-up days, publicly comparable streaks

**Encounter streak**:
How many consecutive dates an End user has an **Encounter day** for, shown only to that person. The **longest** streak is stored (it only ever grows, and only on a write); the **current** streak is stored alongside the last encounter date but must be re-validated against the reader's local date on every read — an untouched stored "current streak" silently rots the moment a day is missed, because nothing writes on the day someone stops.
_Avoid_: trusting a stored current-streak value without date validation, exposing either number to other members, "streak broken" copy

**Lesson note**:
An End user's own writing for one calendar date — free note text plus optional answers to that day's reflection prompts, in one row per user per date. Sign-in required, and writable **only for the current local date**, like an **Encounter day**. The client supplies its IANA device time zone in `X-Timezone`; the backend converts its current UTC time into that zone before accepting the date. Optional throughout: never required to record an Encounter day. **Private** unless explicitly shared via fellowship **Share** with chosen privacy.
_Avoid_: treating all notes as group-visible, a separate store for reflection answers, keying the note to the pooled **Devotion** (a Devotion may be rescheduled; the writing belongs to the person's day, not to the content), requiring a note before an Encounter day, conflating with a **Footnote** (publisher annotation on Scripture)

---

### Bible

**Bible version**:
A translation catalog entry for one published edition (e.g. YouVersion `1392` / CCBT 2023). The **Bible index** is stored up front; verse bodies are filled when someone actually reads that chapter. Text storage is separate from devotion editorial content.
_Avoid_: bundling licensed NIV/ESV without rights, treating a new publisher revision as an in-place edit of the same catalog row when YouVersion issues a new bible id, pre-crawling every verse body into the catalog

**Bible index**:
The address tree of one **Bible version** — books, chapters, and verse identifiers — without Scripture text. Enough to list books, open a chapter picker, and validate a **Passage** reference such as `JHN.3.16`.
_Avoid_: Passage (that is the served text plus its address), storing verse bodies in the index, calling the index "Sync"

**Passage**:
Addressable Scripture text (book, chapter, verse range) for a version — served to reader and devotion surfaces. The Devotion row holds only the address (`passage_start` / `passage_end`); the text comes from the reader's **Bible version** when they actually read. A filled verse is an ordered list of lines (heading, paragraph, poetry line); a paragraph may split into inline fragments. Searchable Scripture for that verse is the concatenated body without **Heading** or **Footnote**.
_Avoid_: duplicating passage blobs inside every lesson row when normalized design exists, sending YouVersion HTML to the App, indexing footnotes or headings as if they were verse text

**Heading**:
Publisher section title inside a **Bible version** (a **Scripture style** such as `s1` / `ms` / `cl`). May sit before a verse or in the middle of that verse's body. It is not Scripture text and not a **Passage** address.
_Avoid_: treating it as the verse's only title field, assuming it always precedes the next verse number

**Footnote**:
Publisher annotation attached as an inline fragment inside verse text (YouVersion `yv-n`, usually type `f` or `x`) — explanation, alternate rendering, or cross-reference. Distinct from a **Lesson note**.
_Avoid_: Note (unqualified), Lesson note, embedding YouVersion HTML in the App

**Scripture style**:
The publisher class on a line or inline fragment (`s1`, `q1`, `nd`, `wj`, `pn`, Footnote kinds, …). Fill stores the class as given. The App's first known set is Heading styles, poetry lines, Footnote, divine name (`nd`), words of Jesus (`wj`), and proper names (`pn`); anything else is stored and shown as ordinary text until a presentation is decided.
_Avoid_: dropping unknown classes at fill time, copying YouVersion HTML/CSS into the App, treating every class as a new domain entity

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
The product identity of someone using the Rooted app — anonymous for read-only devotion/bible where allowed, or authenticated for sync and fellowship. Stored as `app.user` with its own UUID and FK to the auth credential (`auth.user`); created only when the person uses the app as a member (a pure **Admin User** need not have one). Presentation fields such as display name live under **Preferences** (`app.user_preferences`). Future product FKs (journal, groups, …) target `app.user.id`, not `auth.user.id`.
_Avoid_: Member (as the identity noun — that word belongs to **Membership** roles), conflating with **Admin User**, using `auth.user.id` as the product member FK

**Preferences**:
End-user settings and presentation defaults (display name, theme, font scale, bible version, stage, reminder, week start) — distinct from auth credentials, from **Admin User** profile fields, and from the End user identity key. Includes **week start** (`sunday` | `monday`, default `sunday`) — which day the Today screen's weekly rhythm bar begins on; a personal habit that follows the account across devices, unlike language. Does **not** hold UI language: the App always follows the device's system language and never lets the End user override it in-app (ADR 0009).
_Avoid_: Admin User profile fields, burying prefs inside fellowship or journal rows, a stored `locale` column keyed to the account (language is per-device, not a synced account preference — see **Device**)

**Admin User**:
Staff account using the **admin** API (`/admin`) for RBAC, content, and moderation — distinct from **shepherd** (group role) and from **End user**. May share the same auth credential as an End user when one person holds both capacities. Signs in with that **Auth credential** via password and/or an **Identity link**; an Identity-provider sign-in alone never creates an Admin User.
_Avoid_: Operator, treating Membership role as admin, auto-provisioning staff from Google/Apple alone

**Auth credential**:
The sign-in subject in `auth.user`, always identified by a required email, with optional password and zero or more **Identity links**. An **End user** and an **Admin User** may share one credential; product data hangs off **End user**, not off this row. Phone number is not part of this credential.
_Avoid_: Account (ambiguous), conflating with **End user** / `app.user`, phone-as-login-id

**One-time passcode (OTP)**:
A short-lived numeric code emailed to a person to authenticate an **End user** — the sole first-party (non-Identity-provider) sign-in path (ADR 0008). Stored ephemerally (e.g. Redis TTL) keyed to the request, never on **Auth credential** or **Identity link** rows.
_Avoid_: Magic link (superseded by ADR 0008), treating an OTP as a persisted/product-facing entity, phone-delivered OTP (phone is not a Rooted credential identifier)

**Identity provider**:
A known external sign-in source (e.g. Google, Apple) registered in the auth catalog — not the person’s account at that vendor, and not an OAuth token. **Google** is used for both **Admin User** and **End user** sign-in; **Apple** is End-user-only — never for the admin console (ADR 0008). Microsoft is not a Rooted Identity provider.
_Avoid_: Social network, OAuth client, treating a free-form string as the provider without a catalog entry, Microsoft Entra as an in-scope provider, Apple sign-in for Admin Users

**Identity link**:
A durable binding from an **Identity provider** subject (and optional provider tenant) to one **Auth credential**. One credential may have many links across providers; at most one active link per credential per provider; each provider subject binds to at most one credential. Used to recognize the same person on later sign-ins — not an OAuth token store and not a product profile. For **Google**, the provider subject is the account’s stable IdP user id (same across Rooted’s different OAuth clients such as admin console vs the app); Rooted does **not** create one Google Identity link per client application. For **End user** sign-in via Google or Apple (ADR 0008), a first successful Identity-provider sign-in may create the Auth credential and End user; for **Admin User** sign-in it only binds to an already-admin credential, and only via **Google** in the admin console. A first Admin Google success that matches by verified email creates the link; later sign-ins resolve primarily by provider subject.
_Avoid_: OAuth session, social account, third-party login (as the noun for the row), storing provider access/refresh tokens as the purpose of this concept, matching Admin sign-in by email alone after a link exists, Admin Apple Identity links as a product path, one Google Identity link per OAuth client id

**Report**:
User flag on fellowship content (prayer, share, etc.) with reason code — feeds moderation queue in v1.

**Sync**:
Client ↔ server reconciliation for v1 accounts — not a second product surface; respects journal privacy rules on server.

---

### Push notifications

**Device**:
An app installation instance identified by a client-generated `device_key`, holding at most one push token and platform, and optionally linked to the **End user** currently signed in on it (nullable — overwritten on sign-in, cleared on sign-out). Exists independently of authentication: registered on first app launch, before any account exists, so an anonymous install can hold a Device row with no End user attached. Also carries that install's last-known system locale (ADR 0009) — the source of truth for "what language should this device's push copy be in", since **Preferences** no longer holds one.
_Avoid_: conflating with **End user** identity; assuming a Device belongs permanently to one account (a shared or re-logged-in device may change hands); Device Token (the token is a field on Device, not a separate concept); treating Device locale as an editable product preference (it's a passive snapshot, not user-facing)

**Notification**:
A single push-worthy event addressed to one **End user** (e.g. someone prayed for their prayer request). Delivered by fanning out to every active **Device** linked to that End user at send time.
_Avoid_: conflating with the client-local daily reminder (`Preferences.reminder_enabled`/`reminder_time`), which never touches this concept — that reminder fires from an on-device schedule, not a server Notification row

**Notification delivery**:
One attempt to deliver a **Notification** to one specific **Device** — records success/failure and error detail. The basis for deactivating a Device whose token has permanently failed, so it stops being targeted by future Notifications.
_Avoid_: a per-End-user read/unread inbox (not yet modeled — future work)

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
| ADRs | `docs/adr/` (identity storage: ADR 0005; Admin Google: ADR 0006; direct FCM push: ADR 0007; End-user OTP/Google/Apple sign-in: ADR 0008; language follows device: ADR 0009; calendar Daily lesson & no series: ADR 0010; Devotion pool + schedule + per-locale translations: ADR 0011; Encounter streak storage: ADR 0012; date-locked writes: ADR 0013; Bible index + read-time fill: ADR 0014) |

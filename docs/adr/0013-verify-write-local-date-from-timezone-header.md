# ADR 0013 — Verify date-locked writes from the device timezone header

## Status

Accepted (2026-09-09).

## Context

Daily lessons are addressed by the End user's local calendar date (ADR 0010). A lesson note is writable only for that local date, so that a person's writing remains a record of the day rather than a backfillable activity.

The earlier read-path decision lets the client send a date directly: a read does not mutate private history, and the client already knows its local date. A write needs an independent backend check. Deriving the date from the server's own timezone would reject valid writes near midnight for users elsewhere in the world.

## Decision

1. Date-locked write endpoints require an `X-Timezone` request header containing an IANA timezone name, such as `America/Toronto` or `Asia/Taipei`.
2. The backend takes its current UTC instant, converts it to `X-Timezone`, and accepts a write only when the request's date equals that local calendar date.
3. Missing or invalid `X-Timezone` is rejected with `400 INVALID_TIME_ZONE`; a valid zone whose current local date differs from the request date is rejected with `400 LESSON_NOTE_DATE_NOT_TODAY`.
4. The header is a client assertion, not proof of physical location. It prevents normal date and timezone mistakes but does not attempt to provide fraud resistance.

## Considered options

| Option | Rejected | Why |
| ------ | -------- | --- |
| Compare to the server or UTC calendar date | Wrong local day | It misclassifies valid writes around midnight for users outside the server's timezone |
| Trust the request date without validation | Cannot enforce the write rule | Past and future writes cannot be rejected |
| Persist one timezone on the End-user profile | Timezone goes stale while travelling | The device is the source of the current local day, so each date-locked write carries its current zone |

## Consequences

- App clients must add `X-Timezone` to date-locked write requests.
- `GET` daily-lesson and rhythm reads continue to accept the client date without this header, as ADR 0010 specifies.
- A human-authored Alembic migration is required before deploying the `lesson_notes` model; agents do not create migration revisions.

# Issue tracker: Linear

Issues and specs for this repo live as Linear issues on team `ROO` (identifiers like `ROO-123`). Use the Linear GraphQL API. Do not use GitHub Issues for tickets.

GitHub remains the git host for code and pull requests. Pull requests are not a triage surface.

## Auth

- Endpoint: `https://api.linear.app/graphql`
- Header: `Authorization: $LINEAR_API_KEY`
- Do not print the key. Resolve `ROO` to a team id with `teams(filter: { key: { eq: "ROO" } })`.

## Project

Default Linear Project for issues created from this repo: **`rooted core api`**.

Resolve the project id with `projects(filter: { name: { eq: "rooted core api" } })` (or the workspace projects list). When creating an issue, always pass that `projectId` so the ticket lands under this project.

## Conventions

- **Create**: `issueCreate(input: { teamId, projectId, title, description })`. Put a multi-line body in `description` (markdown). Resolve `projectId` from **Project** above.
- **Read**: `issue(id: "ROO-123")` with `id`, `identifier`, `title`, `description`, `state { name type }`, `labels { nodes { name } }`, `comments { nodes { body createdAt user { name } } }`.
- **List**: `issues(filter: { team: { key: { eq: "ROO" } }, state: { type: { nin: ["completed", "canceled"] } } })`. Add a `labels` filter when a skill names a label.
- **Comment**: `commentCreate(input: { issueId, body })`.
- **Apply / remove labels**: `issueAddLabel` / `issueRemoveLabel`. Look up the label id on the team by name; create the label on the team if it is missing.
- **Close**: `issueUpdate` to the team's workflow state whose `type` is `completed` (Done). For `wontfix`, use the state whose `type` is `canceled`, and add the comment first.

A bare `#42` is not a Linear identifier. Resolve tickets by identifier (`ROO-123`) or by Linear issue id.

## Pull requests as a triage surface

**PRs as a request surface: no.**

## When a skill says "publish to the issue tracker"

Create a Linear issue on team `ROO` under this repo's Project (see **Project** above).

## When a skill says "fetch the relevant ticket"

Query `issue(id: "<identifier>")` including comments and labels.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single Linear issue with **child** issues as tickets.

- **Map**: one issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body.
- **Child ticket**: `issueCreate` with `parentId` set to the map. Labels: `wayfinder:<type>` (`research` / `prototype` / `grilling` / `task`). Once claimed, assign it to the driving dev.
- **Blocking**: `issueRelationCreate` with type `blocks`. A ticket is unblocked when every blocker is completed or canceled. If relations are unavailable, put `Blocked by: ROO-n, ROO-n` at the top of the child description.
- **Frontier query**: the map's open children, dropping any with an open blocker or an assignee. First in map order wins.
- **Claim**: `issueUpdate` assignee to the current Linear viewer (`viewer`). This is the session's first write.
- **Resolve**: comment with the answer, set the state to completed, then append a context pointer to the map's Decisions-so-far description.

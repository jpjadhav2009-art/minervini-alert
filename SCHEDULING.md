# Scheduling

## Why there is an external trigger

GitHub's free `schedule:` trigger is best-effort. Measured on this repo:

| Run | Due (UTC) | Actually ran | Late |
|-----|-----------|--------------|------|
| 111 | Fri 10:33 | Sat 00:14 IST | 8.2h |
| 110 | Thu 10:33 | Fri 00:37 IST | 8.6h |
| 109 | Wed 10:33 | Thu 00:28 IST | 8.4h |

Eight hours late every run. The scan still reads a confirmed close, but the
alert lands after midnight instead of just after the market close.

An external cron service calling the `workflow_dispatch` API fires within a
minute or two of the requested time.

## What to call

Two jobs, both HTTP `POST`, five minutes apart:

| Job | Time (Asia/Kolkata) | URL |
|-----|---------------------|-----|
| Part 1 | 16:03, Mon-Fri | `https://api.github.com/repos/jpjadhav2009-art/minervini-alert/actions/workflows/run.yml/dispatches` |
| Part 2 | 16:08, Mon-Fri | `https://api.github.com/repos/jpjadhav2009-art/minervini-alert/actions/workflows/run2.yml/dispatches` |

If the service wants UTC: 10:33 and 10:38.

Headers:

```
Accept: application/vnd.github+json
Authorization: Bearer <TOKEN>
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json
```

Body:

```json
{"ref": "main"}
```

A success is **HTTP 204 No Content** with an empty body. 401 means the token
is wrong or expired; 404 usually means the token lacks Actions write access.

## The token

A fine-grained personal access token, scoped to this repository only, with
**Actions: Read and write**. Nothing else. Create it at
<https://github.com/settings/personal-access-tokens>.

Set an expiry you will notice: when the token expires the trigger stops
silently, and the only symptom is alerts that no longer arrive.

## Testing it by hand

```sh
curl -i -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -d '{"ref":"main"}' \
  https://api.github.com/repos/jpjadhav2009-art/minervini-alert/actions/workflows/run.yml/dispatches
```

Expect `HTTP/2 204`. A new run then appears under Actions within seconds.

## The `schedule:` blocks

Both workflows still carry their own `cron:`. Leave them until the external
trigger has fired successfully at least once - they are the only thing
currently producing alerts. Once the trigger is proven, remove the
`schedule:` block from `run.yml` and `run2.yml`, otherwise every weekday
produces a second, eight-hour-late set of alerts.

Removing `schedule:` also retires the inactivity problem: GitHub only
auto-disables workflows that have a schedule, so the keep-alive step in
`run.yml` becomes belt-and-braces rather than load-bearing.

# How to trigger a workflow from a webhook

## Problem

Something happens outside Agentic (a pull request opens, a deploy finishes, a service posts an alert) and you want the app to react: run an agent, run an Agentic command, or run a shell script.
You want the outside system's event to be the trigger, and you want to see whether it arrived and what it started.

## Prerequisites

- A running API (see the [tutorial](../tutorials/getting-started.md)). The event bus and the workflow executor live in the API process.
- The outside service can reach the API. For GitHub, that means an address GitHub can call (see [Expose Agentic on your network](expose-on-your-network.md) or a tunnel).
- At least one execution graph with an **Event trigger** step. See the [Webhooks view](../views/webhooks.md) for the page itself.

## Steps

### 1. Create a webhook endpoint

1. Open **Webhooks** (`/webhooks`) and click **New endpoint**.
2. Pick a **Kind**:
   - **Generic JSON webhook** accepts any JSON body at `/api/hooks/<endpoint-id>`.
   - **GitHub webhook** accepts GitHub's format at `/api/hooks/github/<endpoint-id>` and verifies its signature.
3. Set a **Secret**.
   - On a GitHub endpoint the secret is the HMAC key GitHub signs every delivery with. Nothing is accepted until it is set.
   - On a generic endpoint the secret is optional. When set, the sender must present it in `X-Webhook-Secret` or as an `Authorization: Bearer` token.
4. Click **Create endpoint**, then **Copy URL**.

### 2. Give the graph an event trigger

1. Open **Execution graphs** (`/graphs`) and edit the graph that should run.
2. Click **+ Event trigger**. A graph holds at most one.
3. Add one **Event field** per payload value the workflow needs, for example:
   - Label `title`, payload path `pull_request.title`
   - Label `author`, payload path `pull_request.user.login`
   - Label `body`, payload path `pull_request.body`
4. Wire an event field into a step's input, then reference it in that step with `{{name}}`.

A path uses dots and list indexes: `pull_request.labels[0].name`.
A leading `payload.` is accepted, so `payload.pull_request.title` works too.
A path that points at an object or a list feeds its JSON.
A path that does not exist feeds an empty string.
A manual or scheduled run has no event, so every event field is empty.

### 3. Wire the graph to the endpoint

1. On the **Webhooks** page, click **Workflows** on the endpoint.
2. Pick the **Workflow** (the execution graph).
3. Optionally set **Event types** (comma separated, for example `pull_request` or `issues`). Leave it empty to accept every event.
4. Optionally add payload **filters**, for example:
   - `action` **equals** `opened`
   - `repository.full_name` **contains** `your-org/your-repo`
   - `pull_request.draft` **exists** (set the value to `false` to require it missing)
5. Click **Wire workflow**.

Every matching event starts a new execution of that graph.
A paused graph is skipped and the delivery says so.
A graph that already has a running execution refuses the new one, and the delivery records the conflict.

### 4. Configure the sender

For GitHub:

1. Open the repository's **Settings → Webhooks → Add webhook**.
2. Set **Payload URL** to the copied `/api/hooks/github/<endpoint-id>` URL.
3. Set **Content type** to `application/json`.
4. Set **Secret** to the same value you saved on the endpoint.
5. Choose the events, or send everything.
6. Save. GitHub sends a `ping` delivery immediately, which appears on the **Events** tab.

For any other service, post JSON to `/api/hooks/<endpoint-id>` and add `X-Event-Type: <name>` when your subscriptions filter by event type.
The query parameter `?event=<name>` works too.

### 5. Check what happened

- **Test** sends a sample event through the endpoint without the secret, so you can prove the wiring.
- **Events** lists every stored delivery. Open one to see its payload, the workflows that matched, each delivery's status, and the execution it started.
- **Replay** delivers the stored event again, which starts the workflows a second time.
- The execution shows up on **Execution graphs → Executions** with trigger `event:<type>`, and the trigger step shows the values it resolved.

## Do it from the CLI

```bash
agentic webhooks create --name "GitHub PRs" --kind github --secret "$SECRET"
agentic webhooks list

agentic webhooks subscribe <endpoint> <graph> --name "PR opened" \
  --event pull_request --filter action=opened
agentic webhooks subscriptions <endpoint>

agentic webhooks test <endpoint> --event pull_request --payload payload.json
agentic webhooks events <endpoint>
agentic webhooks event <event>
agentic webhooks replay <event>
```

## Behavior to know

- An inbound event is stored first, then matched against the endpoint's enabled subscriptions, so a rejected event (bad signature, disabled endpoint) leaves no row.
- A GitHub delivery without a valid `X-Hub-Signature-256` is rejected with `401`. A GitHub endpoint with no secret rejects everything with `400` until you set one.
- Matching filters combine with AND. An empty `events` list matches every event type.
- A delivery records `started`, `skipped`, or `failed`. `failed` covers a missing graph, a paused graph, a validation problem, or a graph already running.
- Deleting an endpoint deletes its subscriptions and stored events. Deleting a graph removes the subscriptions that pointed at it.

## Verification

`agentic webhooks events` lists the delivery, and the execution's trigger step shows the payload values it resolved.
For GitHub, the repository's webhook page shows the delivery's response code (`202`).

## Related

- [Webhooks view](../views/webhooks.md).
- [HTTP API reference](../reference/http-api.md) for the `/api/webhooks` and `/api/hooks` endpoints.
- [Expose Agentic on your network](expose-on-your-network.md) when GitHub must reach your machine.

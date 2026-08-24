# AgentCore Gateway MCP demo

Two-runtime architecture on Amazon Bedrock AgentCore:

```
 Runtime A (MCP client / Strands agent)
        |  HTTPS + Cognito bearer token
        v
 AgentCore Gateway  (ingress: CUSTOM_JWT/Cognito, egress: IAM SigV4)
        |  SigV4-signed call, via the Gateway's own execution role
        v
 Runtime B (MCP server, streamable-HTTP, port 8000/mcp)
        |  boto3
        v
 DynamoDB table "AgentCoreMockCatalog" (25 synthetic rows)
```

Runtime A never talks to Runtime B directly -- it only ever knows the
Gateway's URL. The Gateway is what resolves that to Runtime B's actual
AgentCore Runtime invocation endpoint and authenticates the hop.

## Layout

```
data/seed_dynamodb.py       creates + seeds the DynamoDB table (25 rows)
mcp-server/                 MCP server (Runtime B): server.py, Dockerfile
mcp-client/                 MCP client agent (Runtime A): agent.py, Dockerfile
infra/                      boto3 deployment scripts (run in numeric order)
test/test_end_to_end.py     the verification script
```

`infra/state.json` accumulates every ID/ARN/URL each script creates, so
later scripts (and the test script) don't need anything hardcoded.

## Prerequisites

- AWS credentials for an account with Bedrock AgentCore enabled, exported as
  `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` (and
  optionally `AWS_REGION`, default `us-east-1`).
- Docker with `buildx` (already present in this environment).
- Bedrock model access enabled for the model in `BEDROCK_MODEL_ID`
  (`mcp-client/agent.py`, default `anthropic.claude-3-5-sonnet-20241022-v2:0`)
  if you want to exercise Runtime A's natural-language mode.

## Run it

```bash
pip install -r requirements-local.txt   # boto3 + mcp, for the local scripts/test

# One-shot: seed data + create everything in order
python3 infra/run_all.py

# Or step by step:
python3 data/seed_dynamodb.py
python3 infra/01_create_iam_roles.py
python3 infra/02_build_and_push_images.py
python3 infra/03_setup_cognito.py
python3 infra/04_deploy_mcp_server_runtime.py
python3 infra/05_create_gateway_and_target.py
python3 infra/06_deploy_mcp_client_runtime.py

# Verify the whole chain fetches DynamoDB rows
python3 test/test_end_to_end.py
```

`test/test_end_to_end.py` does three things:
1. Reads the DynamoDB table directly with boto3 (sanity check, expects >=20 rows).
2. Opens an MCP session straight to the **Gateway** URL (as any MCP client
   would) and calls the `list_products` tool -- proving Gateway -> Runtime B
   -> DynamoDB works.
3. Invokes the deployed **Runtime A** container via
   `bedrock-agentcore:InvokeAgentRuntime`, asking it to make the same tool
   call -- proving the full Runtime A -> Gateway -> Runtime B -> DynamoDB
   chain works.

## Notes / things worth knowing before you run this for real

- Everything here uses **boto3 scripts directly**, not the `agentcore` CLI /
  starter toolkit, since the ask was for scripted, reproducible test. The
  official CLI (`agentcore create/deploy`) is a valid, simpler alternative if
  you'd rather not manage IAM policies and ECR pushes by hand.
- Container images **must be `linux/arm64`** -- AgentCore Runtime requires it.
- Runtime B (MCP server) is deployed with `protocolConfiguration.serverProtocol
  = "MCP"` and no JWT authorizer, so its default inbound auth is IAM/SigV4 --
  that's what lets the Gateway's `GATEWAY_IAM_ROLE` credential provider call
  it directly.
- Runtime A (MCP client) is deployed with `protocolConfiguration.serverProtocol
  = "HTTP"` (the standard agent protocol: POST `/invocations` + GET `/ping`),
  provided by the `bedrock_agentcore.runtime.BedrockAgentCoreApp` SDK helper.
- Gateway ingress auth is Cognito (`CUSTOM_JWT`) for simplicity/portability;
  swapping to `AWS_IAM` ingress is possible but requires SigV4-signing the
  streamable-HTTP MCP session yourself, which most MCP client libraries don't
  do out of the box.
- The demo Cognito user's password is written in plaintext to
  `infra/state.json` for convenience -- fine for a throwaway test pool, not a
  pattern to carry into production. **`infra/state.json` is gitignored** for
  exactly this reason -- it accumulates every ARN/URL/secret the scripts
  create as you go. `infra/state.example.json` shows its shape with
  placeholder values if you want to see what it looks like without running
  anything. Nothing else in this repo -- no source file -- has a real
  credential hardcoded into it; everything reads from `state.json` or
  environment variables at runtime.
- AgentCore Gateway namespaces every tool it aggregates as
  `{target_name}___{tool_name}` (e.g. `mcp-demo-server-target___list_products`)
  so tool names stay unique if a gateway ever fronts multiple targets --
  `test/test_end_to_end.py` and any payload sent to Runtime A need the
  fully-qualified name, not the bare tool name the MCP server itself defines.
- Nothing is torn down automatically. See "Tear down" below.

## A few extra scripts you'll find in `infra/`

Beyond the numbered 01-06 sequence, a couple of one-off scripts exist from
debugging a live deployment and are handy to keep around:
- `fix_cleanup.py` -- lists actual gateway/target/runtime state directly from
  AWS (not `state.json`) and deletes stale resources independently, so one
  failure doesn't block the rest. Useful whenever `state.json` and reality
  drift apart.
- `07_update_server_runtime_image.py` -- pushes a new image to an *existing*
  Runtime B in place via `update_agent_runtime`, instead of delete+recreate.
  Keeps the same ARN, so a registered Gateway target stays valid.
- `08_resync_gateway_target.py` -- AgentCore Gateway only introspects a
  target's `tools/list` at `create_gateway_target` time, and doesn't retry on
  its own if that first attempt fails. This deletes and recreates the target
  (waiting out the async deletion properly) to force a fresh sync attempt.
- `check_target_status.py` -- polls a gateway target's sync status and prints
  `statusReasons` on failure, instead of only finding out indirectly via
  `Unknown tool` errors from a client.

## Tear down

```bash
python3 infra/99_teardown.py
```

(deletes both AgentCore Runtimes, the Gateway + target, the Cognito pool,
the ECR repos' images, and the DynamoDB table -- IAM roles are left in place
in case you want to redeploy; delete them manually via the IAM console/CLI
if you're done for good).

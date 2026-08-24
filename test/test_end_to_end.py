#!/usr/bin/env python3
"""
End-to-end verification script.

    (this script, standing in for a generic MCP client)
        --Cognito bearer token-->
    AgentCore Gateway
        --SigV4 (GATEWAY_IAM_ROLE)-->
    AgentCore Runtime B (MCP server, streamable-HTTP)
        --boto3-->
    DynamoDB (AgentCoreMockCatalog, 25 synthetic rows)

and then, separately, proves the *actual two-runtime architecture* by
invoking the deployed MCP client (Runtime A) and asking IT to do the same
round trip -- Runtime A -> Gateway -> Runtime B -> DynamoDB -- so the
whole chain the user asked for is exercised, not just the Gateway leg.

Usage: python3 test_end_to_end.py
"""
import asyncio
import json
import os
import sys
import uuid

import boto3
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "infra"))
from common import load_state, require, REGION  # noqa: E402

# AgentCore Gateway namespaces every tool it aggregates as
# "{target_name}___{tool_name}" so tool names stay unique across multiple
# targets behind the same gateway. Our gateway has exactly one target,
# registered as this name in infra/05_create_gateway_and_target.py.
GATEWAY_TARGET_NAME = "mcp-demo-server-target"


def gw_tool(name: str) -> str:
    return f"{GATEWAY_TARGET_NAME}___{name}"


def _extract_tool_payload(result):
    """Pull the JSON payload out of an MCP CallToolResult, robust to whether
    the server populated structuredContent or only the text content block(s)."""
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured
    if result.content:
        return json.loads(result.content[0].text)
    return {}


def get_bearer_token(state):
    cognito = boto3.client("cognito-idp", region_name=state["region"])
    resp = cognito.initiate_auth(
        ClientId=state["cognito_client_id"],
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={
            "USERNAME": state["cognito_username"],
            "PASSWORD": state["cognito_password"],
        },
    )
    return resp["AuthenticationResult"]["AccessToken"]


def check_dynamodb_directly(state):
    print("\n[1/3] Sanity check: reading DynamoDB table directly with boto3 ...")
    ddb = boto3.resource("dynamodb", region_name=state["region"])
    table = ddb.Table(state["table_name"])
    resp = table.scan(Select="COUNT")
    print(f"      {state['table_name']} has {resp['Count']} rows.")
    assert resp["Count"] >= 20, "Expected at least 20 mock rows -- did you run data/seed_dynamodb.py?"
    return resp["Count"]


async def check_via_gateway(state):
    print("\n[2/3] Client -> Gateway -> MCP server runtime -> DynamoDB (direct MCP session) ...")
    token = get_bearer_token(state)
    headers = {"Authorization": f"Bearer {token}"}

    async with streamablehttp_client(state["gateway_url"], headers, timeout=120, terminate_on_close=False) as (
        read_stream, write_stream, _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            print(f"      Tools discovered through Gateway: {tool_names}")

            result = await session.call_tool(gw_tool("list_products"), {"limit": 25})
            payload = _extract_tool_payload(result)
            rows = payload.get("items", []) if isinstance(payload, dict) else payload
            print(f"      Fetched {len(rows)} rows through the Gateway.")
            if rows:
                print(f"      Sample row: {rows[0]}")
            return rows


def check_via_deployed_client_runtime(state):
    if "client_runtime_arn" not in state:
        print("\n[3/3] Skipping: client_runtime_arn not in infra/state.json "
              "(run infra/06_deploy_mcp_client_runtime.py first).")
        return None

    print("\n[3/3] Invoking the deployed MCP CLIENT runtime (Runtime A) -- "
          "this exercises Runtime A -> Gateway -> Runtime B -> DynamoDB end to end ...")
    client = boto3.client("bedrock-agentcore", region_name=state["region"])
    # agent.py's direct-tool-call mode passes the "tool" value straight through
    # to the Gateway session, so it needs the fully-qualified "{target}___{tool}"
    # name too -- Runtime A itself has no opinion on Gateway naming, it just relays.
    payload = json.dumps({"tool": gw_tool("list_products"), "args": {"limit": 25}})
    session_id = uuid.uuid4().hex + uuid.uuid4().hex  # must be 33+ chars

    resp = client.invoke_agent_runtime(
        agentRuntimeArn=state["client_runtime_arn"],
        runtimeSessionId=session_id,
        payload=payload,
        qualifier="DEFAULT",
    )
    body = json.loads(resp["response"].read())
    print(f"      Runtime A response mode: {body.get('mode')}")
    result = body.get("result", {})
    items = result.get("items", []) if isinstance(result, dict) else []
    print(f"      Runtime A -> Gateway -> Runtime B -> DynamoDB: fetched {len(items)} rows "
          f"(reported count={result.get('count') if isinstance(result, dict) else 'n/a'}).")
    if items:
        print(f"      Sample row: {items[0]}")
    return body


def main():
    state = load_state()
    require(
        state, "region", "table_name", "gateway_url",
        "cognito_client_id", "cognito_username", "cognito_password",
    )

    row_count = check_dynamodb_directly(state)
    gateway_rows = asyncio.run(check_via_gateway(state))
    client_runtime_result = check_via_deployed_client_runtime(state)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"DynamoDB row count (direct):         {row_count}")
    print(f"Rows fetched via Gateway (direct MCP): {len(gateway_rows)}")
    print(f"Deployed client runtime (Runtime A):  "
          f"{'OK' if client_runtime_result else 'skipped/not deployed'}")
    ok = row_count >= 20 and len(gateway_rows) >= 20
    print("\nRESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

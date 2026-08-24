#!/usr/bin/env python3
"""
MCP client agent.

Deployed to AgentCore Runtime A (protocolConfiguration.serverProtocol = "HTTP",
the default agent protocol: container serves POST /invocations + GET /ping on
port 8080). BedrockAgentCoreApp (from the bedrock_agentcore SDK) provides that
HTTP surface for us.

On each invocation this agent:
  1. Fetches a fresh Cognito bearer token (the AgentCore Gateway's ingress
     authorizer is CUSTOM_JWT / Cognito).
  2. Opens an MCP session to the AgentCore Gateway URL (NOT directly to the
     MCP server runtime -- the whole point of the Gateway is that the client
     never talks to Runtime B directly).
  3. Either:
       a) calls a named tool directly and returns the raw result (payload
          contains "tool"/"args") -- deterministic, good for scripted tests, or
       b) hands the discovered tools to a Strands Agent and lets the model
          decide how to answer a natural-language prompt.
"""
import os
import json
import boto3
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient

GATEWAY_URL = os.environ["GATEWAY_URL"]  # e.g. https://<gateway-id>.gateway.bedrock-agentcore.<region>.amazonaws.com/mcp
REGION = os.environ.get("AWS_REGION", "us-east-1")
COGNITO_USER_POOL_ID = os.environ["COGNITO_USER_POOL_ID"]
COGNITO_CLIENT_ID = os.environ["COGNITO_CLIENT_ID"]
COGNITO_USERNAME = os.environ["COGNITO_USERNAME"]
COGNITO_PASSWORD = os.environ["COGNITO_PASSWORD"]

app = BedrockAgentCoreApp()
_cognito = boto3.client("cognito-idp", region_name=REGION)


def _get_bearer_token() -> str:
    resp = _cognito.initiate_auth(
        ClientId=COGNITO_CLIENT_ID,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": COGNITO_USERNAME, "PASSWORD": COGNITO_PASSWORD},
    )
    return resp["AuthenticationResult"]["AccessToken"]


def _transport_factory():
    token = _get_bearer_token()
    headers = {"Authorization": f"Bearer {token}"}
    return streamablehttp_client(GATEWAY_URL, headers)


def _extract_json_payload(mcp_tool_result):
    """Pull a plain-JSON payload out of a Strands MCPToolResult so the
    AgentCore Runtime response body is guaranteed to be JSON-serializable,
    rather than returning the raw SDK object."""
    try:
        content = mcp_tool_result.get("content") if hasattr(mcp_tool_result, "get") else mcp_tool_result["content"]
        if content:
            text = content[0].get("text") if hasattr(content[0], "get") else content[0]["text"]
            return json.loads(text)
    except Exception:  # noqa: BLE001 -- best-effort extraction, fall through
        pass
    return {"raw": str(mcp_tool_result)}


@app.entrypoint
def invoke(payload):
    mcp_client = MCPClient(_transport_factory)

    with mcp_client:
        # Direct, deterministic tool call -- used by the automated test script.
        if "tool" in payload:
            tool_name = payload["tool"]
            tool_args = payload.get("args", {})
            result = mcp_client.call_tool_sync(
                tool_use_id="test-call-1",
                name=tool_name,
                arguments=tool_args,
            )
            return {"mode": "direct_tool_call", "tool": tool_name, "result": _extract_json_payload(result)}

        # Natural-language mode -- lets a Strands Agent pick the tool(s).
        tools = mcp_client.list_tools_sync()
        model = BedrockModel(model_id=os.environ.get(
            "BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"
        ))
        agent = Agent(model=model, tools=tools)
        prompt = payload.get("prompt", "List the mock products in the catalog table and summarize them.")
        result = agent(prompt)
        return {"mode": "agent", "prompt": prompt, "result": str(result)}


if __name__ == "__main__":
    app.run()

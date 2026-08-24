#!/usr/bin/env python3
"""
Deploys the MCP server image to AgentCore Runtime B, with
protocolConfiguration.serverProtocol = "MCP" (the container serves
streamable-HTTP MCP at 0.0.0.0:8000/mcp; AgentCore Runtime fronts that with
its own invocation endpoint + auth).

No authorizerConfiguration is set here, which means this Runtime's default
inbound auth is AWS IAM/SigV4 -- exactly what the Gateway's
GATEWAY_IAM_ROLE credential provider (configured in 05_create_gateway_and_target.py)
expects to call with.
"""
from common import session, load_state, save_state, require, wait_for_runtime_ready

RUNTIME_NAME = "mcp_demo_server"


def main():
    state = load_state()
    require(state, "server_role_arn", "server_image_uri", "table_name", "region")

    client = session().client("bedrock-agentcore-control")

    resp = client.create_agent_runtime(
        agentRuntimeName=RUNTIME_NAME,
        agentRuntimeArtifact={"containerConfiguration": {"containerUri": state["server_image_uri"]}},
        roleArn=state["server_role_arn"],
        networkConfiguration={"networkMode": "PUBLIC"},
        protocolConfiguration={"serverProtocol": "MCP"},
        environmentVariables={
            "DDB_TABLE_NAME": state["table_name"],
            "AWS_REGION": state["region"],
        },
        lifecycleConfiguration={"idleRuntimeSessionTimeout": 900, "maxLifetime": 3600},
    )
    runtime_arn = resp["agentRuntimeArn"]
    runtime_id = resp["agentRuntimeId"]
    print(f"Creating MCP server runtime: {runtime_arn}")

    wait_for_runtime_ready(client, runtime_id)

    encoded_arn = runtime_arn.replace(":", "%3A").replace("/", "%2F")
    invocation_url = (
        f"https://bedrock-agentcore.{state['region']}.amazonaws.com"
        f"/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
    )

    save_state({
        "server_runtime_arn": runtime_arn,
        "server_runtime_id": runtime_id,
        "server_runtime_invocation_url": invocation_url,
    })
    print("\nMCP server runtime is READY.")
    print(f"  runtime_arn    = {runtime_arn}")
    print(f"  invocation_url = {invocation_url}")


if __name__ == "__main__":
    main()

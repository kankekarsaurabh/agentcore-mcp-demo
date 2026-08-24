#!/usr/bin/env python3
"""
Deploys the MCP client / Strands agent image to AgentCore Runtime A, with
protocolConfiguration.serverProtocol = "HTTP" (the default agent protocol:
POST /invocations + GET /ping on port 8080, handled by BedrockAgentCoreApp).

The container is wired with the Gateway URL + Cognito credentials so it can
mint its own bearer tokens and open an MCP session to the Gateway on every
invocation.
"""
from common import session, load_state, save_state, require, wait_for_runtime_ready

RUNTIME_NAME = "mcp_demo_client"


def main():
    state = load_state()
    require(
        state,
        "client_role_arn", "client_image_uri", "gateway_url",
        "cognito_pool_id", "cognito_client_id", "cognito_username", "cognito_password",
    )

    client = session().client("bedrock-agentcore-control")

    resp = client.create_agent_runtime(
        agentRuntimeName=RUNTIME_NAME,
        agentRuntimeArtifact={"containerConfiguration": {"containerUri": state["client_image_uri"]}},
        roleArn=state["client_role_arn"],
        networkConfiguration={"networkMode": "PUBLIC"},
        protocolConfiguration={"serverProtocol": "HTTP"},
        environmentVariables={
            "GATEWAY_URL": state["gateway_url"],
            "COGNITO_USER_POOL_ID": state["cognito_pool_id"],
            "COGNITO_CLIENT_ID": state["cognito_client_id"],
            "COGNITO_USERNAME": state["cognito_username"],
            "COGNITO_PASSWORD": state["cognito_password"],
            "AWS_REGION": state["region"],
        },
        lifecycleConfiguration={"idleRuntimeSessionTimeout": 900, "maxLifetime": 3600},
    )
    runtime_arn = resp["agentRuntimeArn"]
    runtime_id = resp["agentRuntimeId"]
    print(f"Creating MCP client runtime: {runtime_arn}")

    wait_for_runtime_ready(client, runtime_id)

    save_state({"client_runtime_arn": runtime_arn, "client_runtime_id": runtime_id})
    print("\nMCP client runtime is READY.")
    print(f"  runtime_arn = {runtime_arn}")


if __name__ == "__main__":
    main()

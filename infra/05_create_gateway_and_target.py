#!/usr/bin/env python3
"""
Creates the AgentCore Gateway and registers the MCP server Runtime (Runtime B)
as an MCP-server target behind it.

  - Ingress auth (client -> Gateway):  CUSTOM_JWT via the Cognito user pool
    created in 03_setup_cognito.py. Callers present
    `Authorization: Bearer <cognito access token>`.

  - Egress auth (Gateway -> Runtime B): GATEWAY_IAM_ROLE / IAM SigV4. The
    Gateway's own execution role (AgentCoreGatewayRole) signs the call to
    Runtime B's invocation URL using the `bedrock-agentcore` service name --
    this is why Runtime B was deployed WITHOUT a JWT authorizer (it defaults
    to IAM auth).

This is the piece that makes the architecture the user asked for real: the
MCP client never talks to the MCP server runtime directly, it only ever
talks to the Gateway URL.
"""
from common import session, load_state, save_state, require, wait_for_gateway_ready

GATEWAY_NAME = "mcp-demo-gateway"
TARGET_NAME = "mcp-demo-server-target"


def main():
    state = load_state()
    require(
        state,
        "gateway_role_arn", "cognito_discovery_url", "cognito_client_id",
        "server_runtime_invocation_url", "region",
    )

    client = session().client("bedrock-agentcore-control")

    gw_resp = client.create_gateway(
        name=GATEWAY_NAME,
        description="Gateway federating the demo MCP server (DynamoDB tool)",
        roleArn=state["gateway_role_arn"],
        protocolType="MCP",
        # NOTE: deliberately NOT setting searchType="SEMANTIC" here. That mode
        # collapses tools/list down to a single x_amz_bedrock_agentcore_search
        # meta-tool instead of listing the target's real tools directly, and
        # AWS docs are explicit that it can only be set at creation time and
        # can't be toggled afterward -- so we just don't opt into it.
        protocolConfiguration={"mcp": {"supportedVersions": ["2025-06-18"]}},
        authorizerType="CUSTOM_JWT",
        authorizerConfiguration={
            "customJWTAuthorizer": {
                "discoveryUrl": state["cognito_discovery_url"],
                "allowedClients": [state["cognito_client_id"]],
            }
        },
    )
    gateway_id = gw_resp["gatewayId"]
    gateway_url = gw_resp["gatewayUrl"]
    print(f"Creating gateway {gateway_id} ...")

    wait_for_gateway_ready(client, gateway_id)

    target_resp = client.create_gateway_target(
        gatewayIdentifier=gateway_id,
        name=TARGET_NAME,
        targetConfiguration={
            "mcp": {
                "mcpServer": {
                    "endpoint": state["server_runtime_invocation_url"],
                }
            }
        },
        credentialProviderConfigurations=[
            {
                "credentialProviderType": "GATEWAY_IAM_ROLE",
                "credentialProvider": {
                    "iamCredentialProvider": {
                        "service": "bedrock-agentcore",
                        "region": state["region"],
                    }
                },
            }
        ],
    )
    print(f"Created gateway target: {target_resp.get('targetId', target_resp)}")

    save_state({
        "gateway_id": gateway_id,
        "gateway_arn": gw_resp["gatewayArn"],
        "gateway_url": gateway_url,
        "gateway_target_id": target_resp.get("targetId"),
    })
    print("\nGateway is READY.")
    print(f"  gateway_id  = {gateway_id}")
    print(f"  gateway_url = {gateway_url}")


if __name__ == "__main__":
    main()

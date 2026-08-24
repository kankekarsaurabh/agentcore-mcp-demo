#!/usr/bin/env python3
"""
Pushes the (fixed) server image to the EXISTING Runtime B in place via
update_agent_runtime, instead of delete+recreate. Keeps the same runtime
ARN, so the already-registered Gateway target endpoint stays valid.
"""
from common import session, load_state, save_state, require, wait_for_runtime_ready


def main():
    state = load_state()
    require(state, "server_runtime_id", "server_role_arn", "server_image_uri")

    client = session().client("bedrock-agentcore-control")

    resp = client.update_agent_runtime(
        agentRuntimeId=state["server_runtime_id"],
        agentRuntimeArtifact={"containerConfiguration": {"containerUri": state["server_image_uri"]}},
        roleArn=state["server_role_arn"],
        networkConfiguration={"networkMode": "PUBLIC"},
        protocolConfiguration={"serverProtocol": "MCP"},
    )
    print(f"Updating server runtime {state['server_runtime_id']} -> status={resp.get('status')}")

    wait_for_runtime_ready(client, state["server_runtime_id"])
    print("\nServer runtime updated and READY with the fixed image.")


if __name__ == "__main__":
    main()

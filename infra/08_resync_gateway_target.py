#!/usr/bin/env python3
"""
The Gateway only attempts to introspect a target's tools/list at
create_gateway_target time (and apparently doesn't retry on its own once a
target lands in SYNCHRONIZE_UNSUCCESSFUL). Now that Runtime B's image is
fixed, delete the broken target and recreate it against the SAME gateway so
the introspection is retried against the working container.
"""
import time
from common import session, load_state, save_state, require

TARGET_NAME = "mcp-demo-server-target"


def target_is_gone(client, gateway_id, target_id):
    try:
        client.get_gateway_target(gatewayIdentifier=gateway_id, targetId=target_id)
        return False
    except client.exceptions.ResourceNotFoundException:
        return True


def main():
    state = load_state()
    require(
        state,
        "gateway_id", "gateway_target_id", "server_runtime_invocation_url", "region",
    )

    client = session().client("bedrock-agentcore-control")
    gateway_id = state["gateway_id"]
    old_target_id = state["gateway_target_id"]

    if target_is_gone(client, gateway_id, old_target_id):
        print(f"Target {old_target_id} is already gone (deleted previously).")
    else:
        print(f"Deleting stale target {old_target_id} ...")
        try:
            client.delete_gateway_target(gatewayIdentifier=gateway_id, targetId=old_target_id)
        except client.exceptions.ResourceNotFoundException:
            pass  # already gone -- fine

        print("Waiting for deletion to actually finish (this is async) ...")
        for _ in range(30):
            if target_is_gone(client, gateway_id, old_target_id):
                print(f"Target {old_target_id} confirmed deleted.")
                break
            print("  still deleting...")
            time.sleep(10)
        else:
            raise SystemExit(f"Timed out waiting for target {old_target_id} to finish deleting.")

    print("Recreating target against the fixed server runtime ...")
    target_resp = client.create_gateway_target(
        gatewayIdentifier=state["gateway_id"],
        name=TARGET_NAME,
        targetConfiguration={
            "mcp": {"mcpServer": {"endpoint": state["server_runtime_invocation_url"]}}
        },
        credentialProviderConfigurations=[
            {
                "credentialProviderType": "GATEWAY_IAM_ROLE",
                "credentialProvider": {
                    "iamCredentialProvider": {"service": "bedrock-agentcore", "region": state["region"]}
                },
            }
        ],
    )
    new_target_id = target_resp.get("targetId")
    print(f"Created target {new_target_id}, status={target_resp.get('status')}")

    save_state({"gateway_target_id": new_target_id})
    print("\nSaved new gateway_target_id to state.json.")
    print("Check its status with infra/check_target_status.py before rerunning the test.")


if __name__ == "__main__":
    main()

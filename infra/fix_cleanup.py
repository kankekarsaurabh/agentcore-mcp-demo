#!/usr/bin/env python3
"""
One-off repair script: lists actual gateway/target/runtime state from AWS
(ground truth, not state.json guesses), deletes the broken semantic-search
gateway + its target + the stale client runtime, and cleans state.json.
Each deletion is independent -- one failing doesn't block the others.
"""
from common import session, load_state, save_state

GATEWAY_NAME = "mcp-demo-gateway"
CLIENT_RUNTIME_NAME = "mcp_demo_client"


def main():
    control = session().client("bedrock-agentcore-control")
    state = load_state()

    print("--- listing gateways ---")
    gateways = control.list_gateways().get("items", [])
    for gw in gateways:
        print(f"  {gw.get('gatewayId')}  name={gw.get('name')}  status={gw.get('status')}")

    target_gateways = [g for g in gateways if g.get("name") == GATEWAY_NAME]
    for gw in target_gateways:
        gw_id = gw["gatewayId"]
        print(f"\n--- listing targets for gateway {gw_id} ---")
        try:
            targets = control.list_gateway_targets(gatewayIdentifier=gw_id).get("items", [])
        except Exception as e:  # noqa: BLE001
            print(f"  list_gateway_targets failed: {e}")
            targets = []
        for t in targets:
            print(f"  {t}")
            target_id = t.get("targetId")
            if target_id:
                try:
                    control.delete_gateway_target(gatewayIdentifier=gw_id, targetId=target_id)
                    print(f"  deleted target {target_id}")
                except Exception as e:  # noqa: BLE001
                    print(f"  failed to delete target {target_id}: {e}")

        try:
            control.delete_gateway(gatewayIdentifier=gw_id)
            print(f"deleted gateway {gw_id}")
        except Exception as e:  # noqa: BLE001
            print(f"failed to delete gateway {gw_id}: {e}")

    print("\n--- listing agent runtimes ---")
    runtimes = control.list_agent_runtimes().get("agentRuntimes", [])
    for rt in runtimes:
        name = rt.get("agentRuntimeName")
        rt_id = rt.get("agentRuntimeId")
        print(f"  {rt_id}  name={name}  status={rt.get('status')}")
        if name == CLIENT_RUNTIME_NAME and rt_id:
            try:
                control.delete_agent_runtime(agentRuntimeId=rt_id)
                print(f"  deleted client runtime {rt_id}")
            except Exception as e:  # noqa: BLE001
                print(f"  failed to delete client runtime {rt_id}: {e}")

    for k in ["gateway_id", "gateway_arn", "gateway_url", "gateway_target_id",
              "client_runtime_arn", "client_runtime_id"]:
        state.pop(k, None)
    save_state(state)
    print("\nstate.json cleaned of stale gateway/client-runtime keys.")


if __name__ == "__main__":
    main()

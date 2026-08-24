#!/usr/bin/env python3
"""Polls the gateway target's sync status until READY or a terminal failure."""
import time
from common import session, load_state, require


def main():
    state = load_state()
    require(state, "gateway_id", "gateway_target_id", "region")

    client = session().client("bedrock-agentcore-control")

    for _ in range(30):
        try:
            resp = client.get_gateway_target(
                gatewayIdentifier=state["gateway_id"], targetId=state["gateway_target_id"]
            )
        except client.exceptions.ResourceNotFoundException:
            print("Target not found -- state.json's gateway_target_id is stale "
                  "(likely deleted and not yet recreated). Re-run infra/08_resync_gateway_target.py.")
            return
        status = resp.get("status")
        print(f"status = {status}")
        if status == "READY":
            print("Target is READY -- tool sync succeeded.")
            return
        if status in ("FAILED", "SYNCHRONIZE_UNSUCCESSFUL", "UPDATE_UNSUCCESSFUL"):
            print("Target sync failed. statusReasons:")
            for r in resp.get("statusReasons", []):
                print(" -", r)
            return
        time.sleep(10)
    print("Timed out waiting for target sync.")


if __name__ == "__main__":
    main()

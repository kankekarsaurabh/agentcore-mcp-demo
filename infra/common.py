"""Shared helpers for the infra/ deployment scripts."""
import json
import os
import time
import boto3

STATE_PATH = os.path.join(os.path.dirname(__file__), "state.json")
REGION = os.environ.get("AWS_REGION", "us-east-1")


def session():
    return boto3.Session(region_name=REGION)


def account_id():
    return session().client("sts").get_caller_identity()["Account"]


def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {}


def save_state(update: dict):
    state = load_state()
    state.update(update)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, default=str)
    return state


def require(state: dict, *keys):
    missing = [k for k in keys if k not in state]
    if missing:
        raise SystemExit(
            f"Missing required state key(s) {missing} in {STATE_PATH}. "
            f"Run the earlier infra/NN_*.py scripts first."
        )


def wait_for_runtime_ready(client, agent_runtime_id, timeout_s=600, poll_s=10):
    """Poll GetAgentRuntime until status is READY (or a terminal failure)."""
    print(f"Waiting for agent runtime {agent_runtime_id} to become READY ...")
    deadline = time.time() + timeout_s
    last_status = None
    while time.time() < deadline:
        resp = client.get_agent_runtime(agentRuntimeId=agent_runtime_id)
        status = resp.get("status")
        if status != last_status:
            print(f"  status = {status}")
            last_status = status
        if status == "READY":
            return resp
        if status in ("CREATE_FAILED", "UPDATE_FAILED"):
            raise SystemExit(f"Agent runtime {agent_runtime_id} failed: {resp}")
        time.sleep(poll_s)
    raise SystemExit(f"Timed out waiting for agent runtime {agent_runtime_id} to become READY.")


def wait_for_gateway_ready(client, gateway_id, timeout_s=300, poll_s=10):
    print(f"Waiting for gateway {gateway_id} to become READY ...")
    deadline = time.time() + timeout_s
    last_status = None
    while time.time() < deadline:
        resp = client.get_gateway(gatewayIdentifier=gateway_id)
        status = resp.get("status")
        if status != last_status:
            print(f"  status = {status}")
            last_status = status
        if status == "READY":
            return resp
        if status == "FAILED":
            raise SystemExit(f"Gateway {gateway_id} failed: {resp}")
        time.sleep(poll_s)
    raise SystemExit(f"Timed out waiting for gateway {gateway_id} to become READY.")

#!/usr/bin/env python3
"""
Best-effort teardown of everything infra/*.py created (except IAM roles,
left in place for easy redeploy -- delete those manually if you're done).
"""
from botocore.exceptions import ClientError

from common import session, load_state, REGION


def safe(label, fn):
    try:
        fn()
        print(f"  [ok] {label}")
    except ClientError as e:
        print(f"  [skip] {label}: {e.response['Error']['Code']}")
    except Exception as e:  # noqa: BLE001
        print(f"  [skip] {label}: {e}")


def main():
    state = load_state()
    control = session().client("bedrock-agentcore-control")
    ecr = session().client("ecr")
    ddb = session().client("dynamodb")
    cognito = session().client("cognito-idp")

    if "client_runtime_id" in state:
        safe("delete client runtime (Runtime A)",
             lambda: control.delete_agent_runtime(agentRuntimeId=state["client_runtime_id"]))

    if "gateway_target_id" in state and "gateway_id" in state:
        safe("delete gateway target",
             lambda: control.delete_gateway_target(gatewayIdentifier=state["gateway_id"], targetId=state["gateway_target_id"]))

    if "gateway_id" in state:
        safe("delete gateway",
             lambda: control.delete_gateway(gatewayIdentifier=state["gateway_id"]))

    if "server_runtime_id" in state:
        safe("delete server runtime (Runtime B)",
             lambda: control.delete_agent_runtime(agentRuntimeId=state["server_runtime_id"]))

    for repo_key in ("agentcore-demo-mcp-server", "agentcore-demo-mcp-client"):
        safe(f"delete ECR repo {repo_key}",
             lambda repo_key=repo_key: ecr.delete_repository(repositoryName=repo_key, force=True))

    if "cognito_client_id" in state and "cognito_pool_id" in state:
        safe("delete Cognito app client",
             lambda: cognito.delete_user_pool_client(UserPoolId=state["cognito_pool_id"], ClientId=state["cognito_client_id"]))
    if "cognito_pool_id" in state:
        safe("delete Cognito user pool",
             lambda: cognito.delete_user_pool(UserPoolId=state["cognito_pool_id"]))

    if "table_name" in state:
        safe(f"delete DynamoDB table {state['table_name']}",
             lambda: ddb.delete_table(TableName=state["table_name"]))

    print("\nDone. IAM roles (AgentCoreMcpServerRole / AgentCoreMcpClientRole / "
          "AgentCoreGatewayRole) were left in place -- delete manually if desired.")


if __name__ == "__main__":
    main()

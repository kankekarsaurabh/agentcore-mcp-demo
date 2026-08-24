#!/usr/bin/env python3
"""
Creates the three IAM roles this demo needs:

  1. AgentCoreMcpServerRole  -- execution role for Runtime B (the MCP server).
                                 Needs DynamoDB read access on the mock table.
  2. AgentCoreMcpClientRole  -- execution role for Runtime A (the MCP client
                                 / Strands agent). Needs bedrock:InvokeModel
                                 and cognito-idp:InitiateAuth (to mint bearer
                                 tokens for the Gateway).
  3. AgentCoreGatewayRole    -- execution role for the Gateway itself. Needs
                                 bedrock-agentcore:InvokeAgentRuntime so the
                                 Gateway can call Runtime B's MCP endpoint via
                                 SigV4 (GATEWAY_IAM_ROLE credential provider).

All three trust bedrock-agentcore.amazonaws.com. Role ARNs are written to
infra/state.json for the later scripts to consume.
"""
import json
import time
import boto3
from botocore.exceptions import ClientError

from common import session, account_id, save_state, REGION

TABLE_NAME = "AgentCoreMockCatalog"

TRUST_POLICY_TEMPLATE = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AssumeRolePolicy",
            "Effect": "Allow",
            "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
            "Action": "sts:AssumeRole",
            "Condition": {
                "StringEquals": {"aws:SourceAccount": "{account_id}"},
                "ArnLike": {"aws:SourceArn": "arn:aws:bedrock-agentcore:{region}:{account_id}:*"},
            },
        }
    ],
}


def baseline_runtime_policy(acct, region, extra_statements=None):
    statements = [
        {
            "Sid": "ECRImageAccess",
            "Effect": "Allow",
            "Action": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
            "Resource": [f"arn:aws:ecr:{region}:{acct}:repository/*"],
        },
        {"Sid": "ECRTokenAccess", "Effect": "Allow", "Action": ["ecr:GetAuthorizationToken"], "Resource": "*"},
        {
            "Effect": "Allow",
            "Action": ["logs:DescribeLogStreams", "logs:CreateLogGroup"],
            "Resource": [f"arn:aws:logs:{region}:{acct}:log-group:/aws/bedrock-agentcore/runtimes/*"],
        },
        {
            "Effect": "Allow",
            "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
            "Resource": [f"arn:aws:logs:{region}:{acct}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"],
        },
        {"Effect": "Allow", "Action": ["logs:DescribeLogGroups"], "Resource": [f"arn:aws:logs:{region}:{acct}:log-group:*"]},
        {
            "Effect": "Allow",
            "Action": ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"],
            "Resource": ["*"],
        },
        {
            "Effect": "Allow",
            "Resource": "*",
            "Action": "cloudwatch:PutMetricData",
            "Condition": {"StringEquals": {"cloudwatch:namespace": "bedrock-agentcore"}},
        },
        {
            "Sid": "GetAgentAccessToken",
            "Effect": "Allow",
            "Action": [
                "bedrock-agentcore:GetWorkloadAccessToken",
                "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                "bedrock-agentcore:GetWorkloadAccessTokenForUserId",
            ],
            "Resource": [
                f"arn:aws:bedrock-agentcore:{region}:{acct}:workload-identity-directory/default",
                f"arn:aws:bedrock-agentcore:{region}:{acct}:workload-identity-directory/default/workload-identity/*",
            ],
        },
    ]
    if extra_statements:
        statements.extend(extra_statements)
    return {"Version": "2012-10-17", "Statement": statements}


def ensure_role(iam, role_name, trust_policy, description):
    try:
        resp = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description=description,
        )
        print(f"Created role {role_name}")
        time.sleep(10)  # IAM eventual consistency before attaching policies
        return resp["Role"]["Arn"]
    except ClientError as e:
        if e.response["Error"]["Code"] == "EntityAlreadyExists":
            print(f"Role {role_name} already exists, reusing it.")
            return iam.get_role(RoleName=role_name)["Role"]["Arn"]
        raise


def put_inline_policy(iam, role_name, policy_name, policy_doc):
    iam.put_role_policy(RoleName=role_name, PolicyName=policy_name, PolicyDocument=json.dumps(policy_doc))
    print(f"  attached inline policy {policy_name} to {role_name}")


def main():
    acct = account_id()
    region = REGION
    iam = session().client("iam")

    trust_policy = json.loads(
        json.dumps(TRUST_POLICY_TEMPLATE).replace("{account_id}", acct).replace("{region}", region)
    )

    # --- 1. MCP server runtime role -------------------------------------
    server_role_arn = ensure_role(iam, "AgentCoreMcpServerRole", trust_policy, "Execution role for MCP server AgentCore Runtime")
    server_policy = baseline_runtime_policy(acct, region, extra_statements=[
        {
            "Sid": "DynamoDBReadCatalog",
            "Effect": "Allow",
            "Action": ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan"],
            "Resource": [f"arn:aws:dynamodb:{region}:{acct}:table/{TABLE_NAME}"],
        }
    ])
    put_inline_policy(iam, "AgentCoreMcpServerRole", "McpServerBaseline", server_policy)

    # --- 2. MCP client runtime role --------------------------------------
    client_role_arn = ensure_role(iam, "AgentCoreMcpClientRole", trust_policy, "Execution role for MCP client AgentCore Runtime")
    client_policy = baseline_runtime_policy(acct, region, extra_statements=[
        {
            "Sid": "BedrockModelInvocation",
            "Effect": "Allow",
            "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            "Resource": ["arn:aws:bedrock:*::foundation-model/*", f"arn:aws:bedrock:{region}:{acct}:*"],
        },
        {
            "Sid": "CognitoAuthForGatewayToken",
            "Effect": "Allow",
            "Action": ["cognito-idp:InitiateAuth"],
            "Resource": "*",
        },
    ])
    put_inline_policy(iam, "AgentCoreMcpClientRole", "McpClientBaseline", client_policy)

    # --- 3. Gateway role ---------------------------------------------------
    gateway_trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "GatewayAssumeRolePolicy",
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {"StringEquals": {"aws:SourceAccount": acct}},
            }
        ],
    }
    gateway_role_arn = ensure_role(iam, "AgentCoreGatewayRole", gateway_trust_policy, "Execution role for AgentCore Gateway")
    gateway_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "InvokeMcpServerRuntime",
                "Effect": "Allow",
                "Action": ["bedrock-agentcore:InvokeAgentRuntime"],
                "Resource": [f"arn:aws:bedrock-agentcore:{region}:{acct}:runtime/*"],
            }
        ],
    }
    put_inline_policy(iam, "AgentCoreGatewayRole", "GatewayInvokeServerRuntime", gateway_policy)

    save_state({
        "account_id": acct,
        "region": region,
        "table_name": TABLE_NAME,
        "server_role_arn": server_role_arn,
        "client_role_arn": client_role_arn,
        "gateway_role_arn": gateway_role_arn,
    })
    print("\nSaved role ARNs to infra/state.json")
    print(f"  server_role_arn  = {server_role_arn}")
    print(f"  client_role_arn  = {client_role_arn}")
    print(f"  gateway_role_arn = {gateway_role_arn}")
    print("\nNote: IAM roles can take ~10-20s to propagate. If the next step")
    print("fails with an AccessDenied/assume-role error, just re-run it.")


if __name__ == "__main__":
    main()

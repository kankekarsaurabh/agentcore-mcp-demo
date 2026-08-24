#!/usr/bin/env python3
"""
Creates a Cognito User Pool + App Client + a test user, used as the
CUSTOM_JWT authorizer for the AgentCore Gateway (ingress auth: anything
calling the Gateway's MCP endpoint -- our client agent, or this repo's test
script -- presents a Cognito access token as a Bearer token).
"""
import secrets
import string

from common import session, save_state, REGION

POOL_NAME = "AgentCoreMcpDemoPool"
CLIENT_NAME = "AgentCoreMcpDemoClient"
USERNAME = "demo-user"


def random_password(n=16):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(n))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw)):
            return pw


def main():
    cognito = session().client("cognito-idp")
    region = REGION

    existing = cognito.list_user_pools(MaxResults=60)["UserPools"]
    pool = next((p for p in existing if p["Name"] == POOL_NAME), None)
    if pool:
        pool_id = pool["Id"]
        print(f"Reusing existing user pool {pool_id}")
    else:
        resp = cognito.create_user_pool(
            PoolName=POOL_NAME,
            Policies={"PasswordPolicy": {"MinimumLength": 8}},
        )
        pool_id = resp["UserPool"]["Id"]
        print(f"Created user pool {pool_id}")

    existing_clients = cognito.list_user_pool_clients(UserPoolId=pool_id, MaxResults=60)["UserPoolClients"]
    client = next((c for c in existing_clients if c["ClientName"] == CLIENT_NAME), None)
    if client:
        client_id = client["ClientId"]
        print(f"Reusing existing app client {client_id}")
    else:
        resp = cognito.create_user_pool_client(
            UserPoolId=pool_id,
            ClientName=CLIENT_NAME,
            GenerateSecret=False,
            ExplicitAuthFlows=["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
        )
        client_id = resp["UserPoolClient"]["ClientId"]
        print(f"Created app client {client_id}")

    password = random_password()
    try:
        cognito.admin_create_user(
            UserPoolId=pool_id,
            Username=USERNAME,
            MessageAction="SUPPRESS",
        )
        print(f"Created user {USERNAME}")
    except cognito.exceptions.UsernameExistsException:
        print(f"User {USERNAME} already exists, resetting password.")

    cognito.admin_set_user_password(
        UserPoolId=pool_id,
        Username=USERNAME,
        Password=password,
        Permanent=True,
    )

    discovery_url = f"https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/openid-configuration"

    save_state({
        "cognito_pool_id": pool_id,
        "cognito_client_id": client_id,
        "cognito_username": USERNAME,
        "cognito_password": password,
        "cognito_discovery_url": discovery_url,
    })
    print("\nSaved Cognito details to infra/state.json")
    print(f"  pool_id       = {pool_id}")
    print(f"  client_id     = {client_id}")
    print(f"  username      = {USERNAME}")
    print(f"  discovery_url = {discovery_url}")
    print("\n(NOTE: the demo user's password is stored in plaintext in infra/state.json")
    print(" for convenience -- this is a throwaway test pool, not a production pattern.)")


if __name__ == "__main__":
    main()

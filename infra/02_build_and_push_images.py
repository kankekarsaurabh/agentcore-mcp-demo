#!/usr/bin/env python3
"""
Creates two ECR repositories and builds+pushes the MCP server and MCP client
Docker images to them (linux/arm64, as AgentCore Runtime requires).

Uses boto3 (not the `aws` CLI) to create repos and fetch the ECR auth token,
then shells out to `docker buildx build --push`.
"""
import base64
import os
import subprocess
import sys

from common import session, account_id, save_state, REGION

REPO_NAMES = {
    "server": "agentcore-demo-mcp-server",
    "client": "agentcore-demo-mcp-client",
}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCKERFILE_DIRS = {
    "server": os.path.join(ROOT, "mcp-server"),
    "client": os.path.join(ROOT, "mcp-client"),
}


def ensure_repo(ecr, name):
    try:
        ecr.create_repository(repositoryName=name)
        print(f"Created ECR repo {name}")
    except ecr.exceptions.RepositoryAlreadyExistsException:
        print(f"ECR repo {name} already exists, reusing it.")


def docker_login(ecr, registry):
    auth = ecr.get_authorization_token()["authorizationData"][0]
    token = base64.b64decode(auth["authorizationToken"]).decode()
    username, password = token.split(":", 1)
    subprocess.run(
        ["docker", "login", "--username", username, "--password-stdin", registry],
        input=password.encode(),
        check=True,
    )


def buildx_push(build_dir, image_uri):
    subprocess.run(
        [
            "docker", "buildx", "build",
            "--platform", "linux/arm64",
            "-t", image_uri,
            "--push",
            build_dir,
        ],
        check=True,
    )


def main():
    acct = account_id()
    region = REGION
    ecr = session().client("ecr")
    registry = f"{acct}.dkr.ecr.{region}.amazonaws.com"

    docker_login(ecr, registry)

    image_uris = {}
    for key, repo_name in REPO_NAMES.items():
        ensure_repo(ecr, repo_name)
        image_uri = f"{registry}/{repo_name}:latest"
        print(f"\nBuilding + pushing {key} image -> {image_uri}")
        buildx_push(DOCKERFILE_DIRS[key], image_uri)
        image_uris[key] = image_uri

    save_state({
        "server_image_uri": image_uris["server"],
        "client_image_uri": image_uris["client"],
    })
    print("\nSaved image URIs to infra/state.json")
    print(f"  server_image_uri = {image_uris['server']}")
    print(f"  client_image_uri = {image_uris['client']}")


if __name__ == "__main__":
    main()

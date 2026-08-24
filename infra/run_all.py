#!/usr/bin/env python3
"""
Runs the full deployment sequence end to end:

  1. IAM roles
  2. Build + push both Docker images to ECR
  3. Cognito user pool (Gateway ingress auth)
  4. Deploy MCP server -> AgentCore Runtime B
  5. Create Gateway + register Runtime B as an MCP-server target
  6. Deploy MCP client -> AgentCore Runtime A

Run data/seed_dynamodb.py separately (or let this script call it) before
step 4, since the server's tools read from that table.

Usage: python3 run_all.py [--skip-seed]
"""
import argparse
import importlib
import sys
import os

INFRA_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(INFRA_DIR)
sys.path.insert(0, INFRA_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "data"))

STEPS = [
    ("01_create_iam_roles", "Creating IAM roles"),
    ("02_build_and_push_images", "Building + pushing Docker images"),
    ("03_setup_cognito", "Setting up Cognito (Gateway ingress auth)"),
    ("04_deploy_mcp_server_runtime", "Deploying MCP server runtime (Runtime B)"),
    ("05_create_gateway_and_target", "Creating Gateway + MCP server target"),
    ("06_deploy_mcp_client_runtime", "Deploying MCP client runtime (Runtime A)"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-seed", action="store_true", help="Skip seeding DynamoDB mock data")
    args = parser.parse_args()

    if not args.skip_seed:
        print("=" * 70)
        print("Seeding DynamoDB mock data")
        print("=" * 70)
        seed_module = importlib.import_module("seed_dynamodb")
        # seed_dynamodb.main() parses sys.argv itself; give it a clean argv.
        old_argv, sys.argv = sys.argv, ["seed_dynamodb.py"]
        try:
            seed_module.main()
        finally:
            sys.argv = old_argv

    for module_name, label in STEPS:
        print("\n" + "=" * 70)
        print(label)
        print("=" * 70)
        mod = importlib.import_module(module_name)
        mod.main()

    print("\n" + "=" * 70)
    print("Deployment complete. Run test/test_end_to_end.py to verify the chain.")
    print("=" * 70)


if __name__ == "__main__":
    main()

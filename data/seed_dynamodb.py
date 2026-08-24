#!/usr/bin/env python3
"""
Creates a DynamoDB table and seeds it with synthetic mock data.

This is the "source of truth" data that the MCP server (running on
AgentCore Runtime B) exposes as a tool. The MCP client (running on
AgentCore Runtime A) reaches it indirectly through the AgentCore Gateway.

Usage:
    python3 seed_dynamodb.py [--table-name AgentCoreMockCatalog] [--region us-east-1] [--rows 25]
"""
import argparse
import random
import boto3
from botocore.exceptions import ClientError

CATEGORIES = ["Electronics", "Home & Kitchen", "Outdoors", "Office", "Toys", "Apparel"]
ADJECTIVES = ["Compact", "Wireless", "Portable", "Ergonomic", "Rugged", "Smart",
              "Eco-Friendly", "Heavy-Duty", "Ultra-Light", "Premium"]
NOUNS = ["Speaker", "Backpack", "Desk Lamp", "Water Bottle", "Keyboard", "Tent",
         "Charger", "Notebook", "Drone", "Headphones", "Monitor Stand", "Toolkit",
         "Blender", "Sneakers", "Camera Mount", "Router", "Chair", "Mug", "Jacket",
         "Puzzle", "Flashlight", "Sensor Kit", "Whiteboard", "Cable Organizer",
         "Yoga Mat"]


def build_mock_rows(n: int):
    random.seed(42)  # deterministic mock data across runs
    rows = []
    for i in range(1, n + 1):
        adjective = ADJECTIVES[i % len(ADJECTIVES)]
        noun = NOUNS[i % len(NOUNS)]
        category = CATEGORIES[i % len(CATEGORIES)]
        price = round(random.uniform(9.99, 249.99), 2)
        rows.append({
            "product_id": f"P{i:04d}",
            "name": f"{adjective} {noun}",
            "category": category,
            "price_usd": price,
            "in_stock": bool(i % 3 != 0),
            "stock_count": random.randint(0, 500),
            "rating": round(random.uniform(3.0, 5.0), 1),
            "sku": f"SKU-{category[:3].upper()}-{i:04d}",
        })
    return rows


def create_table(ddb, table_name: str):
    try:
        ddb.create_table(
            TableName=table_name,
            KeySchema=[{"AttributeName": "product_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "product_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        print(f"Creating table {table_name} ...")
        ddb.get_waiter("table_exists").wait(TableName=table_name)
        print(f"Table {table_name} is ACTIVE.")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print(f"Table {table_name} already exists, reusing it.")
        else:
            raise


def seed_rows(resource, table_name: str, rows):
    table = resource.Table(table_name)
    with table.batch_writer(overwrite_by_pkeys=["product_id"]) as batch:
        for row in rows:
            item = dict(row)
            item["price_usd"] = str(item["price_usd"])  # Decimal-safe for DynamoDB
            item["rating"] = str(item["rating"])
            batch.put_item(Item=item)
    print(f"Seeded {len(rows)} rows into {table_name}.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--table-name", default="AgentCoreMockCatalog")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--rows", type=int, default=25)
    args = parser.parse_args()

    session = boto3.Session(region_name=args.region)
    ddb_client = session.client("dynamodb")
    ddb_resource = session.resource("dynamodb")

    create_table(ddb_client, args.table_name)
    rows = build_mock_rows(args.rows)
    seed_rows(ddb_resource, args.table_name, rows)

    # sanity check: scan count
    resp = ddb_resource.Table(args.table_name).scan(Select="COUNT")
    print(f"Table now reports {resp['Count']} items.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
MCP server exposing a DynamoDB tool.

Deployed to AgentCore Runtime B (protocolConfiguration.serverProtocol = "MCP").
AgentCore Runtime requires the container to serve streamable-HTTP MCP at
0.0.0.0:8000/mcp -- FastMCP does this by default when run with
transport="streamable-http".

This server is registered as an MCP-server target behind an AgentCore
Gateway; the Gateway (not the client) is what actually calls this
container's /mcp endpoint.
"""
import os
import boto3
from mcp.server.fastmcp import FastMCP

TABLE_NAME = os.environ.get("DDB_TABLE_NAME", "AgentCoreMockCatalog")
REGION = os.environ.get("AWS_REGION", "us-east-1")
# Optional: point at a local/mock DynamoDB endpoint (moto, LocalStack) for testing.
DDB_ENDPOINT_URL = os.environ.get("DDB_ENDPOINT_URL") or None

_ddb = boto3.resource("dynamodb", region_name=REGION, endpoint_url=DDB_ENDPOINT_URL)
_table = _ddb.Table(TABLE_NAME)

mcp = FastMCP(host="0.0.0.0", stateless_http=True)


@mcp.tool()
def list_products(category: str = "", limit: int = 20) -> dict:
    """List mock product rows from the DynamoDB catalog table.

    Args:
        category: Optional category filter (e.g. "Electronics"). Empty = all categories.
        limit: Max number of rows to return (default 20, max 100).

    Returns a dict of the form {"count": <int>, "items": [<row>, ...]} --
    always a single JSON object, not a bare list, so MCP clients get one
    predictable content block back regardless of how many rows matched.
    """
    limit = max(1, min(int(limit), 100))
    scan_kwargs = {}
    if category:
        scan_kwargs["FilterExpression"] = boto3.dynamodb.conditions.Attr("category").eq(category)

    items = []
    last_evaluated_key = None
    # DynamoDB Scan pages internally (1MB/page); loop until we have `limit`
    # rows or the table is exhausted.
    while len(items) < limit:
        if last_evaluated_key:
            scan_kwargs["ExclusiveStartKey"] = last_evaluated_key
        resp = _table.scan(**scan_kwargs)
        items.extend(resp.get("Items", []))
        last_evaluated_key = resp.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break

    items = items[:limit]
    return {"count": len(items), "items": items}


@mcp.tool()
def get_product(product_id: str) -> dict:
    """Fetch a single product row by its product_id (e.g. "P0001") from DynamoDB.

    Args:
        product_id: The primary key of the product row.
    """
    resp = _table.get_item(Key={"product_id": product_id})
    return resp.get("Item", {"error": f"No product found for product_id={product_id}"})


@mcp.tool()
def count_products() -> dict:
    """Return the total number of rows currently in the DynamoDB catalog table."""
    resp = _table.scan(Select="COUNT")
    return {"table": TABLE_NAME, "count": resp["Count"]}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")

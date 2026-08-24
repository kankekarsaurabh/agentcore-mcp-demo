# AgentCore Runtime requires linux/arm64 images.
# Build with: docker buildx build --platform linux/arm64 -t <ecr-uri>:latest --push .
FROM --platform=linux/arm64 python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

# AgentCore Runtime MCP protocol: container must listen on 0.0.0.0:8000/mcp
EXPOSE 8000

ENV AWS_REGION=us-east-1
ENV DDB_TABLE_NAME=AgentCoreMockCatalog

CMD ["python3", "server.py"]

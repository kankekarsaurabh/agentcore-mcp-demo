# AgentCore Runtime requires linux/arm64 images.
# Build with: docker buildx build --platform linux/arm64 -t <ecr-uri>:latest --push .
FROM --platform=linux/arm64 python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py .

# AgentCore Runtime HTTP protocol: container must serve POST /invocations
# and GET /ping on port 8080. BedrockAgentCoreApp handles this for us.
EXPOSE 8080

ENV AWS_REGION=us-east-1

CMD ["python3", "agent.py"]

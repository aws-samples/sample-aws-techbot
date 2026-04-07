FROM --platform=linux/arm64 python:3.12-slim

RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 uv (包含 uvx，aws-pricing skill 需要)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY --from=ghcr.io/astral-sh/uv:latest /uvx /usr/local/bin/uvx

# 安装 Python 依赖
COPY pyproject.toml .
RUN uv pip install --system --no-cache -r pyproject.toml

# 复制应用代码
COPY main.py gateway_cognito.py ./

EXPOSE 8080

ENV PYTHONUNBUFFERED=1
CMD ["python3", "main.py"]

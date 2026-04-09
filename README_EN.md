# AWS TechBot

[![License: MIT-0](https://img.shields.io/badge/License-MIT--0-yellow.svg)](LICENSE)
[![IaC: CloudFormation](https://img.shields.io/badge/IaC-CloudFormation-orange.svg)](deploy/template.yaml)
[![Powered by AgentCore](https://img.shields.io/badge/Powered%20by-Amazon%20Bedrock%20AgentCore-blue.svg)](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/)
[![Built with Strands](https://img.shields.io/badge/Built%20with-Strands%20Agents-green.svg)](https://github.com/strands-agents/sdk-python)

English | [简体中文](README.md)

An AI-powered AWS technical assistant built with [Strands Agents SDK](https://github.com/strands-agents/sdk-python) and [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/).

Tools are managed through AgentCore Gateway — the Agent automatically discovers all available tools at startup.

## Use Cases

- **Documentation Lookup** — @mention the bot in Feishu/Lark to query AWS service docs, best practices, and architectural guidance
- **Configuration & Tutorials** — Look up configuration steps, tutorials, and sample code for AWS services
- **Cost Estimation** — Real-time pricing queries for both AWS Global and China regions
- **Troubleshooting** — Quickly find troubleshooting guides, quota limits, error codes, and operational SOPs

## Deployment

### Prerequisites: Create a Feishu/Lark App

Before deploying, create an app on the Feishu Open Platform to get the App ID and App Secret:

1. Go to [Feishu Open Platform](https://open.feishu.cn/app?lang=en-US) and create an enterprise app
2. Go to **Credentials & Basic Info**, copy **App ID** and **App Secret**
3. Enable **Bot** capability
4. Configure permissions
5. Copy Verification Code

> See the [Feishu Bot Setup Guide](docs/feishu-setup-zh.md) (Steps 1-5) for detailed instructions

### One-Click CloudFormation Deployment

| Region | Deploy |
|--------|--------|
| US West (Oregon) | [![Launch Stack](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://us-west-2.console.aws.amazon.com/cloudformation/home?region=us-west-2#/stacks/quickcreate?templateURL=https://haomiaoj-yuzeli-aws-techbot-us-west-2.s3.us-west-2.amazonaws.com/template.yaml&stackName=TechBot) |

Click the button and fill in the parameters. The stack creates:
- **AgentCore Gateway** — Unified MCP tool endpoint + Cognito auth
- **Gateway Targets** — 4 Lambdas (Global Knowledge, China Knowledge, Pricing, Customer Stories)
- **AgentCore Runtime** — Runs the TechBot container
- **AgentCore Memory** (optional) — Multi-turn conversation memory
- **API Gateway** — `/chat` POST endpoint for Feishu webhook
- **Handler Lambda** — Receives Feishu events, filters @all, async invokes worker
- **Worker Lambda** — Calls AgentCore, updates Feishu card with response

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| Model ID | Pre-filled | Nova Pro, GLM-5, MiniMax M2.5, or DeepSeek V3.2 (only Nova Pro supports image input) |
| Enable Memory | Pre-filled | `true` for multi-turn memory, `false` for stateless |
| Memory Expiry Days | Pre-filled | Memory expiry in days (7-365) |
| Feishu App ID | **Required** | Feishu app credentials |
| Feishu App Secret | **Required** | Feishu app credentials |
| Feishu Verification Token | **Required** | Feishu webhook verification token (Open Platform → Events & Callbacks → Encryption Strategy) |

Leave all other options (Tags, Permissions, Stack failure options, etc.) as default.
Check **I acknowledge that AWS CloudFormation might create IAM resources with custom names** at the bottom.
Click **Create stack** and wait for `CREATE_COMPLETE` (~5 minutes).

### Post-Deployment: Complete Feishu Configuration

After the stack is deployed, copy **FeishuEventSubscriptionUrl** from Outputs and complete the Feishu setup:

1. **Configure Event Subscription** — Paste the URL into Feishu Open Platform → Events & Callbacks → Request URL
2. **Add Events** — Add `im.message.receive_v1` event
3. **Publish App** — Create a version and submit for approval
4. **Add to Group** — Add the bot to a Feishu group

> See the [Feishu Bot Setup Guide](docs/feishu-setup-zh.md) (Steps 6-9) for detailed instructions

### Done!
> See the [Usage Guide](docs/usage-guide-zh.md) for features and examples

## Architecture

```
AgentCore Runtime (Docker Container)
        │
        └── Agent (Bedrock Model) → MCPClient
                                     │
                          AgentCore Gateway (MCP endpoint + Cognito Auth)
                                     │
                    ┌────────────────┼─────────────┐────────────┐
                    │                │             │            │
              Global Knowledge  China Knowledge  Pricing  Customer Stories
                (Lambda)          (Lambda)       (Lambda)    (Lambda)
```

## Model Pricing

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Image Input |
|-------|----------------------|----------------------|-------------|
| Amazon Nova Pro | $0.80 | $3.20 | Yes |
| MiniMax M2.5 | $0.30 | $1.20 | No |
| DeepSeek V3.2 | $0.62 | $1.85 | No |
| GLM-5 (Zhipu AI) | $1.00 | $3.20 | No |

## Cost Estimation

> **All charges are pay-as-you-go. No usage = no cost. No upfront fees, no minimum spend.**

Based on real-world testing (documentation queries, pricing lookups, China region service checks, customer story searches). Estimated for **300 questions/month (~10/day)**.

**Model Invocation Cost**

> Pricing queries cost more per call due to multi-step tool usage. Numbers below are averaged across query types.

| Model | Per Query (avg) | Monthly (300 queries) |
|-------|-----------------|-----------------------|
| MiniMax M2.5 | ~$0.012 | ~$3.7 |
| DeepSeek V3.2 | ~$0.025 | ~$7.6 |
| Nova Pro | ~$0.033 | ~$9.9 |
| GLM-5 | ~$0.041 | ~$12.3 |

**AgentCore Infrastructure Cost**

Each question triggers 1 Runtime invocation and ~5 Gateway API calls on average.

| Service | Description | Monthly |
|---------|-------------|---------|
| Runtime | CPU + Memory, consumption-based | < $3 |
| Gateway | ~5 API calls per question | < $0.01 |
| Memory (optional) | Multi-turn conversation memory | < $0.5 |
| Lambda / API Gateway | | Within free tier |

**Total Monthly Cost**

| Model | Model Cost | Infrastructure | Total |
|-------|-----------|---------------|-------|
| MiniMax M2.5 | ~$3.7 | < $4 | **< $8** |
| DeepSeek V3.2 | ~$7.6 | < $4 | **< $12** |
| Nova Pro | ~$9.9 | < $4 | **< $14** |
| GLM-5 | ~$12.3 | < $4 | **< $17** |

> **All services are pay-as-you-go — no cost when idle.** Actual costs vary based on query complexity (number of tool calls, response time) and Memory settings. Only Nova Pro supports image input.

## Disclaimer

This is sample code for demonstration purposes only. You should work with your security and legal teams to meet your organizational security, regulatory, and compliance requirements before deployment. Deploying this solution may incur AWS charges.

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This project is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.

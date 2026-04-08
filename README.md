# AWS TechBot

基于 [Strands Agents SDK](https://github.com/strands-agents/sdk-python) 和 [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/) 构建的 AI AWS 技术助手。

通过 AgentCore Gateway 统一管理工具接入，Agent 启动时自动从 Gateway 发现所有可用工具。

## 适用场景

- **快速定位文档** — 在飞书群中 @机器人 即可查询 AWS 服务文档、最佳实践和架构指导，减少重复查阅文档的时间
- **配置方法与教程查询** — 查询 AWS 服务的配置步骤、操作教程和示例代码，降低上手门槛
- **成本估算** — 实时查询 AWS 全球和中国区域的服务定价，辅助架构选型和成本优化决策
- **故障排查与运维支持** — 快速检索 AWS 服务的故障排查指南、配额限制、错误码说明和运维 SOP，缩短问题定位和恢复时间

## 部署

### 前置步骤：创建飞书应用

部署前需要先在飞书开放平台创建应用，获取 App ID 和 App Secret：

1. 打开 [飞书开放平台](https://open.feishu.cn/app?lang=zh-CN)，创建企业自建应用
2. 进入 **凭证与基础信息**，复制 **App ID** 和 **App Secret**
3. 启用 **机器人** 能力
4. 配置权限
> 详细图文步骤请参考 [飞书机器人配置手册](docs/feishu-setup-zh.md)（第一步 ~ 第四步）

### 一键部署 CloudFormation

| 区域 | 部署 |
|------|------|
| 美西 (Oregon) | [![Launch Stack](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://us-west-2.console.aws.amazon.com/cloudformation/home?region=us-west-2#/stacks/quickcreate?templateURL=https://haomiaoj-yuzeli-aws-techbot-us-west-2.s3.us-west-2.amazonaws.com/template.yaml&stackName=TechBot) |

点击按钮，填写参数后部署。堆栈会创建：
- **AgentCore Gateway** — 统一 MCP 工具入口 + Cognito 认证
- **Gateway Targets** — 4 个 Lambda（Global Knowledge、China Knowledge、Pricing、Customer Stories）
- **AgentCore Runtime** — 运行 TechBot 容器
- **AgentCore Memory**（可选）— 多轮对话记忆
- **API Gateway** — `/chat` POST 端点，用于飞书 webhook
- **Handler Lambda** — 接收飞书事件，过滤 @all，异步调用 worker
- **Worker Lambda** — 调用 AgentCore，将回复更新到飞书卡片

**需要填写的参数：**

| 参数 | 是否必填 | 说明 |
|------|----------|------|
| Model ID | 已预填 | 可选 Nova Pro、GLM-5、MiniMax M2.5、DeepSeek V3.2（仅 Nova Pro 支持图片输入） |
| Enable Memory | 已预填 | `true` 开启多轮记忆，`false` 无状态 |
| Memory Expiry Days | 已预填 | 记忆过期天数（7-365） |
| Feishu App ID | **必填** | 飞书应用凭证 |
| Feishu App Secret | **必填** | 飞书应用凭证 |

其余选项（Tags、Permissions、Stack failure options 等）保持默认即可，无需修改。
页面底部勾选 **✅ I acknowledge that AWS CloudFormation might create IAM resources with custom names**
点击 **Create stack**，等待堆栈状态变为 `CREATE_COMPLETE`（约 5 分钟）。

### 部署后：完成飞书配置

堆栈部署完成后，从 Outputs 中复制 **FeishuEventSubscriptionUrl**，回到飞书完成剩余配置：

1. **配置事件订阅** — 将 URL 填入飞书开放平台 → 事件与回调 → 请求地址
2. **添加事件** — 添加 `im.message.receive_v1` 等事件
3. **发布应用** — 创建版本并提交审批
4. **添加到群聊** — 将机器人添加到飞书群

> 详细图文步骤请参考 [飞书机器人配置手册](docs/feishu-setup-zh.md)（第五步 ~ 第八步）

### 🎉🎉🎉 完成
> 详细功能说明和使用示例请参考 [使用教程](docs/usage-guide-zh.md)

## 架构

```
AgentCore Runtime (Docker 容器)
        │
        └── Agent (Bedrock 模型) → MCPClient
                                     │
                          AgentCore Gateway (MCP endpoint + Cognito 认证)
                                     │
                    ┌────────────────┼─────────────┐────────────┐
                    │                │             │            │
              Global Knowledge  China Knowledge  Pricing  Customer Stories
                (Lambda)          (Lambda)       (Lambda)    (Lambda)
```

## 模型定价

| 模型 | 输入 (per 1M tokens) | 输出 (per 1M tokens) | 图片输入 |
|------|---------------------|---------------------|---------|
| Amazon Nova Pro | $0.80 | $3.20 | ✅ |
| MiniMax M2.5 | $0.30 | $1.20 | ❌ |
| DeepSeek V3.2 | $0.62 | $1.85 | ❌ |
| GLM-5 (Zhipu AI) | $1.00 | $3.20 | ❌ |

## 成本估算

基于实际测试（文档查询、定价查询、中国区服务查询、客户案例搜索），平均每次对话约 **39K input tokens + 600 output tokens**，**4 次工具调用**。以下按 **300 问题/月（约 10 次/天）** 估算。

**模型调用费用**

| 模型 | 每次调用 | 月费用 (300 次) |
|------|---------|---------------|
| MiniMax M2.5 | ~$0.002 | ~$0.5 |
| DeepSeek V3.2 | ~$0.003 | ~$1.0 |
| Nova Pro | ~$0.005 | ~$1.5 |
| GLM-5 | ~$0.006 | ~$2.0 |

**AgentCore 基础设施费用**

每个问题调用 1 次 Runtime，平均触发 ~5 次 Gateway API 调用。

| 服务 | 说明 | 月费用 |
|------|------|--------|
| Runtime | CPU + Memory，按实际消耗计费 | < $3 |
| Gateway | 平均每问题 ~5 次 API 调用 | < $0.01 |
| Memory（可选） | 多轮对话记忆 | < $0.5 |
| Lambda / API Gateway | | 免费额度内 |

**月度总费用**

| 模型 | 模型调用 | 基础设施 | 合计 |
|------|---------|---------|------|
| MiniMax M2.5 | ~$0.5 | < $4 | **< $5** |
| DeepSeek V3.2 | ~$1.0 | < $4 | **< $5** |
| Nova Pro | ~$1.5 | < $4 | **< $6** |
| GLM-5 | ~$2.0 | < $4 | **< $6** |

> AgentCore 按实际消耗计费，无预付费用。实际费用因问题复杂度（工具调用次数、响应时间）和 Memory 开关而异。仅 Nova Pro 支持图片输入。

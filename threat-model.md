# Comprehensive Threat Model Report

**Generated**: 2026-04-09 20:08:44
**Current Phase**: 1 - Business Context Analysis
**Overall Completion**: 80.0%

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Business Context](#business-context)
3. [System Architecture](#system-architecture)
4. [Threat Actors](#threat-actors)
5. [Trust Boundaries](#trust-boundaries)
6. [Assets and Flows](#assets-and-flows)
7. [Threats](#threats)
8. [Mitigations](#mitigations)
9. [Assumptions](#assumptions)
10. [Phase Progress](#phase-progress)

## Executive Summary

AWS TechBot is an AI-powered technical assistant built on Amazon Bedrock AgentCore. It runs as a Docker container on AgentCore Runtime, connects to AgentCore Gateway (with Cognito JWT auth) to access 4 Lambda-based tool targets (AWS documentation search, China region service availability, pricing queries, customer stories). It integrates with Feishu/Lark as a chatbot via API Gateway + Lambda webhook with Verification Token validation. Feishu credentials stored in AWS Secrets Manager. Optional AgentCore Memory provides multi-turn conversation context. Deployed via one-click CloudFormation. Target users are internal AWS technical teams.

### Key Statistics

- **Total Threats**: 14
- **Total Mitigations**: 15
- **Total Assumptions**: 0
- **System Components**: 8
- **Assets**: 7
- **Threat Actors**: 10

## Business Context

**Description**: AWS TechBot is an AI-powered technical assistant built on Amazon Bedrock AgentCore. It runs as a Docker container on AgentCore Runtime, connects to AgentCore Gateway (with Cognito JWT auth) to access 4 Lambda-based tool targets (AWS documentation search, China region service availability, pricing queries, customer stories). It integrates with Feishu/Lark as a chatbot via API Gateway + Lambda webhook with Verification Token validation. Feishu credentials stored in AWS Secrets Manager. Optional AgentCore Memory provides multi-turn conversation context. Deployed via one-click CloudFormation. Target users are internal AWS technical teams.

### Business Features

- **Industry Sector**: Technology
- **Data Sensitivity**: Internal
- **User Base Size**: Small
- **Geographic Scope**: Global
- **Regulatory Requirements**: None
- **System Criticality**: Low
- **Financial Impact**: Minimal
- **Authentication Requirement**: Federated
- **Deployment Environment**: Cloud-Public
- **Integration Complexity**: Complex

## System Architecture

### Components

| ID | Name | Type | Service Provider | Description |
|---|---|---|---|---|
| C001 | AgentCore Runtime | Compute | AWS | Docker container running TechBot agent with Strands SDK, connects to Gateway via MCP |
| C002 | AgentCore Gateway | Network | AWS | MCP endpoint with Cognito JWT auth, routes tool calls to Lambda targets |
| C003 | Cognito User Pool | Security | AWS | OAuth2 client_credentials auth for Gateway access |
| C004 | Gateway Target Lambdas | Compute | AWS | 4 Lambda functions: Global Knowledge, China Knowledge, Pricing, Customer Stories |
| C005 | API Gateway | Network | AWS | REST API /chat endpoint receiving Feishu webhook events, no auth |
| C006 | Handler Lambda | Compute | AWS | Receives Feishu events, filters @all, async invokes Worker Lambda |
| C007 | Worker Lambda | Compute | AWS | Calls AgentCore Runtime, patches Feishu card with response |
| C008 | AgentCore Memory | Storage | AWS | Optional multi-turn conversation memory with semantic and summary strategies |

## Threat Actors

### Insider

- **Type**: ThreatActorType.INSIDER
- **Capability Level**: CapabilityLevel.MEDIUM
- **Motivations**: Financial, Revenge
- **Resources**: ResourceLevel.LIMITED
- **Relevant**: Yes
- **Priority**: 5/10
- **Description**: An employee or contractor with legitimate access to the system

### External Attacker

- **Type**: ThreatActorType.EXTERNAL
- **Capability Level**: CapabilityLevel.MEDIUM
- **Motivations**: Financial
- **Resources**: ResourceLevel.MODERATE
- **Relevant**: Yes
- **Priority**: 3/10
- **Description**: An external individual or group attempting to gain unauthorized access

### Nation-state Actor

- **Type**: ThreatActorType.NATION_STATE
- **Capability Level**: CapabilityLevel.HIGH
- **Motivations**: Espionage, Political
- **Resources**: ResourceLevel.EXTENSIVE
- **Relevant**: Yes
- **Priority**: 1/10
- **Description**: A government-sponsored group with advanced capabilities

### Hacktivist

- **Type**: ThreatActorType.HACKTIVIST
- **Capability Level**: CapabilityLevel.MEDIUM
- **Motivations**: Ideology, Political
- **Resources**: ResourceLevel.MODERATE
- **Relevant**: Yes
- **Priority**: 6/10
- **Description**: An individual or group motivated by ideological or political beliefs

### Organized Crime

- **Type**: ThreatActorType.ORGANIZED_CRIME
- **Capability Level**: CapabilityLevel.HIGH
- **Motivations**: Financial
- **Resources**: ResourceLevel.EXTENSIVE
- **Relevant**: Yes
- **Priority**: 2/10
- **Description**: A criminal organization with significant resources

### Competitor

- **Type**: ThreatActorType.COMPETITOR
- **Capability Level**: CapabilityLevel.MEDIUM
- **Motivations**: Financial, Espionage
- **Resources**: ResourceLevel.MODERATE
- **Relevant**: Yes
- **Priority**: 7/10
- **Description**: A business competitor seeking competitive advantage

### Script Kiddie

- **Type**: ThreatActorType.SCRIPT_KIDDIE
- **Capability Level**: CapabilityLevel.LOW
- **Motivations**: Curiosity, Reputation
- **Resources**: ResourceLevel.LIMITED
- **Relevant**: Yes
- **Priority**: 9/10
- **Description**: An inexperienced attacker using pre-made tools

### Disgruntled Employee

- **Type**: ThreatActorType.DISGRUNTLED_EMPLOYEE
- **Capability Level**: CapabilityLevel.MEDIUM
- **Motivations**: Revenge
- **Resources**: ResourceLevel.LIMITED
- **Relevant**: Yes
- **Priority**: 4/10
- **Description**: A current or former employee with a grievance

### Privileged User

- **Type**: ThreatActorType.PRIVILEGED_USER
- **Capability Level**: CapabilityLevel.HIGH
- **Motivations**: Financial, Accidental
- **Resources**: ResourceLevel.MODERATE
- **Relevant**: Yes
- **Priority**: 8/10
- **Description**: A user with elevated privileges who may abuse them or make mistakes

### Third Party

- **Type**: ThreatActorType.THIRD_PARTY
- **Capability Level**: CapabilityLevel.MEDIUM
- **Motivations**: Financial, Accidental
- **Resources**: ResourceLevel.MODERATE
- **Relevant**: Yes
- **Priority**: 10/10
- **Description**: A vendor, partner, or service provider with access to the system

## Trust Boundaries

### Trust Zones

#### Internet

- **Trust Level**: TrustLevel.UNTRUSTED
- **Description**: The public internet, considered untrusted

#### DMZ

- **Trust Level**: TrustLevel.LOW
- **Description**: Demilitarized zone for public-facing services

#### Application

- **Trust Level**: TrustLevel.MEDIUM
- **Description**: Zone containing application servers and services

#### Data

- **Trust Level**: TrustLevel.HIGH
- **Description**: Zone containing databases and data storage

#### Admin

- **Trust Level**: TrustLevel.FULL
- **Description**: Administrative zone with highest privileges

### Trust Boundaries

#### Internet Boundary

- **Type**: BoundaryType.NETWORK
- **Controls**: Web Application Firewall, DDoS Protection, TLS Encryption
- **Description**: Boundary between the internet and internal systems

#### DMZ Boundary

- **Type**: BoundaryType.NETWORK
- **Controls**: Network Firewall, Intrusion Detection System, API Gateway
- **Description**: Boundary between public-facing services and internal applications

#### Data Boundary

- **Type**: BoundaryType.NETWORK
- **Controls**: Database Firewall, Encryption, Access Control Lists
- **Description**: Boundary protecting data storage systems

#### Admin Boundary

- **Type**: BoundaryType.NETWORK
- **Controls**: Privileged Access Management, Multi-Factor Authentication, Audit Logging
- **Description**: Boundary for administrative access

## Assets and Flows

### Assets

| ID | Name | Type | Classification | Sensitivity | Criticality | Owner |
|---|---|---|---|---|---|---|
| A001 | User Credentials | AssetType.CREDENTIAL | AssetClassification.CONFIDENTIAL | 5 | 5 | N/A |
| A002 | Personal Identifiable Information | AssetType.DATA | AssetClassification.CONFIDENTIAL | 4 | 4 | N/A |
| A003 | Session Token | AssetType.TOKEN | AssetClassification.CONFIDENTIAL | 5 | 5 | N/A |
| A004 | Configuration Data | AssetType.CONFIG | AssetClassification.INTERNAL | 3 | 4 | N/A |
| A005 | Encryption Keys | AssetType.KEY | AssetClassification.RESTRICTED | 5 | 5 | N/A |
| A006 | Public Content | AssetType.DATA | AssetClassification.PUBLIC | 1 | 2 | N/A |
| A007 | Audit Logs | AssetType.DATA | AssetClassification.INTERNAL | 3 | 4 | N/A |

### Asset Flows

| ID | Asset | Source | Destination | Protocol | Encrypted | Risk Level |
|---|---|---|---|---|---|---|
| F001 | User Credentials | C001 | C002 | HTTPS | Yes | 4 |
| F002 | Session Token | C002 | C001 | HTTPS | Yes | 3 |
| F003 | Personal Identifiable Information | C003 | C004 | TLS | Yes | 3 |
| F004 | Audit Logs | C003 | C005 | TLS | Yes | 2 |

## Threats

### Identified Threats

#### T1: External attacker

**Statement**: A External attacker with internet access to API Gateway endpoint can send crafted webhook payloads to /chat endpoint which has no authentication, which leads to unauthorized invocation of AgentCore Runtime, resource abuse, cost escalation

- **Prerequisites**: with internet access to API Gateway endpoint
- **Action**: send crafted webhook payloads to /chat endpoint which has no authentication
- **Impact**: unauthorized invocation of AgentCore Runtime, resource abuse, cost escalation
- **Tags**: STRIDE-S, API

#### T2: External attacker

**Statement**: A External attacker with knowledge of the Gateway MCP endpoint URL can attempt to bypass Cognito JWT auth or use stolen/expired tokens, which leads to unauthorized access to Gateway tools, data exfiltration from AWS docs/pricing

- **Prerequisites**: with knowledge of the Gateway MCP endpoint URL
- **Action**: attempt to bypass Cognito JWT auth or use stolen/expired tokens
- **Impact**: unauthorized access to Gateway tools, data exfiltration from AWS docs/pricing
- **Tags**: STRIDE-S, Auth

#### T3: Malicious user

**Statement**: A Malicious user with access to the Feishu bot can inject prompt to make agent call unintended tools or return sensitive info, which leads to information disclosure, misuse of tools, misleading responses

- **Prerequisites**: with access to the Feishu bot
- **Action**: inject prompt to make agent call unintended tools or return sensitive info
- **Impact**: information disclosure, misuse of tools, misleading responses
- **Tags**: STRIDE-T, Prompt-Injection

#### T4: External attacker

**Statement**: A External attacker with ability to intercept network traffic can intercept Cognito client secret or JWT token in transit, which leads to credential theft, unauthorized Gateway access

- **Prerequisites**: with ability to intercept network traffic
- **Action**: intercept Cognito client secret or JWT token in transit
- **Impact**: credential theft, unauthorized Gateway access
- **Tags**: STRIDE-I, Credential

#### T5: External attacker

**Statement**: A External attacker with internet access can flood API Gateway /chat endpoint with requests causing DoS, which leads to service unavailability, excessive AWS costs from Lambda/Runtime invocations

- **Prerequisites**: with internet access
- **Action**: flood API Gateway /chat endpoint with requests causing DoS
- **Impact**: service unavailability, excessive AWS costs from Lambda/Runtime invocations
- **Tags**: STRIDE-D, DoS

#### T6: Insider or attacker

**Statement**: A Insider or attacker with access to CloudFormation parameters or Lambda env vars can extract Feishu App Secret stored in Lambda environment variables, which leads to Feishu bot impersonation, send messages as the bot

- **Prerequisites**: with access to CloudFormation parameters or Lambda env vars
- **Action**: extract Feishu App Secret stored in Lambda environment variables
- **Impact**: Feishu bot impersonation, send messages as the bot
- **Tags**: STRIDE-I, Secret

#### T7: Malicious user

**Statement**: A Malicious user with Feishu bot access and Memory enabled can poison conversation memory with misleading context for other users, which leads to future responses based on poisoned memory, misinformation

- **Prerequisites**: with Feishu bot access and Memory enabled
- **Action**: poison conversation memory with misleading context for other users
- **Impact**: future responses based on poisoned memory, misinformation
- **Tags**: STRIDE-T, Memory

#### T8: External attacker

**Statement**: A External attacker with internet access to API Gateway endpoint can send crafted webhook payloads bypassing Verification Token check, which leads to unauthorized invocation of AgentCore Runtime, resource abuse, cost escalation

- **Prerequisites**: with internet access to API Gateway endpoint
- **Action**: send crafted webhook payloads bypassing Verification Token check
- **Impact**: unauthorized invocation of AgentCore Runtime, resource abuse, cost escalation
- **Tags**: STRIDE-S, API, Mitigated-by-VerificationToken

#### T9: External attacker

**Statement**: A External attacker with knowledge of the Gateway MCP endpoint URL can attempt to bypass Cognito JWT auth or use stolen/expired tokens, which leads to unauthorized access to Gateway tools, data exfiltration from AWS docs/pricing

- **Prerequisites**: with knowledge of the Gateway MCP endpoint URL
- **Action**: attempt to bypass Cognito JWT auth or use stolen/expired tokens
- **Impact**: unauthorized access to Gateway tools, data exfiltration from AWS docs/pricing
- **Tags**: STRIDE-S, Auth

#### T10: Malicious user

**Statement**: A Malicious user with access to the Feishu bot can inject prompt to make agent call unintended tools or return sensitive info, which leads to information disclosure, misuse of tools, misleading responses

- **Prerequisites**: with access to the Feishu bot
- **Action**: inject prompt to make agent call unintended tools or return sensitive info
- **Impact**: information disclosure, misuse of tools, misleading responses
- **Tags**: STRIDE-T, Prompt-Injection

#### T11: External attacker

**Statement**: A External attacker with ability to intercept network traffic can intercept Cognito client secret or JWT token in transit, which leads to credential theft, unauthorized Gateway access

- **Prerequisites**: with ability to intercept network traffic
- **Action**: intercept Cognito client secret or JWT token in transit
- **Impact**: credential theft, unauthorized Gateway access
- **Tags**: STRIDE-I, Credential

#### T12: External attacker

**Statement**: A External attacker with internet access can flood API Gateway /chat endpoint with requests causing DoS, which leads to service unavailability, excessive AWS costs from Lambda/Runtime invocations

- **Prerequisites**: with internet access
- **Action**: flood API Gateway /chat endpoint with requests causing DoS
- **Impact**: service unavailability, excessive AWS costs from Lambda/Runtime invocations
- **Tags**: STRIDE-D, DoS

#### T13: Insider or attacker

**Statement**: A Insider or attacker with IAM access to Secrets Manager can retrieve Feishu credentials from Secrets Manager, which leads to Feishu bot impersonation, send messages as the bot

- **Prerequisites**: with IAM access to Secrets Manager
- **Action**: retrieve Feishu credentials from Secrets Manager
- **Impact**: Feishu bot impersonation, send messages as the bot
- **Tags**: STRIDE-I, Secret, Mitigated-by-SecretsManager

#### T14: Malicious user

**Statement**: A Malicious user with Feishu bot access and Memory enabled can poison conversation memory with misleading context for other users, which leads to future responses based on poisoned memory, misinformation

- **Prerequisites**: with Feishu bot access and Memory enabled
- **Action**: poison conversation memory with misleading context for other users
- **Impact**: future responses based on poisoned memory, misinformation
- **Tags**: STRIDE-T, Memory

## Mitigations

### Identified Mitigations

#### M1: Feishu webhook signature verification in Handler Lambda to validate requests originate from Feishu

**Addresses Threats**: T1

#### M2: API Gateway throttling and Lambda concurrency limits to prevent resource abuse

**Addresses Threats**: T5, T1

#### M3: Feishu App Secret should be stored in Secrets Manager instead of Lambda env vars

**Addresses Threats**: T6

#### M4: Cognito CUSTOM_JWT authorizer on AgentCore Gateway validates Bearer tokens with OIDC discovery

**Addresses Threats**: T2

#### M5: System prompt restricts agent to only answer AWS questions, rejects non-AWS queries

**Addresses Threats**: T3

#### M6: All communications use HTTPS/TLS - Gateway, Cognito, API Gateway, Feishu APIs

**Addresses Threats**: T4

#### M7: Memory sessions scoped by session_id and actor_id to limit cross-user contamination

**Addresses Threats**: T7

#### M8: Cognito token auto-refresh with 60s buffer, thread-safe caching in gateway_cognito.py

**Addresses Threats**: T2

#### M9: Handler Lambda validates Feishu Verification Token from Secrets Manager, rejects requests with invalid token (403)

**Addresses Threats**: T8

#### M10: Cognito CUSTOM_JWT authorizer on AgentCore Gateway with OIDC discovery and token auto-refresh (60s buffer)

**Addresses Threats**: T9

#### M11: System prompt restricts agent to only answer AWS questions, rejects non-AWS queries

**Addresses Threats**: T10

#### M12: All communications use HTTPS/TLS - Gateway, Cognito, API Gateway, Feishu APIs, Secrets Manager

**Addresses Threats**: T11

#### M13: API Gateway throttling and Lambda concurrency limits to prevent resource abuse and cost escalation

**Addresses Threats**: T8, T12

#### M14: Feishu credentials (App ID, App Secret, Verification Token) stored in AWS Secrets Manager with encryption at rest

**Addresses Threats**: T13

#### M15: Memory sessions scoped by session_id and actor_id to limit cross-user contamination

**Addresses Threats**: T14

## Assumptions

*No assumptions defined.*

## Phase Progress

| Phase | Name | Completion |
|---|---|---|
| 1 | Business Context Analysis | 100% ✅ |
| 2 | Architecture Analysis | 100% ✅ |
| 3 | Threat Actor Analysis | 100% ✅ |
| 4 | Trust Boundary Analysis | 100% ✅ |
| 5 | Asset Flow Analysis | 100% ✅ |
| 6 | Threat Identification | 100% ✅ |
| 7 | Mitigation Planning | 100% ✅ |
| 7.5 | Code Validation Analysis | 0% ⏳ |
| 8 | Residual Risk Analysis | 0% ⏳ |
| 9 | Output Generation and Documentation | 100% ✅ |

---

*This threat model report was generated automatically by the Threat Modeling MCP Server.*

---
name: deye-openapi-quickstart
description: Onboard developers to the DeyeCloud OpenAPI and guide them from account registration to a first successful API call. Use when a developer asks how to start integrating with DeyeCloud OpenAPI, how to obtain an access token (personal user or business member), which data center / base URL to choose, how to create a DeyeCloud application (AppId/AppSecret), or how to send and query a device control command. Also use for questions about the DeyeCloud developer portal quick-start flow, the /v1.0/account/token endpoint, /v1.0/account/info, or /v1.0/order control endpoints.
version: v261109
author: DeyeCloud Portal
---

# DeyeCloud OpenAPI Quick Start

Guide a developer from zero to a first successful DeyeCloud OpenAPI call.

## Platform Model

DeyeCloud OpenAPI exposes two operation types:

- Monitoring: fetch plant-level and device-level data (historical + real-time).
- Controlling: commit commands to control devices (e.g. set Time of Use).

## Data Center & Base URL

Choose the data center by where the devices are physically located. Data is region-isolated; a cross-region base URL will not return the right devices.

| Device location | Data center | Developer base URL |
|---|---|---|
| Europe / Africa / Asia-Pacific | EU | `https://eu1-developer.deyecloud.com` |
| North / South America | Americas | `https://us1-developer.deyecloud.com` |
| India | India | `https://india-developer.deyecloud.com` |

The prefix (`eu1` / `us1` / `india`) must match the data center chosen at account registration. All endpoints below are relative to this base URL.

When using the Deye Open MCP tools, pass the `data_center` parameter using the short key — not the full name:

| Data center name | `data_center` value |
|---|---|
| EU | `eu` |
| Americas | `am` |
| India | `india` |

To discover available data centers and their base URLs programmatically, call the MCP tool `list_data_centers` (no parameters required).

## Onboarding Flow

1. Register a DeyeCloud account in the correct data center.
2. Create a DeyeCloud Application on the developer portal → receive `AppId` and `AppSecret`. Store them securely.
3. Obtain an `accessToken` (flow differs for personal vs. business members).
4. Call endpoints with `Authorization: bearer <accessToken>`.

## Obtain Access Token — Personal User

A personal user is an account registered as an individual.

`POST /v1.0/account/token?appId={AppId}`

Body fields:
- `appSecret` — from application creation.
- One identifier: `email`, `username`, or `mobile` (+ `countryCode`).
- `password` — SHA256-encrypted and lowercase. Never send plaintext.

Key rules:
- `appId` goes on the URL query string, not in the body.
- Multiple token calls do NOT invalidate the previous token.
- Token expires after 60 days.
- Token is invalidated if the password is reset or the role changes.

Use the returned `accessToken` as `Authorization: bearer <accessToken>`. See `references/token-and-control-examples.md` for curl/Python samples.

## Obtain Access Token — Business Member

A business member belongs to a company. The flow is three steps:

1. `POST /v1.0/account/token?appId={AppId}` with credentials → returns a temporary personal access token.
2. `POST /v1.0/account/info` with `Authorization: bearer <token>` → returns `companyId`.
3. `POST /v1.0/account/token?appId={AppId}` again, now adding `companyId` to the body → returns the business member access token.

Cache `companyId` so step 2 can be skipped on token refresh. The same password rules (SHA256, lowercase) apply.
Note: the MCP convenience tool `account_token` does not support `companyId`. For business member tokens, use `call_deye_api` to call `POST /v1.0/account/token` directly with `companyId` in the body.

## Control a Device — Commit & Query

Commit a control command (example: Set Time of Use):

`POST /v1.0/order/sys/tou/update`

Body: `deviceSn`, `timeUseSettingItems[]` (`enableGeneration`, `enableGridCharge`, `power`, `soc`, `time`). The response carries an `orderId`.
TOU constraints (verified):
- Exactly 6 time intervals must be passed (fewer or more → `2101006` error).
- `time` format on write must be `HH:mm` (e.g. `"02:10"`), in 5-minute intervals.
- `config/tou` read returns `time` in `HHmm` format (e.g. `"0105"`) — convert to `HH:mm` before writing back.
- Supported device types: 3-Phase & 1-Phase Hybrid inverter; Micro Storage System (no voltage setting).

Query the command result:

`GET /v1.0/order/{orderId}`

with `Authorization: bearer <accessToken>`. Check status before sending the next command to the same device — best practice is to wait for confirmation before issuing the next command.
If a second command is sent while the previous one is still executing on the same device, the server rejects it with `2104004 command concurrent running`. Always wait for the first command to complete before issuing the next.

## Common Pitfalls

- Sending the plaintext password instead of SHA256 lowercase → auth failure.
- Putting `appId` in the body instead of the query string.
- Using the wrong data-center base URL for the account.
- For business members, forgetting `companyId` on the final token call.
- Issuing a second device command before the first completes → rejected with `2104004 command concurrent running`. (Note: if commands are spaced far enough apart, both succeed because the lock window has closed — this is not a contradiction.)
- Control commands require per-device write permission. Not all devices under a station are writable — some return `2101027` (permission denied). If a device rejects control, check with the station owner whether write access was granted for that device.

For the full endpoint reference, point developers to the API Documentation page (`/api`) on the developer portal.


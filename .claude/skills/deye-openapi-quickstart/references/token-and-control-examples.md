# DeyeCloud OpenAPI — Token & Control Examples

Load this reference when a developer needs concrete curl/Python snippets for token acquisition or device control. Replace placeholder values (`{dataCenter}`, AppId/AppSecret, credentials, device SN) with the caller's own.

## Personal User — Obtain Access Token

### curl

```bash
curl --location 'https://{dataCenter}-developer.deyecloud.com/v1.0/account/token?appId=ffffffff' \
--header 'Content-Type: application/json' \
--data-raw '{
  "appSecret": "ffffffff",
  "email": "aaa@gmail.com",
  "password": "1d8286c46e8e0d32c0987809114ad8aa41234"
}'
```

### Python (by email)

```python
import requests

url = 'https://{dataCenter}-developer.deyecloud.com/v1.0/account/token?appId=202406270000000'
headers = {'Content-Type': 'application/json'}
data = {
    "appSecret": "af958493485e56e7d58d092ea3473b64",
    "email": "aaa@gmail.com",
    "password": "1d8286c46e8e0d32cab580009114ad8aa2f778642be"  # SHA256, lowercase
}
try:
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    print(response.status_code)
    print(response.json())
except requests.exceptions.HTTPError as err:
    print(f"HTTP error occurred: {err}")
except Exception as err:
    print(f"Other error occurred: {err}")
```

### Python (by username)

```python
import requests

url = 'https://{dataCenter}-developer.deyecloud.com/v1.0/account/token?appId=202406273000000'
headers = {'Content-Type': 'application/json'}
data = {
    "appSecret": "af958493485e56e7d58d092ea3473b64",
    "username": "jbdon",
    "password": "8d969eef6ecad3c29a00000000e686cf0c3f5d0000002"  # SHA256, lowercase
}
response = requests.post(url, headers=headers, json=data)
print(response.status_code)
print(response.json())
```

### Python (by mobile)

```python
import requests

url = 'https://{dataCenter}-developer.deyecloud.com/v1.0/account/token?appId=202406273000004'
headers = {'Content-Type': 'application/json'}
data = {
    "appSecret": "af958493485e56e7d58d092ea3473b64",
    "mobile": "13100000000",
    "countryCode": 86,
    "password": "1d8286c4600000008a809114ad8aa411805778642be"  # SHA256, lowercase
}
response = requests.post(url, headers=headers, json=data)
print(response.status_code)
print(response.json())
```

### Token response shape

```json
{
    "code": "1000000",
    "msg": "success",
    "success": true,
    "accessToken": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
    "tokenType": "bearer",
    "refreshToken": "...",
    "expiresIn": "5183999",
    "scope": "all",
    "uid": 1000
}
```

## Business Member — Obtain Access Token (3-step)

### Step 1 — get personal access token

Same request as personal user (see above); the returned `accessToken` is temporary.

### Step 2 — get companyId

```bash
curl --location --request POST 'https://{dataCenter}-developer.deyecloud.com/v1.0/account/info' \
--header 'Content-Type: application/json' \
--header 'Authorization: bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...'
```

```python
import requests

url = 'https://{dataCenter}-developer.deyecloud.com/v1.0/account/info'
headers = {
    'Content-Type': 'application/json',
    'Authorization': 'bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...'
}
response = requests.post(url, headers=headers, json={})
print(response.status_code)
print(response.json())
```

### Step 3 — get business member token (add companyId)

```bash
curl --location 'https://{dataCenter}-developer.deyecloud.com/v1.0/account/token?appId=fffffff' \
--header 'Content-Type: application/json' \
--data-raw '{
  "appSecret": "ffffff",
  "email": "aaa@gmail.com",
  "companyId": 999,
  "password": "1d8286c46e8e0d32cab58abcg32f778642be"
}'
```

```python
import requests

url = 'https://{dataCenter}-developer.deyecloud.com/v1.0/account/token?appId=202406270000000'
headers = {'Content-Type': 'application/json'}
data = {
    "appSecret": "af958493485e56e7d58d092ea3473b64",
    "email": "aaa@gmail.com",
    "password": "1d8286c46e8e0d32cab580009114ad8aa33180578642be",
    "companyId": "96011"
}
response = requests.post(url, headers=headers, json=data)
print(response.status_code)
print(response.json())
```

## Device Control — Set Time of Use

`POST /v1.0/order/sys/tou/update`

```python
import requests

url = 'https://{dataCenter}-developer.deyecloud.com/v1.0/order/sys/tou/update'
headers = {
    'Authorization': 'bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...',
    'Content-Type': 'application/json'
}
data = {
    "deviceSn": "221299",
    "timeUseSettingItems": [
        {"enableGeneration": True,  "enableGridCharge": True,  "power": 1000, "soc": 20, "time": "02:10"},
        {"enableGeneration": True,  "enableGridCharge": False, "power": 2000, "soc": 20, "time": "03:15"},
        {"enableGeneration": False, "enableGridCharge": True,  "power": 3000, "soc": 40, "time": "04:20"},
        {"enableGeneration": True,  "enableGridCharge": True,  "power": 4000, "soc": 50, "time": "05:25"},
        {"enableGeneration": False, "enableGridCharge": True,  "power": 333,  "soc": 60, "time": "14:00"},
        {"enableGeneration": True,  "enableGridCharge": False, "power": 100,  "soc": 70, "time": "15:10"}
    ]
}
# NOTE: Exactly 6 time intervals are required (fewer/more → 2101006 error).
# time format on write: "HH:mm" in 5-minute intervals (e.g. "02:10").
# config/tou read returns time in "HHmm" format (e.g. "0105") — convert before writing back.
response = requests.post(url, headers=headers, json=data)
print(response.status_code)
print(response.json())  # contains orderId
```

## Device Control — Query Command Result

`GET /v1.0/order/{orderId}`

```python
import requests

orderId = "6811105"  # orderId from the Set Time of Use response
url = f'https://{dataCenter}-developer.deyecloud.com/v1.0/order/{orderId}'
headers = {
    'Authorization': 'bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...',
    'Content-Type': 'application/json;charset=UTF-8'
}
response = requests.get(url, headers=headers)
print(response.status_code)
print(response.json())
```

Verify command status (success / failed / in-progress) here before sending the next command to the same device.

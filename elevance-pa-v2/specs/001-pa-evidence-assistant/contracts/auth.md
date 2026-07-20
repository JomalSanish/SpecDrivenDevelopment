# API Contracts: Auth

**Base path**: `/api/v1/auth`
**Auth required**: None on token endpoints. All other endpoints require Bearer JWT.

---

## POST /api/v1/auth/token

OAuth2 password grant. Returns access + refresh tokens.

**Request** (`application/x-www-form-urlencoded`):
```
username=intake1&password=secret&grant_type=password
```

**Response 200**:
```json
{
  "access_token": "<JWT>",
  "token_type": "bearer",
  "expires_in": 900,
  "refresh_token": "<opaque UUID>"
}
```

**Response 401** (invalid credentials or deactivated account):
```json
{ "detail": "Invalid credentials" }
```

---

## POST /api/v1/auth/refresh

Exchange a valid refresh token for a new access token + rotated refresh token.

**Request** (`application/json`):
```json
{ "refresh_token": "<opaque UUID>" }
```

**Response 200**:
```json
{
  "access_token": "<JWT>",
  "token_type": "bearer",
  "expires_in": 900,
  "refresh_token": "<new opaque UUID>"
}
```

**Response 401**: `{ "detail": "Refresh token invalid or expired" }`

---

## POST /api/v1/auth/logout

Revokes the provided refresh token server-side. Access token expires naturally.

**Auth**: Bearer JWT (any role)

**Request** (`application/json`):
```json
{ "refresh_token": "<opaque UUID>" }
```

**Response 204**: No content.

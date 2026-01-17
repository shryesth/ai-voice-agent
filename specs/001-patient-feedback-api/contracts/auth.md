# API Contract: Authentication

**Base Path**: `/api/v1/auth`
**Purpose**: User authentication and token management

---

## POST `/api/v1/auth/login`

**Description**: Authenticate user and receive access token

**Authentication**: None (public endpoint)

**Request Body**:
```json
{
  "email": "admin@example.com",
  "password": "secure_password_123"
}
```

**Request Schema**:
```python
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
```

**Success Response** (200 OK):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "email": "admin@example.com",
    "role": "admin",
    "is_active": true
  }
}
```

**Response Schema**:
```python
class UserResponse(BaseModel):
    email: EmailStr
    role: UserRole
    is_active: bool

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: UserResponse
```

**Error Responses**:

- **401 Unauthorized** - Invalid credentials
```json
{
  "detail": "Incorrect email or password"
}
```

- **422 Unprocessable Entity** - Validation error
```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email address",
      "type": "value_error.email"
    }
  ]
}
```

---

## GET `/api/v1/auth/me`

**Description**: Get current authenticated user info

**Authentication**: Bearer token required

**Headers**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Success Response** (200 OK):
```json
{
  "email": "admin@example.com",
  "role": "admin",
  "is_active": true,
  "created_at": "2026-01-18T10:30:00Z",
  "last_login": "2026-01-18T14:45:00Z"
}
```

**Response Schema**:
```python
class CurrentUserResponse(UserResponse):
    created_at: datetime
    last_login: Optional[datetime]
```

**Error Responses**:

- **401 Unauthorized** - Missing or invalid token
```json
{
  "detail": "Could not validate credentials"
}
```

---

## POST `/api/v1/auth/logout`

**Description**: Invalidate current access token

**Authentication**: Bearer token required

**Success Response** (200 OK):
```json
{
  "message": "Successfully logged out"
}
```

**Response Schema**:
```python
class MessageResponse(BaseModel):
    message: str
```

**Note**: For MVP, tokens are stateless JWT. Logout is client-side only (discard token). Future: token blacklist in Redis.

---

## Security Notes

### Token Format
- JWT with HS256 algorithm
- Payload includes: `user_id`, `email`, `role`, `exp` (expiration)
- Expires in 24 hours (86400 seconds)

### Password Requirements
- Minimum 8 characters
- Hashed with bcrypt (cost factor: 12)
- Never stored or returned in plaintext

### Rate Limiting (Future)
- Login endpoint: 5 attempts per 15 minutes per IP
- Lockout after 5 failed attempts: 1 hour

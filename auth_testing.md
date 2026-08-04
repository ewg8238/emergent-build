# Auth Testing
- Login: POST /api/auth/login {email, password}. Returns user + token, sets access_token cookie.
- Admin/owner: ewg8238@gmail.com / Compliance2026!
- Protected routes use cookie OR Authorization: Bearer <token>.
- /api/auth/me returns current contractor.

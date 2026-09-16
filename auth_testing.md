# Auth-Gated App Testing Playbook (Emergent Google Auth)

## Step 1: Create Test User & Session (mongosh)
```
mongosh --eval "
use('vampires_choice');
var userId = 'user_' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({ user_id: userId, email: 'test.user.'+Date.now()+'@example.com', name: 'Test User', picture: 'https://via.placeholder.com/150', created_at: new Date() });
db.user_sessions.insertOne({ user_id: userId, session_token: sessionToken, expires_at: new Date(Date.now()+7*24*60*60*1000), created_at: new Date() });
print('Session token: ' + sessionToken);
print('User ID: ' + userId);
"
```

## Step 2: Backend API (same-origin /api)
```
curl -s -X GET "$ORIGIN/api/auth/me" -H "Authorization: Bearer $TOKEN"
curl -s -X GET "$ORIGIN/api/me/save" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "$ORIGIN/api/me/claim" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"playerId":"vc_<id>"}'
```

## Step 3: Browser Testing (inject session cookie)
```
await page.context.add_cookies([{ "name":"session_token","value":"$TOKEN","domain":"<host>","path":"/","httpOnly":true,"secure":true,"sameSite":"None" }])
```
Bearer token via Authorization header also works for API calls.

## Checklist
- users doc has custom user_id (Mongo _id never exposed)
- user_sessions.user_id matches users.user_id
- all queries use {"_id":0}
- /api/auth/me returns user for valid token, 401 for invalid/expired
- /api/me/save requires authenticated owner; anon id alone cannot access it
- claim is idempotent and cannot hijack an already-claimed save

## Clean test data
```
mongosh --eval "use('vampires_choice'); db.users.deleteMany({email:/test\.user\./}); db.user_sessions.deleteMany({session_token:/test_session/});"
```

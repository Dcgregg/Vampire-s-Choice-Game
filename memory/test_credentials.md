# Test Credentials — Vampire's Choice

## Authentication: Emergent-managed Google sign-in (Phase 5)
Google OAuth does NOT use app-managed passwords, so there are no username/password
credentials to store. For automated testing, seed a session directly in MongoDB
(db: `vampires_choice`) per `/app/auth_testing.md`:

```
mongosh --eval "use('vampires_choice');
var uid='user_'+Date.now(); var tok='test_session_'+Date.now();
db.users.insertOne({user_id:uid,email:'test.user.'+Date.now()+'@example.com',name:'Test User',picture:null,created_at:new Date()});
db.user_sessions.insertOne({user_id:uid,session_token:tok,expires_at:new Date(Date.now()+7*24*60*60*1000),created_at:new Date()});
print('TOKEN='+tok);"
```
Use the token as `Authorization: Bearer <TOKEN>` for API calls, or inject a cookie
`session_token=<TOKEN>` (httpOnly, secure, sameSite=None) for browser tests.

- Real Google accounts: any Google account can sign in (no allowlist configured).
- Anonymous play requires NO credentials (localStorage `vc_player_id`).

## Cleanup
```
mongosh --eval "use('vampires_choice'); db.users.deleteMany({email:/test\.user\./}); db.user_sessions.deleteMany({session_token:/test_session/});"
```

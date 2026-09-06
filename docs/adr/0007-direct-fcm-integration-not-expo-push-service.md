# Direct Firebase Admin SDK integration for push, not Expo Push Service

`rooted-app` (the v1 client) is Expo React Native. Expo offers a hosted Expo Push Service that proxies delivery through FCM (Android) and APNs (iOS) and issues its own Expo-format push tokens — this is the path `rooted-docs` ADR-001 ("client-react-native") implies by naming "Expo Notifications" as the push mechanism.

We decided instead to have `rooted-core-api` integrate directly with Firebase Cloud Messaging via the `firebase-admin` Python SDK, targeting native device tokens (FCM registration tokens on Android; APNs tokens registered into the Firebase project for iOS) rather than routing sends through Expo's hosted service. A Firebase project and service account already exist for this purpose.

**Why:** direct control over the Firebase project (message targeting, delivery diagnostics, future use of other Firebase messaging features) without a dependency on Expo's push infrastructure or its token format.

**Consequences:** `rooted-app` cannot obtain native tokens via the plain Expo-managed workflow — it must adopt a config plugin and `expo prebuild` to generate native `ios/`/`android/` projects (tracked as separate client-side tickets). The backend owns and stores real FCM/APNs tokens directly on `Device` rows (see `CONTEXT.md`), not Expo push tokens.

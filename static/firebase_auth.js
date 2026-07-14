import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-app.js";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
} from "https://www.gstatic.com/firebasejs/10.12.5/firebase-auth.js";

let firebaseAuth = null;

function getFirebaseAuth() {
  const config = window.firebaseAuthConfig || {};
  if (!config.apiKey || !config.authDomain || !config.projectId || !config.appId) {
    throw new Error("Firebase is not configured. Add FIREBASE_API_KEY, FIREBASE_AUTH_DOMAIN, FIREBASE_PROJECT_ID and FIREBASE_APP_ID.");
  }
  if (!firebaseAuth) {
    firebaseAuth = getAuth(initializeApp(config));
  }
  return firebaseAuth;
}

window.signInWithGoogle = async function signInWithGoogle(role = "user") {
  try {
    const provider = new GoogleAuthProvider();
    provider.setCustomParameters({ prompt: "select_account" });
    const result = await signInWithPopup(getFirebaseAuth(), provider);
    const idToken = await result.user.getIdToken();
    const response = await fetch(window.firebaseGoogleAuthUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idToken, role }),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || "Google sign-in failed.");
    }
    window.location.href = data.redirect || "/";
  } catch (error) {
    alert(error.message || "Google sign-in failed.");
  }
};

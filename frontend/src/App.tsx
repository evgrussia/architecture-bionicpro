import React from 'react';
import { ReactKeycloakProvider } from '@react-keycloak/web';
import Keycloak, { KeycloakConfig, KeycloakInitOptions } from 'keycloak-js';
import ReportPage from './components/ReportPage';

const keycloakConfig: KeycloakConfig = {
  url: process.env.REACT_APP_KEYCLOAK_URL,
  realm: process.env.REACT_APP_KEYCLOAK_REALM||"",
  clientId: process.env.REACT_APP_KEYCLOAK_CLIENT_ID||""
};

const keycloak = new Keycloak(keycloakConfig);

// Authorization Code Flow + PKCE (RFC 7636, S256).
// keycloak-js сам генерирует code_verifier/code_challenge и хранит verifier в sessionStorage.
const initOptions: KeycloakInitOptions = {
  onLoad: 'check-sso',
  pkceMethod: 'S256',
  checkLoginIframe: false,
  silentCheckSsoRedirectUri: window.location.origin + '/silent-check-sso.html'
};

const App: React.FC = () => {
  return (
    <ReactKeycloakProvider authClient={keycloak} initOptions={initOptions}>
      <div className="App">
        <ReportPage />
      </div>
    </ReactKeycloakProvider>
  );
};

export default App;
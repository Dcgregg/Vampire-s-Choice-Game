import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import {AuthProvider} from './auth/AuthContext';
import './index.css';

const params = new URLSearchParams(window.location.search);
const isolatedPreview = ['betaBook', 'stagedBook'].some((key) => /^book[1-9][0-9]*$/.test(params.get(key) ?? ''));

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isolatedPreview ? <App /> : <AuthProvider><App /></AuthProvider>}
  </StrictMode>,
);

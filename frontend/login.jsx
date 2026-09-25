import React, { useState } from 'react';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';

export function LoginView({ model }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [visiblePassword, setVisiblePassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const submit = async event => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    try { await model.login({ username, password }); }
    catch (failure) { setError(failure.message || 'No se pudo iniciar sesión'); }
    finally { setBusy(false); }
  };
  return <main className="login-screen" aria-labelledby="login-title"><section className="login-shell"><h1 id="login-title">Ingresar a Libro de Trabajo</h1><p>Acceso exclusivo para el equipo de Porto Servicios.</p><form className="login-primary-form tw-grid tw-gap-3" onSubmit={submit}><label className="tw-grid tw-gap-1">Correo corporativo o usuario<InputText value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" required autoFocus /></label><label className="tw-grid tw-gap-1">Contraseña<span className="password-control"><InputText value={password} onChange={event => setPassword(event.target.value)} type={visiblePassword ? 'text' : 'password'} autoComplete="current-password" required /><Button type="button" text icon={visiblePassword ? 'pi pi-eye-slash' : 'pi pi-eye'} aria-label={visiblePassword ? 'Ocultar contraseña' : 'Mostrar contraseña'} onClick={() => setVisiblePassword(value => !value)} /></span></label>{error && <p className="login-error" role="alert">{error}</p>}<Button type="submit" label="Ingresar" loading={busy} disabled={busy} /></form></section></main>;
}

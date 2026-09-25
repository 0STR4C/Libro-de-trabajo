import React, { useState } from 'react';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
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
  return <main className="login-screen" aria-labelledby="login-title"><section className="login-shell"><h1 id="login-title">Ingresar a Libro de Trabajo</h1><p>Acceso exclusivo para el equipo de Porto Servicios.</p><form className="login-primary-form tw-flex tw-w-full tw-flex-col tw-gap-4 tw-text-[13px]" onSubmit={submit}><label className="tw-flex tw-w-full tw-flex-col tw-gap-1"><span>Usuario o correo electrónico</span><InputText className="tw-h-9 tw-w-full" value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" required autoFocus /></label><label className="tw-flex tw-w-full tw-flex-col tw-gap-1"><span>Contraseña</span><span className="password-control tw-w-full"><InputText className="tw-h-9 tw-w-full" value={password} onChange={event => setPassword(event.target.value)} type={visiblePassword ? 'text' : 'password'} autoComplete="current-password" required /><Button className="tw-h-9 tw-h-9" type="button" text icon={visiblePassword ? 'pi pi-eye-slash' : 'pi pi-eye'} aria-label={visiblePassword ? 'Ocultar contraseña' : 'Mostrar contraseña'} onClick={() => setVisiblePassword(value => !value)} /></span></label>{error && <p className="login-error" role="alert">{error}</p>}<Button className="tw-h-9 tw-w-full tw-h-9" type="submit" label="Ingresar" loading={busy} disabled={busy} /></form></section></main>;
}

export function LogoutDialog({ model }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const confirm = async () => {
    if (busy) return;
    setBusy(true);
    setError('');
    try { await model.confirm(); }
    catch (failure) { setError(failure.message || 'No se pudo cerrar la sesión'); setBusy(false); }
  };
  return <Dialog header="Cerrar sesión" visible modal onHide={model.cancel} closable={!busy} closeOnEscape={!busy} style={{ width: 'min(400px, 94vw)' }} appendTo={document.body}><p>¿Querés salir de Libro de Trabajo?</p>{error && <p role="alert" className="login-error">{error}</p>}<div className="tw-flex tw-justify-end tw-gap-2"><Button className="tw-h-9" label="Cancelar" text disabled={busy} onClick={model.cancel} /><Button className="tw-h-9" label="Salir" severity="danger" loading={busy} onClick={confirm} /></div></Dialog>;
}

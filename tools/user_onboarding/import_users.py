"""Alta aditiva de Telefonistas. JSON por stdin; no recibe ni revela secretos."""
import argparse
import json
import re
import secrets
import sys


def validate_roster(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 500:
        raise ValueError('Se requiere una lista de 1 a 500 personas')
    result, seen = [], set()
    for row in value:
        if not isinstance(row, dict):raise ValueError('Registro inválido')
        name=str(row.get('name','')).strip()
        email=str(row.get('email','')).strip().lower()
        if not 2 <= len(name) <= 150 or not re.fullmatch(r'[a-z0-9][a-z0-9._-]*@portoservicios\.com\.uy',email):
            raise ValueError('Nombre o correo corporativo inválido')
        if email in seen:raise ValueError('El listado contiene correos duplicados')
        seen.add(email);result.append(dict(name=name,email=email,username=email.split('@')[0]))
    return result


def provision(db, roster, apply=False):
    from app.security import hash_password
    # No llama initialize(): únicamente inserta en las tablas ya existentes.
    from app.postgres_server import audit
    db.execute('LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE')
    role=db.execute("SELECT id FROM roles WHERE name='Telefonista'").fetchone()
    if not role:raise ValueError('No existe el rol Telefonista')
    pending=[];existing=0
    for row in roster:
        found=db.execute('SELECT id FROM users WHERE lower(email)=%s OR lower(username)=%s', (row['email'],row['username'])).fetchall()
        if found:existing+=1
        else:pending.append(row)
    if not apply:return dict(requested=len(roster),existing_preserved=existing,would_create=len(pending),created=0)
    password=secrets.token_urlsafe(32)
    for row in pending:
        record=db.execute('INSERT INTO users(username,email,display_name,password_hash,role_id,active) VALUES(%s,%s,%s,%s,%s,TRUE) RETURNING id',
                          (row['username'],row['email'],row['name'],hash_password(password),role['id'])).fetchone()
        audit(db,'user',record['id'],'CREADO','Alta de equipo autorizada por Administrador',row['email'])
    password=None
    return dict(requested=len(roster),existing_preserved=existing,created=len(pending),role='Telefonista',temporary_password='generated_not_disclosed')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Confirma INSERT; sin esta opción solo comprueba')
    args=parser.parse_args()
    try:
        roster=validate_roster(json.load(sys.stdin))
        from app.postgres_server import connect
        with connect() as db:result=provision(db,roster,args.apply)
        print(json.dumps(result))
    except Exception:
        # Evita reproducir parámetros SQL, información personal o conexión.
        print('Alta no completada; transacción revertida. Revisar formato, rol y disponibilidad de la base.',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())

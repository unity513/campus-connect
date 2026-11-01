# Campus Connect — e-commerce platform

**Simple products. Thoughtfully chosen.**

Campus Connect is the customer-facing storefront brand. The platform is built and
operated on technology **Powered by LAVIDA**. This is a real, database-backed
Django application — not a mockup — with a working customer storefront and a
complete administrative back office.

---

## What's included

| Area | Status |
|------|--------|
| Customer storefront (home, shop, search, filter, sort, product pages) | ✅ DB-driven |
| Shopping cart with server-side stock validation | ✅ |
| Customer accounts, dashboard, order history, order tracking | ✅ |
| Order system (`CC-000001` numbering, full status lifecycle, history) | ✅ |
| Payment-proof workflow (configurable methods, private uploads, verify/reject) | ✅ |
| Admin dashboard + branded back office | ✅ |
| Product management (CRUD, publish/unpublish/archive, compliance gating) | ✅ |
| Inventory management (adjust/correct, movement history, no negative stock) | ✅ |
| Role-based access control (5 roles, enforced server-side) | ✅ |
| Regulated-product controls + licensed-merchant workflow | ✅ |
| Pickup / delivery fulfilment (configurable) | ✅ |
| Notifications (templated, pluggable provider) | ✅ |
| Admin settings, audit log, analytics events | ✅ |
| SEO (titles, meta, OG, sitemap, robots, favicon) | ✅ |
| Responsive, mobile-first UI | ✅ |
| Security (CSRF, server-side authz, private media, rate limiting, hardening) | ✅ |
| Automated acceptance tests | ✅ `python manage.py test` |

---

## Tech stack

- **Django 6.1** (Python 3.12)
- Relational DB: **SQLite** by default, **PostgreSQL / Supabase** via env vars
- Server-rendered templates + Tailwind (CDN) + Lucide icons
- No build step required to run

### Apps

- `accounts` — custom user, customer profiles, addresses, RBAC roles
- `catalog` — categories, products, images, inventory movements, compliance
- `orders` — cart, orders, items, payments, payment proofs, status events
- `store` — settings, payment/fulfilment methods, merchant profile,
  notifications, audit log, analytics
- `storefront` — customer-facing views, SEO, error handlers
- `backoffice` — branded operations dashboard (complements Django admin)

---

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Apply migrations
python manage.py migrate

# 3. First-run setup: roles, settings, payment methods, notification
#    templates, and the first Super Admin. Credentials come from the
#    environment — never hard-coded.
export SAVANA_ADMIN_USER=admin
export SAVANA_ADMIN_EMAIL=you@example.com
export SAVANA_ADMIN_PASSWORD='choose-a-strong-password'
python manage.py savana_setup            # add --demo to seed a sample catalogue

# 4. Run
python manage.py runserver
```

- Storefront: `http://127.0.0.1:8000/`
- Branded back office: `http://127.0.0.1:8000/backoffice/`
- Django admin (product/settings management): `http://127.0.0.1:8000/admin/`

> The `--demo` flag seeds four sample products. Omit it for a clean store and
> add real products from `/admin/`.

---

## Configuration

All runtime configuration is read from environment variables — see
`.env.example`. Nothing operational (account numbers, payment instructions,
pickup locations, delivery fees, store info) is hard-coded in templates; it all
lives in the database and is editable from the admin.

### PostgreSQL / Supabase

The app resolves its database in this order: `SAVANA_DATABASE_URL` (or the
conventional `DATABASE_URL`) → `SAVANA_POSTGRES_*` → SQLite.

**Supabase (hosted Postgres).** In the Supabase dashboard open
*Project Settings → Database → Connection string*, choose **URI**, and copy it.
For most deployments use the connection **pooler** host (port `6543`); the
direct host uses port `5432`. Set it as a single variable:

```bash
export SAVANA_DATABASE_URL='postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres'
```

SSL is required by Supabase and is enabled automatically (`sslmode=require`);
override with `SAVANA_DB_SSLMODE` if your setup needs a different mode. The
`psycopg[binary]` driver in `requirements.txt` is used for the connection. Then
run the usual migrate + setup against Supabase:

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py savana_setup --demo
```

**Self-hosted Postgres.** Alternatively set `SAVANA_POSTGRES_DB` (and the
related `SAVANA_POSTGRES_*` vars) to switch from SQLite to PostgreSQL.

### Production checklist

- `SAVANA_DEBUG=0`
- Set a strong `SAVANA_SECRET_KEY`
- Set `SAVANA_ALLOWED_HOSTS` and `SAVANA_CSRF_TRUSTED_ORIGINS`
- Serve behind HTTPS (`SAVANA_SSL_REDIRECT=1`)
- `python manage.py collectstatic`
- Use gunicorn (see `Procfile` / `Dockerfile`)

---

## Security notes

- Authentication via Django's auth system; passwords validated and hashed.
- Authorization enforced **server-side** (view checks + permission system);
  the UI only hides what the server already forbids.
- Payment proofs are stored in **private** media (`private_media/`) under
  unguessable filenames and served only through an authorization-checked view
  — never a predictable public URL.
- CSRF protection on all forms; cookies hardened outside DEBUG.
- Simple per-IP rate limiting on login, registration and proof-upload.
- Important administrative actions are written to the audit log.
- An order is **never** auto-marked paid because a customer uploaded a
  screenshot — a Payment Verifier (or Super Admin) must confirm it.

---

## Roles (RBAC)

| Role | Scope |
|------|-------|
| Super Admin | Full access |
| Store Admin | Products, inventory, orders, customers |
| Payment Verifier | Payment verification + payment-related order info |
| Fulfilment Staff | Fulfilment / order-processing only |
| Content Manager | Products & storefront content, no financial admin |

---

## Testing

```bash
python manage.py test
```

The suite covers the full customer journey, admin journey, product publish
lifecycle, inventory flips, payment verify/reject, regulated-product gating,
RBAC enforcement, private-proof access control, and SEO endpoints.

---

## Modularity

The merchant, payment methods, fulfilment methods, categories and settings are
all data-driven, so additional stores / product lines can be added without
touching application code. Campus Connect remains the storefront brand; the licensed
merchant is modelled separately so Campus Connect never pretends to be the licensed
entity for regulated transactions.

*Powered by LAVIDA.*

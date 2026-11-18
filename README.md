# FindIt backend (Django + DRF)

## Ishga tushirish

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py makemigrations accounts listings
python manage.py migrate
python manage.py seed             # kategoriyalar, joylar, demo foydalanuvchilar
python manage.py runserver
```

Admin panel: http://localhost:8000/admin/ (admin@findit.uz yoki moderator@findit.uz, parol: `findit12345`).
Demo foydalanuvchilar faqat sinov uchun; ishga tushirishdan oldin o'chiring.

Standart baza SQLite. PostgreSQL uchun `.env.example` dagi `POSTGRES_*` o'zgaruvchilarini bering.

## API

| Metod | Manzil | Tavsif |
|---|---|---|
| POST | `/api/auth/register/` | Ro'yxatdan o'tish (email, full_name, phone, password) |
| POST | `/api/auth/login/` | Kirish (email, password) -> access, refresh |
| POST | `/api/auth/refresh/` | Tokenni yangilash |
| GET/PATCH | `/api/auth/me/` | Joriy foydalanuvchi |
| GET | `/api/categories/`, `/api/locations/` | Ro'yxatlar |
| GET | `/api/listings/` | Faol e'lonlar. Filtr: `type, category, location, color, q, date_from, date_to` |
| POST | `/api/listings/` | E'lon yaratish (multipart, `image` bilan). Holati PENDING bo'ladi |
| GET | `/api/listings/{id}/` | Tafsilot |
| DELETE | `/api/listings/{id}/` | O'z e'lonini o'chirish |
| GET | `/api/listings/mine/` | Mening e'lonlarim |
| GET | `/api/listings/{id}/matches/` | E'longa mos kelganlar (faqat egasi) |
| POST | `/api/matches/{id}/dismiss/` | Mosni rad etish |
| POST | `/api/claims/` | Egalik da'vosi (listing, match?, proof_text) |
| GET | `/api/claims/` | Mening da'volarim |

Autentifikatsiya: `Authorization: Bearer <access>`.

## Jarayon

1. User e'lon yaratadi -> `PENDING`.
2. Moderator `/admin/` da e'lonni tasdiqlaydi -> `ACTIVE`, matching avtomatik ishlaydi.
3. Foydalanuvchi `/matches/` da mos e'lonlarni ko'radi va FOUND e'longa da'vo yuboradi -> e'lon `IN_CLAIM`.
4. Moderator da'voni admin panelda ko'radi (da'vo matni va topuvchining yashirin belgisi yonma-yon):
   - tasdiqlasa: FOUND (va mos LOST) e'lon `CLOSED`;
   - rad etsa: FOUND e'lon yana `ACTIVE`.

`secret_detail`, `storage_place` va `reject_reason` API'da faqat e'lon egasi va moderatorga qaytadi.

## Matching ballari (0-100)

Kategoriya 30, rang 15, joy 20, sana (0-3 kun 15, 4-7 kun 8), nom o'xshashligi 20.
Chegara: `FINDIT_MATCH_MIN_SCORE` (standart 50).

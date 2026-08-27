# Rencana Implementasi: LeadMaps BI — Business Lead Scraper Dashboard
### Studi Kasus: Cari Prospek Jasa Pembuatan Website via Google Places API per Lokasi & Kategori Usaha
### FastAPI + MySQL + Tailwind CSS (Pure, Tanpa Vite/NPM Run Dev)

> Dokumen ini adalah blueprint teknis lengkap dan **self-contained** — tujuannya adalah peta jalan yang bisa langsung dieksekusi step-by-step untuk membangun dashboard internal pencarian leads usaha lokal (via Google Places API resmi), lengkap dengan sistem tracking status follow-up sales, tanpa build step Node.js/NPM di server produksi.

---

## 1. Ringkasan Proyek

| Item | Detail |
|---|---|
| Tipe website | Internal tool — dashboard business intelligence & lead generation |
| Sumber data | Google Places API (New) — resmi, bukan scraping DOM |
| Gaya UI | Dashboard business-intelligence internal — sidebar gelap + kartu metrik gaya market-intelligence report |
| Backend | Python 3.11+ / FastAPI |
| Database | MySQL 8 |
| CSS | Tailwind CSS **standalone CLI** (binary, tanpa Node/NPM, tanpa Vite, tanpa `npm run dev`) |
| JS | htmx (via CDN) untuk interaktivitas tanpa reload; Leaflet.js (via CDN) untuk peta; tanpa build step apapun |
| Templating | Jinja2 (native di FastAPI, tanpa dependency tambahan) |
| Auth internal (opsional) | Session-based sederhana (starlette `SessionMiddleware`), tanpa framework auth pihak ketiga |
| Upload/Export | Export CSV/Excel via `pandas` + `openpyxl` |
| Target hosting | VPS/cloud kecil (butuh runtime Python — bukan shared hosting PHP), bisa juga via Docker |

**Prinsip utama "tanpa Vite/NPM":** semua styling memakai **Tailwind CSS Standalone CLI** — binary yang di-download sekali, dipakai untuk compile `resources/css/app.css` menjadi `static/css/app.css` statis. Tidak ada `package.json`, `node_modules`, dev server, atau hot-reload yang wajib ada di server produksi. htmx dan Leaflet cukup di-include lewat tag `<script>`/`<link>` dari CDN — tidak perlu bundler sama sekali.

---

## 2. Ringkasan Kebutuhan & Breakdown Fitur per Halaman

> Bagian ini adalah acuan teknis lengkap yang dipakai langsung saat membangun tiap halaman — tidak perlu dokumen tambahan lain.

**A. Dashboard Ringkasan (`/`)**
1. Card "Mulai Crawling Leads Baru": form input kata kunci kategori usaha + dropdown Provinsi + dropdown Kota/Kabupaten + tombol "Mulai Crawl" (`hx-post` ke `/crawl`, tanpa reload)
2. Card "Filter Data Agregasi": pill filter wilayah aktif + dropdown Waktu/Provinsi/Kota/Kategori + tombol "Terapkan" (`hx-get`)
3. Section header "Agregasi N Sesi Crawling" + total leads unik di kanan
4. 4 kartu metrik: Total Usaha Terdata, Belum Punya Website (+persentase), Rata-rata Rating Pasar, Leads Sudah Dihubungi
5. 2 kartu chart: Sebaran Kategori Usaha (bar chart), Status Website vs Rating (bar/scatter)

**B. Peta & Analisis Leads (`/leads`)**
1. Card filter (kategori, punya/tidak punya website, rating minimum, status kontak)
2. Peta interaktif (Leaflet) dengan pin berwarna beda untuk status "belum website" vs "sudah website"
3. Tabel leads: Nama Usaha, Kategori, Alamat, Telepon, Website, Rating, Status Kontak, Aksi (WA / Lihat Maps / Ubah Status) — baris tanpa website di-highlight hijau
4. Sort & filter kolom via `hx-get`, update partial tanpa reload

**C. Detail Leads (`/leads/{business_id}`)**
1. Info lengkap usaha (semua field dari Places API)
2. Riwayat status & catatan follow-up
3. Form ubah status kontak (dropdown funnel) + textarea notes, submit via `hx-post`
4. Tombol WhatsApp dengan pesan template pre-filled (ambil dari `business_profile.default_wa_template`)

**D. Riwayat Crawling (`/history`)**
1. Tabel log semua sesi fetch: tanggal, lokasi, kategori, jumlah hasil, status, **jumlah API request terpakai** (kontrol biaya)
2. Perbandingan leads baru vs leads lama per wilayah (agar tidak fetch ulang lokasi yang sama terlalu sering)

**E. Metodologi & Panduan (`/guide`)**
- Halaman statis: penjelasan cara kerja lead scoring (`priority` high/medium/low), cara pakai filter, dan etika outreach (opt-out)

**F. Profil Bisnis Saya (`/settings/profile`)**
- Form: nama jasa, kontak person, nomor telepon, template pesan WA default (dengan placeholder `{business_name}`)

---

## 3. Analisis Visual / UI (Design Cues)

Gaya visual dashboard yang harus diikuti konsisten di semua halaman:

- **Palet warna:** sidebar gelap nyaris hitam (`#0B0F19`), konten utama abu sangat muda (`#F5F6F8`), card putih dengan border tipis (`#E5E7EB`), aksen biru muda (`#DBEAFE` bg / `#1D4ED8` teks) untuk pill filter aktif, hijau muda (`#ECFDF5`) untuk highlight leads prioritas.
- **Tipografi:** font Inter/sans-serif sistem. Judul halaman bold 20–22px, label kecil uppercase letter-spacing lebar untuk label field (11px), angka metrik besar-bold (28–32px), body/tabel 13–14px.
- **Card:** flat, radius 8px, padding 20–24px, shadow sangat tipis (`0 1px 2px rgba(0,0,0,0.04)`), bukan shadow tebal — kesan minimal, bukan dekoratif.
- **Sidebar:** fixed width 240px, background `#0B0F19`. Header brand (logo + nama produk + subtitle kecil abu). 2 grup navigasi dengan label section uppercase kecil: **"NAVIGASI UTAMA"** (Dashboard Ringkasan, Peta & Analisis Leads, Riwayat Crawling, Metodologi & Panduan) dan **"KONFIGURASI"** (Profil Bisnis Saya, dst). Item nav aktif berlatar `#1E293B` dengan teks putih; item non-aktif teks abu `#CBD5E1`. Footer sidebar: copyright kecil + titik status hijau (`#22C55E`) menandakan sistem online.
- **Tombol primer:** solid gelap (`#0F172A`) teks putih, radius 8px, dipakai konsisten di semua form submit (Mulai Crawl, Terapkan, Simpan).
- **Grid metrik:** 4 kolom desktop → 2 kolom tablet → 1 kolom mobile, gap 16px.
- **Grid chart:** 2 kolom berdampingan (desktop), 1 kolom di mobile.
- **Highlight baris tabel:** baris usaha tanpa website diberi background `#ECFDF5` (hijau muda) agar langsung terlihat sebagai leads prioritas.

---

## 4. Setup Tailwind CSS Tanpa Vite / NPM Run Dev

### 4.1 Kenapa Standalone CLI (bukan CDN, bukan bundler Node)

| Opsi | Butuh Node? | Cocok untuk |
|---|---|---|
| Tailwind Play CDN (`<script src="cdn.tailwindcss.com">`) | Tidak | Prototyping cepat, TAPI file tidak di-purge (besar, JIT compile di browser tiap load — tidak ideal untuk dashboard yang dipakai berjam-jam tiap hari) |
| **Tailwind Standalone CLI (binary)** ✅ | **Tidak** | Rekomendasi utama — compile sekali jadi file CSS statis kecil, tanpa Vite, tanpa `npm run dev`, tanpa `package.json` di server |
| Tailwind via PostCSS/Vite | Ya, wajib | Dihindari sesuai permintaan — project ini murni Python di server |

### 4.2 Langkah Instalasi Tailwind Standalone CLI

```bash
# 1. Download binary sesuai OS (contoh Linux 64-bit) — sekali saja, tidak perlu npm
curl -sLO https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64
chmod +x tailwindcss-linux-x64
mv tailwindcss-linux-x64 tailwindcss   # taruh di root project

# 2. Buat file konfigurasi
./tailwindcss init
```

**`tailwind.config.js`**
```js
module.exports = {
  content: [
    "./app/templates/**/*.html",
  ],
  theme: {
    extend: {
      colors: {
        sidebar: "#0B0F19",
        sidebarActive: "#1E293B",
        contentBg: "#F5F6F8",
        accentBlue: "#1D4ED8",
        accentBlueBg: "#DBEAFE",
        highlightLead: "#ECFDF5",
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
      },
    },
  },
  plugins: [],
}
```

**`app/static/src/app.css`** (source, belum dicompile)
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer components {
  .btn-primary  { @apply inline-block bg-sidebar text-white text-sm font-medium px-5 py-2.5 rounded-lg hover:opacity-90 transition; }
  .card         { @apply bg-white border border-gray-200 rounded-lg p-6; }
  .metric-label { @apply text-[11px] uppercase tracking-wide text-gray-500 font-medium; }
  .metric-value { @apply text-3xl font-bold text-gray-900; }
  .pill-active  { @apply bg-accentBlueBg text-accentBlue text-sm px-3 py-1.5 rounded-full font-medium; }
  .lead-highlight { @apply bg-highlightLead; }
}
```

**Perintah build (dijalankan tiap ada perubahan class, cukup 1 command, bukan dev server):**
```bash
./tailwindcss -i ./app/static/src/app.css -o ./app/static/css/app.css --minify
```
> Selama development lokal boleh pakai `--watch` (opsional, murni file-watcher bawaan Tailwind CLI, BUKAN Vite/npm run dev):
> `./tailwindcss -i ./app/static/src/app.css -o ./app/static/css/app.css --watch`

**Pemakaian di layout Jinja2:**
```html
<link rel="stylesheet" href="{{ url_for('static', path='css/app.css') }}">
```

Tidak ada `package.json`, `node_modules`, atau `vite.config.js` yang dibutuhkan di server produksi — cukup runtime Python + MySQL.

### 4.3 JS Ringan Tanpa Build Step

```html
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
```
Semua lewat CDN — tidak ada `npm install`, tidak ada langkah build JS apa pun.

---

## 5. Integrasi Google Places API (Detail Teknis)

### 5.1 Endpoint yang Dipakai

| Endpoint | Fungsi | Field Penting |
|---|---|---|
| `POST places.googleapis.com/v1/places:searchText` | Cari usaha berdasarkan query bebas (kategori + lokasi) | `places.id`, `places.displayName`, `places.formattedAddress`, `places.location`, `places.types` |
| `GET places.googleapis.com/v1/places/{place_id}` | Ambil detail lengkap 1 usaha | `nationalPhoneNumber`, `websiteUri`, `regularOpeningHours`, `rating`, `userRatingCount`, `businessStatus`, `googleMapsUri` |
| `GET maps.googleapis.com/maps/api/geocode/json` | (Opsional) ubah nama kota jadi koordinat pusat pencarian | `geometry.location.lat/lng` |

### 5.2 Field Mask (Wajib di Places API New)

```
# Tahap search (murah — Basic tier)
X-Goog-FieldMask: places.id,places.displayName,places.formattedAddress,places.location,places.primaryType

# Tahap detail (lebih mahal — Enterprise tier, panggil hanya untuk place_id baru)
X-Goog-FieldMask: id,displayName,formattedAddress,nationalPhoneNumber,websiteUri,rating,userRatingCount,regularOpeningHours,businessStatus,googleMapsUri,location
```

### 5.3 Prinsip Hemat Biaya

1. Panggil `searchText` dulu dengan field mask minim → dapat daftar `place_id`
2. Cek `place_id` terhadap tabel `businesses` di MySQL — skip jika sudah pernah di-fetch dalam 30 hari terakhir
3. Panggil `Place Details` **hanya** untuk `place_id` baru/perlu update
4. Simpan `api_requests_used` per sesi crawl untuk monitoring biaya di halaman `/history`
5. Set quota limit harian di Google Cloud Console sebagai pengaman terakhir

### 5.4 Pagination

`searchText` mengembalikan maksimum 20 hasil per request dengan `nextPageToken` (total maksimum ±60 hasil per query). Untuk cakupan lebih luas, jalankan beberapa variasi kata kunci per kategori (misal "bengkel motor", "servis motor") lalu dedup by `google_place_id`.

---

## 6. Desain Database (MySQL)

### 6.1 Diagram Relasi (ringkas)
```
crawl_runs ──< businesses
businesses ──o| lead_status   (1-to-1, via business_id UNIQUE)
business_profile (independen, dipakai di layer aplikasi untuk template WA)
```

### 6.2 Detail Tabel & Kolom

**`crawl_runs`**
| Kolom | Tipe |
|---|---|
| id | bigint PK auto_increment |
| location_query | varchar(255) |
| category_query | varchar(255) |
| province | varchar(100) nullable |
| city | varchar(100) nullable |
| search_method | varchar(50) default 'text_search' |
| started_at | datetime |
| finished_at | datetime nullable |
| status | varchar(50) — success/failed/partial |
| total_businesses | int default 0 |
| api_requests_used | int default 0 |

**`businesses`**
| Kolom | Tipe |
|---|---|
| id | bigint PK auto_increment |
| crawl_run_id | bigint FK → crawl_runs.id |
| google_place_id | varchar(255) **unique** |
| location_query | varchar(255) |
| category | varchar(255) nullable |
| business_name | varchar(500) |
| address | varchar(1000) nullable |
| province | varchar(100) nullable |
| city | varchar(100) nullable |
| phone | varchar(50) nullable |
| whatsapp_link | varchar(255) nullable |
| website | varchar(500) nullable |
| has_website | boolean default false |
| rating_avg | decimal(3,2) nullable |
| total_review | int default 0 |
| opening_hours | varchar(500) nullable |
| business_status | varchar(50) nullable |
| gmaps_url | varchar(1000) nullable |
| latitude | decimal(10,7) nullable |
| longitude | decimal(10,7) nullable |
| scraped_at | datetime |

**`lead_status`**
| Kolom | Tipe |
|---|---|
| id | bigint PK auto_increment |
| business_id | bigint FK → businesses.id, **unique** |
| contact_status | enum('belum_dihubungi','sudah_dihubungi','follow_up','tidak_tertarik','deal','tidak_relevan') default 'belum_dihubungi' |
| priority | enum('low','medium','high') default 'low' |
| notes | text nullable |
| last_contacted_at | datetime nullable |
| assigned_to | varchar(255) nullable |
| updated_at | datetime |

**`business_profile`**
| Kolom | Tipe |
|---|---|
| id | bigint PK auto_increment |
| company_name | varchar(255) |
| contact_person | varchar(255) nullable |
| phone | varchar(50) nullable |
| default_wa_template | text nullable |
| updated_at | datetime |

### 6.3 Business Rules

1. **Dedup usaha**: sebelum insert `lead_status` baru, sistem cek apakah `google_place_id` sudah pernah ada di `businesses`. ID ini stabil dari Google sehingga dedup jauh lebih akurat dibanding mencocokkan nama+alamat secara teks. Jika leads dengan `place_id` tsb sudah punya status tertentu, **status lama dipertahankan** — hanya data mentah `businesses` yang ditambah sebagai record baru (histori rating/status dari waktu ke waktu). Fetch ulang `place_id` yang sama dalam 30 hari terakhir sebaiknya dilewati (baca dari cache MySQL) untuk menghemat kuota API.
2. **`has_website`** dihitung otomatis: `true` jika kolom `website IS NOT NULL AND website != ''`.
3. **`priority`** dihitung otomatis saat insert/update:
   - `high` jika `has_website = false` DAN (`rating_avg >= 4.0` ATAU `total_review >= 20`)
   - `medium` jika `has_website = false` tapi rating/review rendah
   - `low` jika `has_website = true`
4. **Cascade delete**: jika sebuah `crawl_runs` dihapus, semua `businesses` terkait ikut terhapus (`ON DELETE CASCADE`), namun `lead_status` **tidak ikut terhapus** — histori follow-up sales tetap dipertahankan.

### 6.4 Indexing yang Disarankan

| Tabel | Index | Tujuan |
|---|---|---|
| `businesses` | `google_place_id` (UNIQUE) | Kunci dedup utama & cache-check sebelum panggil API lagi |
| `businesses` | `(location_query, category)` | Percepat filter dashboard per lokasi & kategori |
| `businesses` | `has_website` | Percepat filter leads prioritas |
| `lead_status` | `business_id` (UNIQUE) | Jamin relasi 1-to-1 & percepat join |
| `lead_status` | `contact_status` | Percepat filter funnel di dashboard leads |

---

## 7. Routing Plan

### 7.1 Public/Internal Routes (`app/main.py`)
```
GET  /                                   dashboard_view          → Dashboard Ringkasan
POST /crawl                              trigger_crawl            → Jalankan Places API fetch (htmx)
GET  /leads                              leads_list_view          → Tabel + Peta Leads
GET  /leads/{business_id}                lead_detail_view         → Detail 1 leads
POST /leads/{business_id}/status         update_lead_status       → Update status kontak (htmx)
GET  /history                            history_view             → Riwayat crawling
GET  /export/leads.csv                   export_leads_csv         → Export CSV
GET  /export/leads.xlsx                  export_leads_excel       → Export Excel
GET  /guide                              guide_view               → Metodologi & panduan
GET  /settings/profile                   profile_view             → Form profil bisnis
POST /settings/profile                   update_profile           → Simpan profil bisnis
```

### 7.2 API Internal (dipakai oleh htmx, bukan publik)
```
GET  /api/leads/table        → partial HTML tabel leads (untuk filter/sort tanpa reload)
GET  /api/dashboard/metrics  → partial HTML 4 kartu metrik (untuk filter agregasi)
GET  /api/dashboard/charts   → data JSON untuk Chart.js
```

---

## 8. Modul & Komponen (Detail Implementasi)

| Modul | Fitur Tampilan | Data/Aksi |
|---|---|---|
| Dashboard | Form crawl, filter agregasi, 4 kartu metrik, 2 chart | Trigger `ingest.pipeline.run()`, query agregasi SQLAlchemy |
| Leads Table | Tabel + peta, highlight leads tanpa website | Filter/sort via query param, `hx-get` partial |
| Lead Detail | Info usaha, histori status, form update | `hx-post` update `lead_status`, generate link `wa.me` dari `business_profile` |
| History | Tabel log crawl + api_requests_used | Read-only, join `crawl_runs` |
| Export | Tombol CSV/Excel | Generate file dari pandas DataFrame hasil query leads terfilter |
| Profil Bisnis | Form 1 halaman | CRUD `business_profile` (biasanya cuma 1 baris) |
| Guide | Halaman statis | Konten hardcode di template (boleh statis karena bukan data operasional) |

---

## 9. Struktur Folder Project (Final)

```
leadmaps-bi/
├── app/
│   ├── main.py                     # FastAPI app & route registration
│   ├── database.py                 # SQLAlchemy engine/session
│   ├── models.py                   # crawl_runs, businesses, lead_status, business_profile
│   ├── config.py                   # env vars (DB, GOOGLE_MAPS_API_KEY)
│   ├── deps.py                     # dependency injection (get_db, dsb)
│   ├── routers/
│   │   ├── dashboard.py
│   │   ├── leads.py
│   │   ├── history.py
│   │   ├── export.py
│   │   └── settings.py
│   ├── places_api/
│   │   ├── client.py               # wrapper httpx: search_text(), get_place_details()
│   │   ├── geocoding.py            # opsional
│   │   ├── field_masks.py
│   │   └── mapper.py               # JSON Google → schema internal
│   ├── ingest/
│   │   └── pipeline.py             # orkestrasi: search → dedup → detail → clean → save
│   ├── leads/
│   │   └── scoring.py              # logic auto-priority
│   ├── templates/
│   │   ├── layouts/
│   │   │   └── base.html           # sidebar + slot konten
│   │   ├── partials/
│   │   │   ├── metric_card.html
│   │   │   ├── filter_bar.html
│   │   │   ├── leads_table.html
│   │   │   └── nav_sidebar.html
│   │   ├── dashboard.html
│   │   ├── leads_list.html
│   │   ├── lead_detail.html
│   │   ├── history.html
│   │   ├── guide.html
│   │   └── settings_profile.html
│   └── static/
│       ├── src/app.css             # source Tailwind
│       └── css/app.css             # hasil compile (statis, di-commit)
├── requirements.txt
├── tailwind.config.js
├── tailwindcss                     # binary standalone (di-.gitignore atau commit)
├── docker-compose.yml              # MySQL untuk dev lokal
├── .env.example
└── README.md
```

---

## 10. Autentikasi Internal (Opsional, Ringan)

Karena ini tool internal (dipakai tim sales sendiri, bukan publik), autentikasi dibuat **sesederhana mungkin, tanpa framework pihak ketiga**:
1. Tabel `users` sederhana (email, password_hash, role: admin/sales) — bisa ditambahkan belakangan jika perlu multi-user.
2. Middleware session-based (`starlette.middleware.sessions.SessionMiddleware`) + halaman login manual.
3. Untuk v1 (single-user/tim kecil), **boleh dilewati dulu** dan cukup diamankan lewat basic auth di reverse proxy (Nginx) atau restrict akses by IP/VPN — sesuai kebutuhan riil tim.

---

## 11. Design System (Acuan UI — Ringkas)

| Token | Nilai |
|---|---|
| Font | Inter (Google Fonts `<link>`, bukan npm package) |
| Sidebar bg | `#0B0F19` |
| Content bg | `#F5F6F8` |
| Card | putih, border `#E5E7EB`, radius 8px, shadow tipis |
| Highlight leads prioritas | `#ECFDF5` (hijau muda) |
| Tombol primer | `bg-sidebar text-white rounded-lg px-5 py-2.5` |
| Grid metrik | `grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4` |
| Grid chart | `grid grid-cols-1 lg:grid-cols-2 gap-4` |

> Token di atas dan detail lengkap di Bagian 3 (Analisis Visual/UI) adalah acuan tunggal — ikuti persis, jangan menebak warna/komponen di luar yang tertulis di dokumen ini.

---

## 12. Rencana Tahapan Pengerjaan (Sprints)

**Sprint 1 — Fondasi**
- Setup Google Cloud project, aktifkan Places API (New), buat & restrict API key
- Setup FastAPI project, virtualenv, `requirements.txt`
- Setup MySQL via `docker-compose.yml` (dev lokal)
- Setup Tailwind Standalone CLI (Bagian 4.2) — pastikan tidak ada `package.json`/`vite.config.js`
- Buat `models.py` (SQLAlchemy) sesuai skema di Bagian 6, jalankan migration/`create_all`
- Buat `layouts/base.html` + `partials/nav_sidebar.html` sesuai Design System

**Sprint 2 — Integrasi Places API & Pipeline**
- Buat `places_api/client.py`: `search_text()`, `get_place_details()`, dengan field mask sesuai Bagian 5.2
- Buat `ingest/pipeline.py`: orkestrasi search → cek dedup by `google_place_id` → detail fetch → cleaning (pandas) → simpan MySQL
- Buat `leads/scoring.py`: auto-priority high/medium/low

**Sprint 3 — Dashboard Ringkasan**
- Route `/` + `/crawl` (trigger pipeline via htmx)
- Card filter agregasi, 4 kartu metrik dinamis dari query SQLAlchemy
- 2 chart (Chart.js) dari endpoint `/api/dashboard/charts`

**Sprint 4 — Manajemen Leads**
- Route `/leads` (tabel + peta Leaflet), filter/sort via `hx-get`
- Route `/leads/{id}` (detail + form update status via `hx-post`)
- Tombol WhatsApp dengan template dari `business_profile`

**Sprint 5 — Riwayat & Export**
- Route `/history` (tabel log crawl + `api_requests_used`)
- Route export CSV/Excel dari leads terfilter

**Sprint 6 — Konfigurasi**
- Route `/settings/profile` (CRUD `business_profile`)
- Halaman `/guide` (statis)
- (Opsional) autentikasi internal sesuai Bagian 10

**Sprint 7 — Polish & Deployment**
- Responsive check (sidebar → drawer di mobile, grid metrik 1 kolom)
- Retry/backoff untuk request Places API yang gagal/timeout, handle HTTP 429
- Compile Tailwind final dengan `--minify`
- Setup deployment (Bagian 14)

---

## 13. Checklist Performa, Keamanan & Kontrol Biaya API

- [ ] `GOOGLE_MAPS_API_KEY` di `.env`, tidak pernah di-commit ke Git
- [ ] API key di-restrict by IP/HTTP referrer di Google Cloud Console
- [ ] Quota limit harian di-set di Google Cloud Console
- [ ] Cache/dedup by `google_place_id` sebelum panggil `Place Details` lagi
- [ ] Field mask selalu diset eksplisit (jangan minta field yang tidak dipakai)
- [ ] Retry dengan exponential backoff untuk HTTP 429/5xx dari Places API
- [ ] Validasi & normalisasi nomor telepon sebelum disimpan
- [ ] Rate limiting endpoint `/crawl` (misal via `slowapi`) untuk cegah trigger crawl berulang tanpa sengaja
- [ ] Index database sesuai `ERD-gmaps-lead-scraper.md` §4 (Indexing yang Disarankan)
- [ ] `.env` terpisah untuk dev/production, tidak pernah hardcode kredensial

---

## 14. Deployment (VPS/Cloud — Bukan Shared Hosting PHP)

> Berbeda dari stack PHP yang bisa jalan di shared hosting cPanel, FastAPI butuh runtime Python persisten — cocok untuk VPS kecil (mis. 1 vCPU/1GB RAM) atau container.

1. Siapkan server (Ubuntu 22.04+), install Python 3.11+, MySQL 8 (atau pakai managed MySQL)
2. Clone project, buat virtualenv, `pip install -r requirements.txt`
3. Copy `.env.example` → `.env`, isi kredensial DB & `GOOGLE_MAPS_API_KEY`
4. Compile Tailwind final di lokal (atau di server sekali saja), commit/copy hasil `static/css/app.css` — server tidak perlu binary Tailwind kalau CSS sudah statis
5. Jalankan migration (`Base.metadata.create_all` atau Alembic jika dipakai)
6. Jalankan dengan `uvicorn app.main:app --host 0.0.0.0 --port 8000` di belakang **Nginx reverse proxy**
7. (Opsional) pakai `systemd` service atau `supervisor` agar proses uvicorn auto-restart
8. (Opsional) Docker: siapkan `Dockerfile` + `docker-compose.yml` untuk app + MySQL sekaligus, mempermudah deploy ulang

---

## 15. Checklist Fitur Lengkap (Ringkasan Final)

- [x] Dashboard ringkasan dengan filter agregasi & 4 kartu metrik dinamis
- [x] Fetch data usaha via Google Places API (searchText + Place Details), bukan scraping DOM
- [x] Deteksi otomatis `has_website` sebagai flag leads prioritas
- [x] Auto-priority scoring (high/medium/low) berbasis rating & jumlah review
- [x] Dedup berbasis `google_place_id` (bukan cocokan teks nama+alamat)
- [x] Tabel leads dengan filter/sort tanpa reload (htmx)
- [x] Peta interaktif (Leaflet) dengan pin berwarna per status website
- [x] Halaman detail leads + tracking status funnel + catatan follow-up
- [x] Tombol WhatsApp dengan template pesan siap kirim
- [x] Riwayat crawling + monitoring jumlah API request per sesi (kontrol biaya)
- [x] Export CSV/Excel
- [x] Profil bisnis untuk template pesan WA
- [x] Tailwind CSS compile tanpa Vite/NPM run dev
- [x] Tanpa dependency Node.js di server produksi

---

## 16. Langkah Selanjutnya

Setelah plan ini disetujui, langkah build aktual disarankan urut sesuai **Bagian 12 (Sprint 1 → 7)**. Saya bisa langsung mulai membuatkan:
1. Struktur project FastAPI + models + Tailwind Standalone CLI setup (Sprint 1), atau
2. Langsung tampilan Dashboard (Jinja2 + Tailwind) sesuai `DESIGN.md` sebagai contoh visual dulu.

Beri tahu mana yang ingin dikerjakan lebih dulu.

# LeadMaps BI — Business Lead Scraper & Market Intelligence Dashboard

Dashboard internal business intelligence dan lead generation untuk mencari prospek usaha lokal via **Google Maps (SerpApi / Google Places API)** per lokasi dan kategori usaha, dengan sistem tracking status follow-up sales, kalkulasi prioritas otomatis, dan ekspor data tanpa build step Node.js di server produksi.

---

## Fitur Utama

- **Live Google Maps Data**: Pencarian data bisnis lokal real-time (Nama Usaha, Alamat, Nomor Telepon WhatsApp, Rating, Jumlah Ulasan, Jam Buka, Koordinat Peta).
- **Dukungan API Fleksibel**:
  - **SerpApi (Direkomendasikan)**: 100 search gratis/bulan tanpa perlu kartu debit/kredit.
  - **Google Places API (New)**: Integrasi resmi Google Cloud.
  - **Mock Offline Mode**: Data simulasi fixture JSON saat tanpa koneksi/API key.
- **Lead Priority Scoring Otomatis**:
  - **HIGH**: Usaha tanpa website (`has_website = False`) dengan Rating $\ge 4.0$ atau Ulasan $\ge 20$ (Target utama penawaran web).
  - **MEDIUM**: Usaha tanpa website dengan rating & ulasan rendah (Prospek sekunder).
  - **LOW**: Usaha yang sudah memiliki website resmi.
- **Dropdown Kota Dinamis**: Pilihan kota/kabupaten otomatis menyesuaikan dengan provinsi yang dipilih.
- **Katalog Portofolio & Demo Web Otomatis (Demo Matcher)**:
  - Sistem otomatis mencocokkan kategori usaha prospek dengan link demo web spesifik (misal: Toko/Retail $\rightarrow$ Demo E-Commerce, Klinik/Dokter $\rightarrow$ Demo Janji Temu Dental, Resto/Kafe $\rightarrow$ Demo QR Menu, Bengkel $\rightarrow$ Demo Service Booking).
  - Manajemen katalog portofolio lengkap di menu **Profil Bisnis Saya** (bisa tambah/hapus link demo dan kata kunci kategori).
- **WhatsApp Outreach Studio Interaktif**:
  - Di halaman Detail Lead, tersedia editor pesan interaktif dengan preview real-time.
  - Pilihan variasi template (*Direct Demo Link*, *Fokus Solusi Omset*, *Santai & Bersahabat*).
  - Tombol WhatsApp otomatis memperbarui URL pesan secara langsung saat teks diketik atau saat link portofolio diganti.
  - Tombol **Copy Teks** instan ke clipboard.
- **Tabel Leads & Peta Interaktif (Leaflet.js)**:
  - Baris tanpa website otomatis di-highlight hijau lembut.
  - Pin peta interaktif (Emerald = Target Tanpa Web, Slate = Sudah Punya Web).
  - **Update Status Instan per Baris**: Ubah status kontak langsung dari dropdown tabel tanpa refresh halaman.
- **Tracking Funnel Sales Lengkap**:
  - 6 status follow-up: *Belum Kontak*, *Sudah Di-WA*, *Follow Up*, *Deal Client*, *Tidak Tertarik*, *Tidak Relevan*.
  - Catatan negosiasi sales (`notes`), PIC penanggung jawab (`assigned_to`), dan timestamp kontak terakhir.
- **Export Data Fleksibel**:
  - **CSV (UTF-8 BOM)**: Siap untuk WhatsApp broadcast manual atau CRM import.
  - **Excel (.xlsx)**: Spreadsheet rapi dengan lebar kolom otomatis via `openpyxl`.
- **Zero Node.js di Server**:
  - Menggunakan **Tailwind CSS Standalone CLI** binary untuk kompilasi CSS statis minified.
  - Frontend interaktif menggunakan **HTMX**, **Leaflet.js**, dan **Chart.js** via CDN.


---

## 💻 Panduan Menjalankan di Lokal (Local Development)

### 1. Konfigurasi Database & Environment
Buka file `.env` di root project dan sesuaikan konfigurasi database Anda:
```env
# 1. Konfigurasi Database MySQL (Parameter Terpisah)
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_NAME=leadmaps_bi

# 2. API Key Google Maps
# -> Masukkan API Key SerpApi Anda (Gratis 100 search/bulan):
SERPAPI_API_KEY=fc7b417886ef04670a8e7536600090fa4cff3fe194f21f4300344f3960b18f2a

# (Opsional) Jika menggunakan Google Cloud Places API:
GOOGLE_MAPS_API_KEY=

# 3. Pengaturan Aplikasi
DEBUG=True
APP_NAME=LeadMaps BI
APP_ENV=development
SECRET_KEY=leadmaps_secret_key_dev_mode_12345
```

### 2. Install Dependencies & Jalankan Server
```powershell
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Buka browser di: **`http://localhost:8000`**

---

## 💾 Cara Memindahkan Data Lokal ke Server (Supaya Data Tidak Hilang)

Agar data usaha yang sudah di-crawl di lokal tetap ada saat aplikasi dipindahkan ke server VPS produksi:

### 1. Export (Backup) Database dari Lokal
Jalankan perintah ini di Command Prompt / Terminal Windows Anda (atau gunakan fitur Export di phpMyAdmin / HeidiSQL):
```bash
mysqldump -u root -p leadmaps_bi > backup_leadmaps.sql
```

### 2. Upload & Restore Database di Server Produksi
Setelah server VPS Anda siap dan database `leadmaps_bi` sudah dibuat:
```bash
# Upload file backup_leadmaps.sql ke server via SCP/SFTP, lalu jalankan di server:
mysql -u leadmaps_user -p leadmaps_bi < backup_leadmaps.sql
```
*Semua data leads, riwayat crawling, status follow-up sales, dan catatan Anda akan langsung terisi lengkap di server tanpa hilang sedikit pun.*

---

## 🚀 Panduan Deployment Produksi (Server VPS / Ubuntu)

### Opsi A: Menggunakan Docker Compose (Paling Cepat & Otomatis)

1. Clone repository ke server VPS Anda:
   ```bash
   git clone <url_repo_anda> /var/www/leadmaps-bi
   cd /var/www/leadmaps-bi
   ```
2. Buat file `.env` produksi:
   ```bash
   cp .env.example .env
   nano .env
   ```
   *Pastikan `SERPAPI_API_KEY`, `DEBUG=False`, dan `SECRET_KEY` diisi dengan benar.*
3. Jalankan container:
   ```bash
   docker compose up -d --build
   ```
4. Restore data lama (opsional):
   ```bash
   docker exec -i leadmaps_mysql mysql -u leadmaps_user -pleadmaps_password leadmaps_bi < backup_leadmaps.sql
   ```
   Aplikasi langsung aktif di port `8000`.

---

### Opsi B: Manual di Ubuntu VPS (Systemd + Nginx)

#### 1. Install Paket Server & Setup Database
```bash
sudo apt update && sudo apt install -y python3 python3-pip python3-venv mysql-server nginx

# Setup Database MySQL
sudo mysql -e "CREATE DATABASE leadmaps_bi CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
sudo mysql -e "CREATE USER 'leadmaps_user'@'localhost' IDENTIFIED BY 'password_aman_anda';"
sudo mysql -e "GRANT ALL PRIVILEGES ON leadmaps_bi.* TO 'leadmaps_user'@'localhost'; FLUSH PRIVILEGES;"
```

#### 2. Setup Project & Virtual Environment
```bash
sudo mkdir -p /var/www/leadmaps-bi
sudo chown -R $USER:$USER /var/www/leadmaps-bi
cd /var/www/leadmaps-bi

# Copy file project Anda ke folder ini
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Inisialisasi tabel database (jika tidak restore dari backup):
python -c "from app.database import init_db; init_db()"
```

#### 3. Pasang Systemd Service (Auto-Start & Restart)
```bash
sudo cp deploy/leadmaps.service /etc/systemd/system/leadmaps.service
sudo systemctl daemon-reload
sudo systemctl enable --now leadmaps.service
```

#### 4. Pasang Nginx Reverse Proxy & SSL (HTTPS)
```bash
sudo cp deploy/nginx-leadmaps.conf /etc/nginx/sites-available/leadmaps
sudo ln -s /etc/nginx/sites-available/leadmaps /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Pasang SSL Gratis (Certbot Let's Encrypt):
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d domainanda.com
```

---

## 📁 Struktur Folder Project

```text
leadmaps-bi/
├── app/
│   ├── main.py                     # FastAPI app, routing, & lifespan handler
│   ├── database.py                 # SQLAlchemy engine & session setup
│   ├── models.py                   # Model: crawl_runs, businesses, lead_status, business_profile
│   ├── config.py                   # Pydantic Settings & environment loader (MySQL + SerpApi)
│   ├── deps.py                     # Dependency injection (get_db)
│   ├── routers/
│   │   ├── dashboard.py            # Overview metrics, /crawl trigger via HTMX, & Chart.js data
│   │   ├── leads.py                # Leads list, Leaflet map markers, quick status update, & detail
│   │   ├── history.py              # Crawl audit logs & API request counter
│   │   ├── export.py               # CSV & Excel (.xlsx) export engine
│   │   └── settings.py             # Business profile CRUD & methodology guide view
│   ├── places_api/
│   │   ├── client.py               # SerpApi & Google Places API client + retry backoff & mock loader
│   │   ├── mapper.py               # Normalisasi response -> Schema DB + WhatsApp link generator
│   │   └── fixtures/               # Mock data dummy JSON untuk testing offline
│   ├── ingest/
│   │   └── pipeline.py             # Orkestrasi: search -> dedup 30 hari -> cleaning pandas -> sync MySQL
│   ├── leads/
│   │   └── scoring.py              # Logika kalkulasi lead priority (HIGH/MEDIUM/LOW)
│   ├── templates/                  # Jinja2 HTML templates (Clean & Formal UI)
│   └── static/css/app.css          # Compiled Tailwind CSS (Statis & Minified)
├── deploy/
│   ├── leadmaps.service            # Systemd service unit template
│   └── nginx-leadmaps.conf         # Nginx reverse proxy template
├── Dockerfile                      # Production Docker container
├── docker-compose.yml              # Multi-container app + MySQL
├── requirements.txt                # Python package dependencies
├── tailwind.config.js              # Konfigurasi Tailwind CSS
├── tailwindcss.exe                 # Binary Tailwind Standalone CLI
└── README.md                       # Dokumentasi lengkap
```
"# scraping" 

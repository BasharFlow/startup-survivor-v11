# Startup Survivor (Streamlit) — Cloud-Ready Repo

Bu repo, **Streamlit Community Cloud**'a direkt deploy edilebilir şekilde hazırlanmıştır.

## 1) Streamlit Community Cloud’da çalıştırma (önerilen)

### A) GitHub’a yükle
1. GitHub’da yeni repo aç (Public/Private fark etmez).
2. Bu klasördeki dosyaları repo köküne koy:
   - `app.py`
   - `requirements.txt`
   - `core/`, `content/` klasörleri
3. Commit + push.

### B) Streamlit Cloud’a deploy et
1. Streamlit Community Cloud → **New app**
2. Repo + branch seç
3. **Main file path**: `app.py`
4. (İsteğe bağlı) **Advanced settings**’ten Python versiyonunu seç
5. Deploy.

### C) Secrets (Gemini zorunlu)
Bu sürüm **LLM-only** çalışır (offline fallback yok). Devam etmek için Gemini API key eklemelisin:

Streamlit Cloud → App settings → **Secrets** alanına şunu ekle:

```toml
GOOGLE_API_KEY = "YOUR_KEY"
# veya
# GEMINI_API_KEY = "YOUR_KEY"
```

> Anahtar **asla ekrana basılmaz**, sadece env/secrets üzerinden okunur.

## 2) Lokal çalıştırma (tek komut)

### macOS / Linux
```bash
bash run_local.sh
```

### Windows (PowerShell)
```powershell
./run_local.ps1
```

## 3) Hızlı doğrulama
```bash
python -m core.selfcheck
```

## 4) Sık karşılaşılan deploy notları
- Community Cloud bağımlılıkları `requirements.txt` ile kurar. Gerekirse OS paketleri için `packages.txt` eklenir.
- Python sürümü, deploy sırasında **Advanced settings**’ten seçilebilir.


## Oyun akışı notu
- Her ay 2-3 seçenek (A/B/(C)) gelir.
- Ayrıca **"Kendi çözümün"** alanına kendi planını yazıp **"Bu planı uygula"** diyebilirsin. (Gemini planını yapılandırır, ekonomi deterministik şekilde uygulanır.)

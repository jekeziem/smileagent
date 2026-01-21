# SmileAgent 🦷

> AI-powered dental aggregator for the Irish market. Emergency triage, Medical Card filtering, Med 2 tax automation.

## Quick Start (Local Development)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy environment template
cp .env.example .env

# 3. Run the server
python main.py

# 4. Open in browser
# http://localhost:8001
```

## Project Structure

```
smileagent/
├── main.py              # FastAPI backend
├── index.html           # Vue.js frontend (single file)
├── requirements.txt     # Python dependencies
├── .env.example         # Environment template (commit this)
├── .env                 # Your secrets (DO NOT commit)
├── .gitignore          
├── render.yaml          # Render.com deployment config
├── vercel.json          # Vercel deployment config
└── README.md
```

## Deployment

### Backend (Render.com - Free)
1. Push to GitHub
2. Connect repo on render.com
3. Set environment variables
4. Deploy

### Frontend (Vercel - Free)
1. Update `apiBase` in index.html to your Render URL
2. Connect repo on vercel.com
3. Deploy

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DEBUG` | Enable debug mode | No (default: false) |
| `ENCRYPTION_KEY` | Fernet encryption key | Yes |
| `ALLOWED_ORIGINS` | CORS allowed origins | Yes |

Generate encryption key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Features

- ✅ Emergency Triage (Manchester Triage adapted)
- ✅ Medical Card / PRSI filtering
- ✅ Med 2 Tax Relief automation
- ✅ PDF generation
- ✅ GDPR consent logging
- ✅ Mobile-responsive UI

## Pilot Area

Dublin 22 (Clondalkin) - 3 clinics

## License

Proprietary - All rights reserved

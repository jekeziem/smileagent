# SmileAgent 🦷

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
├── main.py             
├── index.html           
├── requirements.txt     
├── .env.example         
├── .env    
├── .gitignore          
├── render.yaml          
├── vercel.json         
└── README.md
```



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


## Pilot Area

Dublin 22 (Clondalkin) - 3 clinics

## License

Proprietary - All rights reserved

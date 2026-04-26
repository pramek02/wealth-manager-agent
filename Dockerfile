FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libfreetype6-dev libpng-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Only build local stock database if not already present
RUN python -c "from pathlib import Path; import sys; sys.exit(0) if Path('data/stocks.db').exists() else None" || python setup_local_db.py

EXPOSE 8000

CMD ["python", "main.py"]

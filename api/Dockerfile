# Imagem de producao do painel + API SOMPO (Flask servido por waitress).
FROM python:3.12-slim

# Nao gerar .pyc e log sem buffer (melhor para os logs do Render).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instala as dependencias primeiro (cache de camada enquanto o requirements nao muda).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copia o codigo da API (o .dockerignore mantem venv/.env/tests fora da imagem).
COPY . .

# Porta local padrao; no Render a plataforma injeta a env PORT.
EXPOSE 5000

# Sobe com waitress (WSGI de producao) em 0.0.0.0, respeitando a porta do host.
# 'app:app' = objeto Flask 'app' definido em app.py.
CMD ["sh", "-c", "waitress-serve --host=0.0.0.0 --port=${PORT:-5000} app:app"]
